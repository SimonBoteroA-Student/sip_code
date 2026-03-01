# CLAUDE.md

## Project
Dual-platform project: Claude Code CLI + Antigravity IDE. GSD workflows available via `/gsd:*`.

## GSD
This project uses GSD workflows (`/gsd:*` commands) from `~/.claude/commands/gsd/`. Execute them by reading the referenced workflow files in `~/.claude/get-shit-done/workflows/` and following all instructions end-to-end.
When a GSD workflow requires parallel sub-agents (e.g., researchers, planners), prompt the user to spawn each as a separate fresh-context agent tab with a lighter model, providing the exact prompt and output file path for each, and appropriately connecting their output to the parent agent. 

## Claude in Antigravity
Read ~/.claude/projects/-Users-simonb-SIP-Code/memory/MEMORY.md

## Platform Note
If `/gsd:` commands, `@` references, or `.planning/` files don't work, read `.agent/skills/platform-interop/SKILL.md`.


## Rules 
1. Update .claude/projects/-Users-simonb-SIP-Code/memory/MEMORY.md often, after an important step is commited, with concise and condensed context. Do not include more than what is strictly necessary to pick off from. 
