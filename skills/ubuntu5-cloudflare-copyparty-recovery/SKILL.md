---
name: ubuntu5-cloudflare-copyparty-recovery
description: 处理“Cloudflare 530/1033”“upload.lynch5mo.xyz 上传失败/变慢”“ubuntu5 Tunnel 不稳”这类故障。适用于先恢复 `ubuntu5` 可达性、再验证 cloudflared 与 Copyparty 的受控排障。
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  argument_hint: "[outage|upload|verify]"
---

# Ubuntu5 Cloudflare + Copyparty recovery

## When to use

- 用户报告 `alpha-ficc.lynch5mo.xyz` 或 `upload.lynch5mo.xyz` 的 Cloudflare 530/1033、Tunnel 不可用、外网上传在中途失败，或要求稳定性与速度一起处理。
- 需要确认 Copyparty 当前 `u2j` / `u2sz` 配置、验证公网上传，或判断是否应考虑独立高速入口。

不要用于：

- Alpha-FICC 应用代码/Provider 实现问题。
- 没有明确授权的凭证重置、Cloudflare token 修改或大规模 NAS 文件操作。

## Inputs / context to gather

1. 当前工作目录是否为 `/Users/lynch5mo/Work Documents/Mac`，目标主机是否仍为 `ubuntu5` / `192.168.10.33`。
2. 故障是全站不可达、Tunnel 失败、主机压力，还是仅 Copyparty 上传性能；记录外部 URL 的 HTTP 状态。
3. 只用 SSH key 与 known_hosts。不要读取/输出完整 secrets、不要用 `sshpass` 或关闭 host-key 检查。
4. 需要写配置前，先确认持久真源：
   - `/var/lib/casaos/apps/cloudflared/docker-compose.yml`
   - `/DATA/AppData/copyparty/cfg/copyparty.conf`

## Procedure

1. 先分层定位，不要先改 Cloudflare token 或 NAS 权限。
   - 外部 URL -> 主机 LAN 可达性 -> `cloudflared` 容器及真实子进程 -> 主机 `uptime` / `free -m` / `docker stats` -> 后端服务。
   - 当 hostname/Tailscale 不可靠时，直接用 `192.168.10.33`。
2. 主机压力优先排除。
   - 检查 swap、iowait、load 与高耗容器。历史上 `immich-machine-learning` 曾耗尽 4 GiB 主机的内存；持久 limit 在 `/var/lib/casaos/apps/immich/docker-compose.yml`。
   - SSH banner hang 先当成 load/latency 症状，而不是立刻认定机器完全挂了。
3. 若日志出现 `failed to dial a quic connection ... timeout: no recent network activity`，确认 cloudflared 持久配置为 `PROTOCOL: http2`，重建后检查 `cloudflared-watchdog.timer` 是否持续覆盖容器和实际子进程。
4. 验证修复必须同时覆盖：公网入口 HTTP 200、后端本地服务、Tunnel 子进程、主机资源合理。视频流额外验证 HTTP 206、`accept-ranges: bytes`、`content-type: video/webm`。
5. 调 Copyparty 时以稳定为先。
   - 保持已验证配置 `u2j: 1`、`u2sz: 96`，除非用户明确授权做受控试验。
   - 用小文件开始并逐步增加：公网上传须返回 HTTP 201、确认写入后清理测试文件；对比 LAN 与公网速度以定位瓶颈。
   - 若日志包含 `please upload sequentially using one thread`，不要提高 `u2j`。需要明显提速时，提出独立 IPv6、DNS-only 或 HTTPS 反代入口，保留 Tunnel 作为稳定路径。

## Efficiency plan

1. 先用一条外部状态和一条 LAN/SSH 探测确定故障层，避免同时改 host、Tunnel、Copyparty。
2. 使用短、单目的 SSH 命令；复杂 shell quoting 容易失败，也会触发安全策略。
3. 不依赖页面源码显示 `u2sz`；以服务端配置和真实 HTTP 201 测试作为证据。
4. 达到“公网 HTTP 200 + 上传 HTTP 201 + 必要时 Range HTTP 206”后停止扩展排障；性能建议与变更分开。

## Pitfalls and fixes

- 症状：530/1033 -> 可能是主机资源、网络不可达或 Tunnel 协议问题，不是单一 Cloudflare 配置故障；按分层顺序证伪。
- 症状：命令被拦截或远端写入失败 -> 避免 `sshpass`、disabled host-key checks、宽范围 `docker inspect`、完整配置输出；改用 key/known_hosts 和脱敏窄读取。
- 症状：提高并发后上传失败 -> `u2j` 保持 1，并用受控 A/B 上传而非直接升并发。

## Verification checklist

- [ ] 确认 `ubuntu5` / `192.168.10.33` 可达，并记录主机资源状态。
- [ ] 公网 `upload.lynch5mo.xyz` 与相关入口返回预期 HTTP 200。
- [ ] `cloudflared` 真实子进程存在；若曾有 QUIC 超时，持久配置为 `PROTOCOL: http2`，watchdog 可用。
- [ ] Copyparty 配置仍为预期 `u2j: 1`、`u2sz: 96`，或所有偏离都有明确、已验证的授权。
- [ ] 公网测试上传返回 HTTP 201，测试文件已清理；流媒体场景确认 HTTP 206。
