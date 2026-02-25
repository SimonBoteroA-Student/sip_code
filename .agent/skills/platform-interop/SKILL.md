---
name: Platform Interop (Claude Code ↔ Antigravity)
description: Resolve file/directory conflicts when switching between Claude Code CLI and Antigravity IDE. Use when /gsd: commands fail, `.planning/` files can't be found, `@` references don't resolve, or there's confusion about which config directory to read.
---

# Platform Interop Guide

This project alternates between **Claude Code** (terminal CLI) and **Antigravity** (IDE). Both must share state seamlessly.

## GSD Workflow Bridge

- GSD installed globally: `~/.claude/` (commands, agents, workflows, templates, references)
- Antigravity accesses GSD via **symlinks**: `.agent/workflows/gsd:*.md` → `~/.claude/commands/gsd/*.md`
- Both share **`.planning/`** for all GSD artifacts (PROJECT.md, ROADMAP.md, STATE.md, phases/)

### Resolving `@` References
GSD command files use `@./.claude/get-shit-done/...` paths. In Antigravity, resolve these to `~/.claude/get-shit-done/...`:
- Workflows: `~/.claude/get-shit-done/workflows/`
- References: `~/.claude/get-shit-done/references/`
- Templates: `~/.claude/get-shit-done/templates/`
- Agents: `~/.claude/agents/gsd-*.md`

### GSD Sub-Agents
Claude Code runs sub-agents via its Task tool. Antigravity should read agent files from `~/.claude/agents/` and follow instructions inline.

## Directory Mapping

| Path | Claude Code | Antigravity |
|---|---|---|
| `CLAUDE.md` | ✅ reads | ✅ reads |
| `.planning/` | ✅ reads/writes | ✅ reads/writes |
| `.claude/rules/` | ✅ reads | ❌ not seen |
| `.claude/commands/` | ✅ slash commands | ❌ use `.agent/workflows/` symlinks |
| `.agent/workflows/` | ❌ not seen | ✅ slash commands |
| `~/.claude/agents/` | ✅ Task tool | ❌ read manually |

## Fixing Broken Symlinks
After a GSD update, recreate symlinks:
```bash
for f in ~/.claude/commands/gsd/*.md; do ln -sf "$f" ".agent/workflows/gsd:$(basename "$f")"; done
```
