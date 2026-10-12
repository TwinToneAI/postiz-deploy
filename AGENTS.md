# AGENTS.md

Operating rules for AI agents (Codex, Cursor, Copilot, Claude Code, Hermes) working in this repo. A nested `AGENTS.md` deeper in the tree overrides this file.

## Linear ticket discipline (NON-NEGOTIABLE)
Every branch, commit, and PR references its Linear ticket.
- Branch: `james/<TICKET-ID>-<slug>`
- PR title must contain `<TICKET-ID>`: `type(scope): TICKET-ID summary` (squash-merge turns the title into the commit message on `main`).
- PR body must contain `Closes <TICKET-ID>` (Linear auto-transitions on merge).
Accepted prefixes: `TWI2`, `VEN`, `SAL`, `MAR`, `CONSULT`, `RES`. Never reuse an unrelated ID to satisfy the format.

## Concurrency: one agent, one worktree
Several agents work this org. Work in your own git worktree + branch; never edit the primary checkout; never commit on another agent's branch. Stage by explicit path (`git add <path>`), never `git add -A`.

## Verify before claiming done
No "works / done / fixed / shipped" without the verifying command's fresh output in the same message. "Tests pass" needs runner output; "deployed" needs a live check; "fixed" needs the original failure reproduced and now passing. If you have not verified it, say so.

## Static analysis gate
`.github/workflows/static-analysis.yml` runs on PRs (advisory): `tsc --noEmit`, ESLint, **knip** (dead files/exports/deps), **jscpd** (copy-paste) for JS/TS; **Ruff**, **vulture** (dead code), **pip-audit** for Python; **gitleaks** for secrets. Read the job summary and fix findings rather than disabling the gate.

## Code style
- Prefer many small files over few large ones; 200-400 lines typical, 800 max. Functions under 50 lines, nesting under 4 levels.
- Handle errors explicitly at every level; never silently swallow (no empty `catch {}` / `except: pass`).
- Validate at system boundaries. No hardcoded secrets or environment-specific values.
- No `any` / `@ts-ignore` / `# noqa` without a stated reason. No leftover `console.log` / `debugger` / commented-out blocks.

## Commits & merges
Conventional commits: `type(scope): TICKET-ID summary`. Squash-merge; the PR title becomes the `main` commit message, so it must be self-contained.

## Development
- See repo README for build/run/test commands.
