# lynch5mo Agent Skills

这是 lynch5mo 自建设备、服务和工作流 Skill 的公开分发仓库。每个 Skill 都可以独立安装，适合 Codex、Claude Code、Hermes，以及能够从 GitHub 读取 `SKILL.md` 的其他 Agent。

## 自建设备与运维 Skills

| Skill | 目标系统 | 主要用途 |
|---|---|---|
| `ubuntu5-cloudflare-copyparty-recovery` | Ubuntu5、Cloudflare、Copyparty | 530/1033、Tunnel、上传稳定性与吞吐排障 |
| `nas-management` | TrueNAS、Synology、SMB、NAS Git | 文件恢复、同步、Git 维护、媒体盘点与安全操作 |
| `movie-library-controlled-ops` | NAS 个人电影库 | 只读扫描、决策包、精确重复规划、隔离、回滚与核验 |
| `media-library-inventory` | 本地/NAS 媒体目录 | 大规模文件盘点、sidecar 分类、重叠与重复候选报告 |
| `android-obsidian-self-hosted-git` | Android、Termux、Obsidian、自建 Git | 安卓手机接入自托管 Obsidian 知识库 |
| `android-termux-development` | Android、Termux | 软件安装、Python 包兼容、进程与 APK 管理 |
| `hermes-desktop-troubleshooting` | macOS、Hermes Desktop | Electron/backend 启动、连接和版本不匹配排障 |
| `multi-runtime-skill-install` | Codex、Claude、OpenCode、Hermes | 按各运行时原生方式安装同一 Skill/plugin 仓库 |
| `codex-claude-skill-install` | Codex、Claude Code | Codex 与 Claude 双端 Skill/plugin 安装 |

仓库还保留已有的 `agent-kb-workflow`，用于 Agent-KB 管理与学习工作流；它不是设备运维 Skill。

## 安全边界

公开仓库只包含 Skill 指令、references 和可安装包，不包含：

- 密码、token、私钥、cookies 或认证文件；
- NAS、服务器或设备上的用户数据；
- 电影、课程、书籍、视频或音频正文；
- Agent 对话、运行日志或备份；
- 本机 `.env`、SSH 配置或 secret store。

这些 Skill 面向 lynch5mo 的设备拓扑。安装后的 Agent 必须先核对主机、路径、挂载、容器和凭证位置，不得把文档中的历史值当作当前事实。认证信息只能由本机私密配置提供。

## 从 GitHub 安装单个 Skill

先克隆仓库：

```bash
git clone --depth 1 https://github.com/lynch5mo/agent-skills.git
cd agent-skills
```

将 `<skill-name>` 替换为上表中的名称。

### Codex

```bash
mkdir -p "$HOME/.codex/skills/<skill-name>"
cp -R "skills/<skill-name>/." "$HOME/.codex/skills/<skill-name>/"
```

### Claude Code

```bash
mkdir -p "$HOME/.claude/skills/<skill-name>"
cp -R "skills/<skill-name>/." "$HOME/.claude/skills/<skill-name>/"
```

### Hermes

```bash
mkdir -p "$HOME/.hermes/skills/<skill-name>"
cp -R "skills/<skill-name>/." "$HOME/.hermes/skills/<skill-name>/"
```

如果 Hermes 使用独立 profile，则复制到该 profile 的 `skills/<skill-name>/`。安装完成后启动新会话，让 Agent 重新加载 Skill metadata。

## `.skill` 安装包

每个 Skill 都在 `dist/` 下提供独立安装包：

```text
dist/<skill-name>.skill
```

支持 `.skill` 导入的 Agent 可以直接下载对应文件。压缩包内包含一个以 Skill 名命名的顶层目录。

## 让 Agent 自行安装

可以直接向 Agent 提供以下指令：

```text
从 https://github.com/lynch5mo/agent-skills 安装 skills/<skill-name>。
先读取该仓库 README 和目标 SKILL.md，按当前 Agent 的原生 Skills 目录安装；
不要读取、复制或输出任何本机认证信息，安装后验证 SKILL.md 可发现。
```

## 更新

更新仓库后，用新的完整 Skill 目录替换旧目录。不要只复制 `SKILL.md`；如果 Skill 带有 `references/`、`scripts/` 或 `templates/`，必须一起更新。

仓库清单与版本见 [`manifest.json`](manifest.json)。
