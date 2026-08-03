---
name: android-obsidian-self-hosted-git
description: 连接安卓手机到自建 Git 服务器上的 Obsidian 知识库（Termux + SSH + Obsidian Git 插件）
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: knowledge-management
---

# 安卓连接自建 Git Obsidian 知识库

适用于：NAS 或私有服务器上托管的 Git 仓库 + 安卓手机 + Obsidian

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

### 8. Obsidian 打开仓库
- 选 **Open folder as vault**
- 路径：`/storage/emulated/0/<vault名>`

### 9. 安装 Obsidian Git 插件
- 设置 → 第三方插件 → 关安全模式 → 浏览 → 搜 **Obsidian Git** → 安装启用
- 插件设置：
  - Vault backup interval：10
  - Auto pull on startup：打开
  - Auto push on commit：打开

## 常见坑
1. **ssh-keygen 跑出帮助信息**：Termux 键盘输入可能有误（自动纠错、空格等）。用最简单的 `ssh-keygen` 不带任何参数
2. **SSH 首次连接必须输 `yes` 不是 `y`**：输入 `y` 会反复报错
3. **`~/storage/shared/` 不链接到手机存储**：必须先跑 `termux-setup-storage` 授权。如果弹出"管理所有文件"设置页，找到 Termux → 允许
4. **判断 storage 是否生效**：跑 `realpath ~/storage/shared`，应该是 `/storage/emulated/0`，不是 `/data/data/com.termux/files/home/storage/shared`
5. **storage 没有正确链接**：如果 `realpath` 显示的是 Termux 内部路径，且 `ls -la ~/storage/` 里 `shared` 没有 `->` 箭头，说明链接失败。修复方法：先删再重建
   ```bash
   rm -rf ~/storage
   termux-setup-storage
   ```
   删除前如有已 clone 的仓库，先删仓库避免重复占用空间。如果 `termux-setup-storage` 运行时闪退，去 设置→应用→Termux→权限→所有文件访问权限 确认为允许状态，再重试
5. **Obsidian 打开的路径是 `/storage/emulated/0/xxx`**，不是 `~/storage/shared/xxx`
6. **5G 外网连不上内网 NAS**：必须同 WiFi 局域网
7. **clone 顺序**：先 `termux-setup-storage` 再 clone，否则文件在 Termux 私有目录里，Obsidian 读不到
8. **Graph 视图孤立节点太多**：`.obsidian/graph.json` 的设置（如 `showOrphans: false`）可能没完全生效。手动修复：打开 Graph → ⚙️ → 筛选 → 关掉「孤立文件」开关 → 搜索框输入 `path:"wiki/"` 过滤
9. **`termux-setup-storage` 闪退**：安卓高版本需要先在系统设置里开权限再跑命令。顺序：设置→应用→Termux→权限→所有文件访问权限→允许，然后再跑 `termux-setup-storage`

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
