---
name: android-obsidian-self-hosted-git
description: Use when an Android Obsidian Vault must share one self-hosted Git checkout with Termux, especially when locating an existing Vault, avoiding duplicate clones, or applying Agent-KB device identity and graph policy.
license: MIT
metadata:
  version: "1.1.0"
  author: lynch5mo
  category: knowledge-management
---

# 安卓连接自建 Git Obsidian 知识库

适用于：NAS 或私有服务器上托管的 Git 仓库 + 安卓手机 + Obsidian

## 先复用现有 Vault，禁止直接创建第二份

先从 Obsidian 的 Vault 管理页面确认完整路径。Agent-KB 的 Vivo 路径通常是 `/storage/emulated/0/agent-kb`。随后在 Termux 做只读核验：

```bash
cd "/storage/emulated/0/agent-kb"
git rev-parse --show-toplevel
git remote get-url origin
git status --short --branch
```

只有路径不存在或 `git rev-parse` 明确证明它不是 Git checkout 时，才考虑 clone。不要因为 Termux 当前提示符在 `~` 就断言手机没有副本；Android App 私有目录和 `.git` 文件也可能使简单 `find -type d` 漏检。

## 前置条件
- 安卓手机与服务器在同一内网（或有 VPN）
- 服务器已配置 SSH 访问
- 知识库已是 Git 仓库

## 步骤

### 1. 安装软件
- **Obsidian**：Google Play 安装
- **Termux**：从 F-Droid 安装（Play 版已停更）
  - 地址：https://f-droid.org/packages/com.termux/

### 2. Termux 里安装 Git 和 SSH
```bash
pkg install git openssh
```

### 3. Termux 授权存储权限（必须在 clone 之前！）
```bash
termux-setup-storage
```
- 会弹系统权限请求，点**允许**
- 如果提示 `~/storage` 已存在，输入 `y` 然后**回车**
- 如果弹出"管理所有文件"设置页，找到 Termux → 允许
- ⚠️ 这步不做的话，`~/storage/shared/` 不会链接到手机真实存储，Obsidian 看不到文件

### 4. 生成 SSH key
```bash
ssh-keygen
```
三个问题全部按回车（默认路径、不设密码、确认）

### 5. 把公钥加到服务器
```bash
cat ~/.ssh/id_ed25519.pub
```
把输出内容加到服务器的 `~/.ssh/authorized_keys` 里

### 6. 配置 SSH 连接
```bash
cat >> ~/.ssh/config << 'EOF'
Host nas
    HostName <服务器IP>
    User <用户名>
    IdentityFile ~/.ssh/id_ed25519
EOF
```

### 7. 测试连接
```bash
ssh nas echo "connected"
```
⚠️ 首次连接会问是否信任主机，必须输入完整的 `yes`（不是 `y`）

### 8. Clone 仓库
```bash
git clone ssh://<用户>@<IP>/<仓库路径>.git ~/storage/shared/<vault名>
```
⚠️ `~/storage/shared/` 对应手机内部存储根目录（`/storage/emulated/0/`）

### 9. Obsidian 打开仓库
- 选 **Open folder as vault**
- 路径：`/storage/emulated/0/<vault名>`

### 10. 安装 Obsidian Git 插件（可选）
- 设置 → 第三方插件 → 关安全模式 → 浏览 → 搜 **Obsidian Git** → 安装启用
- 插件设置：
  - Vault backup interval：10
  - Auto pull on startup：打开
  - Auto push on commit：打开

Termux 与 Obsidian Git 插件不要同时执行自动提交/推送；选择一个同步责任方，避免并发 commit 和 non-fast-forward。

## Agent-KB Vivo 绑定与图谱规则

在已确认的 `/storage/emulated/0/agent-kb` 中执行：

```bash
git config --local core.filemode false
git pull --rebase origin main
python3 ops/scripts/configure_agent_instance.py set hermes-vivo-mobile
python3 ops/scripts/configure_agent_instance.py check Hermes
bash ops/scripts/sync_obsidian_graph.sh
bash ops/scripts/sync_obsidian_graph.sh --check
```

`core.filemode false` 只作用于当前 Android clone，用于消除共享存储的权限假变更。`outputs/` 继续由 Git 同步，但由 Agent-KB policy 排除出 Obsidian 搜索和关系图谱。

`Rebuild vault cache` 必须从 Obsidian 命令面板执行，不是 Termux shell 命令。只有旧报告节点仍残留时才需要重建缓存。

## 常见坑
1. **ssh-keygen 跑出帮助信息**：Termux 键盘输入可能有误（自动纠错、空格等）。用最简单的 `ssh-keygen` 不带任何参数
2. **SSH 首次连接必须输 `yes` 不是 `y`**：输入 `y` 会反复报错
3. **`~/storage/shared/` 不链接到手机存储**：必须先跑 `termux-setup-storage` 授权。如果弹出"管理所有文件"设置页，找到 Termux → 允许
4. **判断 storage 是否生效**：跑 `realpath ~/storage/shared`，应该是 `/storage/emulated/0`，不是 `/data/data/com.termux/files/home/storage/shared`
5. **storage 没有正确链接**：先到系统设置确认 Termux 的文件访问权限，再重新执行 `termux-setup-storage`；不要在未盘点现有内容时递归删除 `~/storage`
6. **Obsidian 打开的路径是 `/storage/emulated/0/xxx`**，不是 `~/storage/shared/xxx`
7. **5G 外网连不上内网 NAS**：必须同 WiFi 局域网或使用受控 VPN
8. **clone 顺序**：先 `termux-setup-storage` 再 clone，否则文件在 Termux 私有目录里，Obsidian 读不到
9. **Graph 仍有运行报告节点**：先应用并检查仓库的版本化 policy；缓存残留时在 Obsidian 命令面板执行 `Rebuild vault cache`，不要把它输入 Termux
10. **`termux-setup-storage` 闪退**：安卓高版本需要先在系统设置里开权限再跑命令。顺序：设置→应用→Termux→权限→所有文件访问权限→允许，然后再跑 `termux-setup-storage`

## 远程同步方案（内网 IP 不可用时）

### Tailscale（推荐，最省心）
- NAS 和手机都装 Tailscale
- 自动虚拟组网，无需公网 IP、无需改路由器
- 免费版最多 100 台设备
- 装完后 Git 地址不用改（用 Tailscale 分配的 IP）

### Cloudflare Tunnel
- NAS 装 cloudflared，暴露 SSH 服务
- 手机装 Cloudflare WARP 客户端连接
- 走 Cloudflare 网络，安全性好
- 需要有 Cloudflare 账号和域名

### Zero Tier
- 类似 Tailscale，配置稍复杂
- 免费
