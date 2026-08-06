# lynch5mo Agent Skills

这是 lynch5mo 全部自建 Agent Skill 的公开分发仓库。当前收录 20 个 Skill，分为核心业务、专项辅助、设备与运维三组。每个 Skill 都可以独立安装，适合 Codex、Claude Code、Hermes，以及能够从 GitHub 读取 `SKILL.md` 的其他 Agent。

## 核心业务 Skills

| Skill | 主要用途 |
|---|---|
| `agent-kb-workflow` | Agent-KB 摄入、编译、检索、学习管理，以及 Codex/Claude/Hermes 跨设备实例报告收口 |
| `use-alpha-ficc-terminal` | Alpha-FICC 金融终端、当前图表上下文、图表数据、推图、标注和 V4/V5 Research OS |
| `film-skill` | Agent-KB 剧本项目、Scrivener 导入导出、分场审计、格式检查和受控改稿 |

`agent-kb-workflow` 同时承担知识库学习工作流；课程/阅读管理不是一套相互竞争的独立主 Skill。

## 专项辅助 Skills

| Skill | 主要用途 |
|---|---|
| `course-series-translation` | 按既有中文课程风格翻译后续课时 |
| `knowledge-base-to-article` | 把知识库研究和讨论整理为面向人的正式文章 |
| `pay-peng-video-transcription` | 付鹏系列音视频 Whisper 转写与 Markdown 整理 |
| `pdf-to-markdown-conversion` | PDF 文本与图片转换为 Markdown |
| `large-doc-chapter-split` | 超大 Markdown 文档的章节拆分、目录和交叉链接 |
| `boe-paper-download` | 英格兰银行 Quarterly Bulletin 和论文下载 |
| `alpha-ficc-hermes-testing` | Alpha-FICC V1–V5、图表标注和 Research OS 专项验收 |
| `fupeng-models-charting` | 付鹏核心研究模型的旧版直接数据绘图工作流 |

`fupeng-models-charting` 属于历史辅助路线；当前受治理的金融终端操作优先使用 `use-alpha-ficc-terminal`。

## 设备与运维 Skills

| Skill | 目标系统与主要用途 |
|---|---|
| `ubuntu5-cloudflare-copyparty-recovery` | Ubuntu5、Cloudflare 530/1033、Tunnel 与 Copyparty 上传排障 |
| `nas-management` | TrueNAS、Synology、SMB、NAS Git、恢复、同步和安全文件操作 |
| `movie-library-controlled-ops` | NAS 个人电影库扫描、决策包、重复隔离、回滚与核验 |
| `media-library-inventory` | 本地/NAS 媒体盘点、sidecar 分类、目录重叠与重复报告 |
| `android-obsidian-self-hosted-git` | Android、Termux、Obsidian 复用同一 Vault、直接 Git、设备绑定与图谱策略 |
| `android-termux-development` | Termux 软件安装、Python 包兼容、进程与 APK 管理 |
| `hermes-desktop-troubleshooting` | macOS Hermes Desktop Electron/backend 启动与连接排障 |
| `multi-runtime-skill-install` | Codex、Claude、OpenCode、Hermes 多运行时安装 |
| `codex-claude-skill-install` | Codex 与 Claude Code 双端安装 |

## 安全边界

公开仓库只包含 Skill 指令、references、scripts、templates 和可安装包，不包含：

- 密码、token、私钥、cookies 或认证文件；
- NAS、服务器、终端或知识库中的用户数据；
- 电影、课程、书籍、视频或音频正文；
- Agent 对话、运行日志、数据库或备份；
- 本机 `.env`、SSH 配置或 secret store。

这些 Skill 面向 lynch5mo 的工作流和设备拓扑。安装后的 Agent 必须核对主机、路径、挂载、容器、API 版本和凭证位置，不得把文档中的历史值当作当前事实。认证信息只能由本机私密配置提供。

## 从 GitHub 安装单个 Skill

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

如果 Hermes 使用独立 profile，则复制到该 profile 的 `skills/<skill-name>/`。安装后启动新会话，让 Agent 重新加载 Skill metadata。

## `.skill` 安装包

每个 Skill 都在 `dist/` 下提供独立安装包：

```text
dist/<skill-name>.skill
```

支持 `.skill` 导入的 Agent 可以直接下载对应文件。压缩包内包含一个以 Skill 名命名的顶层目录，以及该 Skill 所需的 references、scripts 和 templates。

## 让 Agent 自行安装

```text
从 https://github.com/lynch5mo/agent-skills 安装 skills/<skill-name>。
先读取仓库 README 和目标 SKILL.md，按当前 Agent 的原生 Skills 目录安装完整目录；
不要读取、复制或输出任何本机认证信息，安装后验证 SKILL.md 及配套 references/scripts 可发现。
```

## 更新

更新仓库后，用新的完整 Skill 目录替换旧目录。不要只复制 `SKILL.md`；`references/`、`scripts/`、`templates/` 和 `agents/` 必须一起更新。

完整清单与版本见 [`manifest.json`](manifest.json)。
