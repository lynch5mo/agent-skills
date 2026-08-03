---
name: codex-claude-skill-install
description: 安装 GitHub skill/plugin 仓库到 Codex 和 Claude Code。适用于“把这个 skills 安装一下”“Claude Code 也装上”这类请求，需要先判断 repo 是 plain skills、Codex `.codex/` 集成，还是 Claude marketplace/plugin。
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  argument_hint: "[repo-or-path]"
---

# Codex + Claude skill install

## When to use

- 用户给一个 GitHub skills/plugin 仓库，要求直接安装。
- 用户明确要同时装到 Codex 和 Claude Code。
- 需要判断 repo 原生结构，避免把 marketplace、plain skills、hooks 混为一谈。

不要用于：

- 只做文档说明、不需要实际落盘安装。
- 单个普通项目依赖安装，不涉及 skills/plugin 结构。

## Inputs / context to gather

1. repo 里有没有这些入口：
   - `skills/*/SKILL.md`
   - `.codex/skills/`
   - `.codex/hooks/`
   - `.claude-plugin/` 或 `.plugin/plugin.json`
2. 本机目标位置：
   - `~/.codex/skills`
   - `~/.codex/hooks`
   - `~/.codex/hooks.json`
   - `~/.codex/config.toml`
   - `~/.claude/plugins/marketplaces`
   - `~/.claude/skills`
3. 是否需要 name prefix 以避免与现有技能冲突。

## Procedure

1. 先判 repo 类型，不要直接复制。
   - plain skills repo：主要看 `skills/*`
   - Codex-native repo：优先看 `.codex/skills` / `.codex/hooks`
   - Claude marketplace/plugin：看 `.claude-plugin/` 或 `.plugin/plugin.json`
2. Codex 安装策略。
   - plain `skills/*`：按 repo 来源加前缀后复制到 `~/.codex/skills`
   - 原生 `.codex/skills`：直接保留 repo-native 结构
   - 如有 `.codex/hooks`：合并到现有 hooks，不覆盖用户已有项
3. Claude Code 安装策略。
   - 有 marketplace/plugin 元数据：复制到 `~/.claude/plugins/marketplaces/<name>`
   - 只有 plain skills：复制到 `~/.claude/skills/<skill-name>`
   - 不要伪造 marketplace 注册
4. 若 repo 同时支持两端，分别按各自原生方式安装，不强行统一成一种格式。
5. 做最小验证。
   - 检查目标 `SKILL.md` / `plugin.json` / `marketplace.json` 是否存在
   - 若改了 JSON/TOML，确认能被解析

## Efficiency plan

1. 每个 repo 单独处理；安装器 wrapper 不稳定时，不要把多个 repo 混成一次调用。
2. 先 `find`/`rg` repo 结构，再决定复制路径，避免反复返工。
3. 只在 repo 自带 `.codex/` 集成时处理 hooks/config；plain skills repo 不要额外发明集成层。

## Pitfalls and fixes

- 症状：多 repo 一次性安装脚本很吵或失败
  - 原因：wrapper/temp path 冲突
  - 修复：改成一 repo 一次，必要时直接 copy/rsync
- 症状：Claude 端找不到插件
  - 原因：把 plain skills 当 marketplace
  - 修复：无 plugin metadata 时装到 `~/.claude/skills`
- 症状：本机已有 skill 被覆盖或重名
  - 原因：没做 repo 前缀或没检查现有目录
  - 修复：Codex 侧优先做 repo 来源前缀
- 症状：hooks 安装后破坏原有配置
  - 原因：直接覆盖 `hooks.json` 或漏开 `hooks = true`
  - 修复：合并 hooks，保留现有配置，并核对 `~/.codex/config.toml`

## Verification checklist

- 已确认 repo 属于 plain skills、Codex-native、Claude marketplace 中的哪一类。
- Codex 侧目标技能都存在，且未无意覆盖同名旧技能。
- Claude 侧按真实 repo 结构落盘，没有伪造 marketplace。
- 若改了 hooks/JSON/TOML，已做解析或存在性验证。
