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
1. Update .claude/projects/-Users-simonb-SIP-Code/memory/MEMORY.md often, after an important step is done, with concise and condensed context. Also update the gsd files like ROADMAP.md. Do not include more than what is strictly necessary to pick off from. This should be done so claude can pick off if a rate limit is hit mid-session. 
2. Any important change in the codebase, file structure, or project functionality that is essential to understanding and operating the project has to be written to README.MD. You must be concise and follow the format already given. All CLI commands and changes should be logged here. 
3. The project must work both on Windows and Mac OS. Mac OS is the main development platform where everything will be tested, but Windows is where it will be deployed for testing. Later deployment, the cloud will be done on a Linux-based server. 
