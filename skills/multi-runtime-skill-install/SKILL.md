---
name: multi-runtime-skill-install
description: 安装同一个 GitHub skills/plugin 仓库到多个本机 agent/runtime。适用于“把这个给自己装上”“Claude Code 也装上”“还有 hermes agent”这类请求，需要按 repo 原生文档分别处理 Codex、Claude Code、OpenCode、Hermes。
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  argument_hint: "[repo-or-path]"
---

# Multi-runtime skill install

## When to use

- 用户给一个 skills/plugin repo，并希望直接安装而不是只看说明。
- 同一个 repo 要覆盖多个 runtime，例如 Codex、Claude Code、OpenCode、Hermes。
- 需要先判断 repo 对每个 runtime 的原生支持边界，避免发明 adapter。

不要用于：

- 只涉及 Codex + Claude Code，且已有成熟路径时；那种场景优先用 `skills/codex-claude-skill-install/SKILL.md`。
- 只做 repo 评估，不需要实际落盘。

## Inputs / context to gather

1. repo 文档和结构：
   - `README*`
   - `skills/*/SKILL.md`
   - `.claude-plugin/`、`.plugin/plugin.json`
   - `.opencode/` 或 OpenCode 说明
2. 本机目标路径：
   - `~/.codex/skills`
   - `~/.claude/plugins/marketplaces`
   - `~/.claude/skills`
   - `~/.opencode/skills`
   - `~/.hermes/skills`
   - `~/.hermes/config.yaml`
3. 用户点名了哪些 runtime，哪些是可以顺手继续覆盖的兼容 runtime。

## Procedure

1. 先判 repo 对各 runtime 的真实支持，不要直接复制。
   - Codex：看是 plain `skills/*` 还是 `.codex/` 原生集成。
   - Claude Code：看 marketplace/plugin metadata 或 plain skills。
   - OpenCode：看 README 是否明确说明 clone/copy 路径，或 repo 是否自带 `.opencode/`。
   - Hermes：先看 repo 是否有专用 adapter；没有的话，再判断是否能按 generic `SKILL.md` 目录安装到 `~/.hermes/skills`。
2. 为每个 documented runtime 选 repo-native 落盘方式。
   - 不同 runtime 各自独立处理，不强行统一格式。
   - OpenCode 若文档要求 clone 整个 repo，就不要只 copy 内层 `skills/`。
   - Hermes 若走 generic skills tree，可用一个分类目录承载同组技能。
3. 只安装已验证支持的 runtime。
   - 用户没明确点名，但 repo 明显支持且任务语境是“给自己装上”时，可继续覆盖同机兼容 runtime。
   - repo 没有文档、没有 adapter、没有原生入口的 runtime，停在 compatibility boundary。
4. 做最小验证。
   - 目标 `SKILL.md` / `plugin.json` / README 指向的关键文件存在。
   - Hermes 侧确认 `~/.hermes/config.yaml` 的 skills 配置不会把新目录排除掉。
   - OpenCode 侧确认路径符合 repo 文档，不额外引入 `opencode.json` 改动，除非 repo 明说需要。

## Efficiency plan

1. 先读 repo 文档和目录树，再决定 runtime 覆盖面，避免边装边返工。
2. 按 runtime 建一个简短矩阵：documented / generic-skills-ok / unsupported。
3. 复用已有技能安装 skill 或已有本地路径认知，不重复探测无关配置。
4. 一旦发现某 runtime 缺乏原生支持，立即停止在该 runtime 的探索。

## Pitfalls and fixes

- 症状：想把一个 repo 的安装套路原样搬到所有 runtime
  - 原因：忽略了 repo 的 host-specific docs
  - 修复：先读 README 和 metadata，把每个 runtime 单独分类
- 症状：OpenCode 装完却找不到技能
  - 原因：repo 文档要求 clone 全 repo，但只复制了 `skills/`
  - 修复：按 README 的完整路径重装到 `~/.opencode/skills/<repo>`
- 症状：Hermes 安装时想补写不存在的 plugin 层
  - 原因：把 generic `SKILL.md` skills 和 plugin runtime 混淆
  - 修复：repo 无 Hermes adapter 时，直接落到 `~/.hermes/skills`
- 症状：不同 agent 的 token/config 被混用
  - 原因：把多 runtime 安装当成共享配置
  - 修复：保持 `~/.codex`、`~/.claude`、`~/.opencode`、`~/.hermes` 各自隔离

## Verification checklist

- 已确认每个目标 runtime 是 documented、generic-skills-ok、还是 unsupported。
- 已按各 runtime 的原生路径落盘，没有发明额外 adapter。
- OpenCode / Hermes 如无明确要求，没有额外写入不必要的全局配置。
- 关键安装产物存在，且路径与 repo 文档一致。
