# lynch5mo Agent Skills

这是个人 Agent Skills 分发仓库，用于在桌面或手机 Agent 中安装同一套工作流。

仓库当前包含：

- `agent-kb-workflow`：Agent-KB 的完整使用流程，包括通用 ingest、PDF 与系列编译、课程学习、书籍阅读、英文材料中文预处理、弹性学习进度、暂停恢复、对话整理和知识晋升。

## 隐私边界

本仓库只包含 Skill 指令、references 和测试提示，不包含：

- Agent-KB 知识正文；
- 课程、书籍、视频或音频；
- 用户与 Agent 的对话；
- token、密码、密钥或认证文件；
- NAS 中的原始材料。

## 手机 Agent 安装

在支持从 GitHub 仓库安装 Skills 的 Agent 中：

1. 添加公开仓库：

```text
https://github.com/lynch5mo/agent-skills
```

2. 选择 Skill 路径：

```text
skills/agent-kb-workflow
```

3. 确认安装后的 Skill 名称仍为：

```text
agent-kb-workflow
```

不同手机 Agent 的安装按钮名称可能不同，但应选择“从 GitHub”“Repository Skill”或同义入口，并填写以上仓库与目录。

如果手机 Agent 支持上传 `.skill` 安装包，也可以下载：

```text
dist/agent-kb-workflow.skill
```

## Git 安装

```bash
git clone https://github.com/lynch5mo/agent-skills.git
```

然后把 `skills/agent-kb-workflow` 复制到 Agent 的 Skills 目录。

常见目标：

```text
Codex:  ~/.codex/skills/agent-kb-workflow
Claude: ~/.claude/skills/agent-kb-workflow
Hermes: ~/.hermes/profiles/codex/skills/agent-kb-workflow
```

安装后重新启动 Agent 会话，使 Skill metadata 重新加载。

## 更新

仓库更新后重新拉取，并用新的 `skills/agent-kb-workflow` 目录替换旧版本。不要只复制 `SKILL.md`；`references/` 也是执行流程的一部分。

## 版本

当前版本见根目录 `manifest.json` 和 Skill 的 `SKILL.md` frontmatter。
