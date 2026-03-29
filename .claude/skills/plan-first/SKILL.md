---
name: plan-first
description: >-
  Produces a short implementation plan before edits for KashiwaaS. Use when the
  task is non-trivial (multi-file, behavior/config/bot/hooks/CI changes), or
  when the user asks for a plan, design review, or approval gate. Skips a formal
  plan only for trivial fixes (typos, comments, obvious nits).
---

# Plan-first (KashiwaaS)

## When to use

- New feature or refactor touching more than one file
- Behavior, config, `.claude` hooks (see `.cursor/hooks.json`), CI, or `@kashiwaas` bot changes
- User asked for a plan or said to wait for approval before coding

## When to skip a formal plan

- Single obvious typo, comment-only, or trivial nit from review

## Rules

1. Output a plan **before** any file edits; wait for user approval unless they already approved in the same turn.
2. If unclear, ask **at most 1–2** questions, then proceed with stated assumptions.
3. After approval, implement and run `make` / `pytest` as in [AGENTS.md](../../../AGENTS.md).

## Output format

Use [plan-template.md](plan-template.md). Sections:

- Goal
- Scope (in / out)
- Files to touch
- Verification (`make test`, `make lint`, CI dry-run if relevant)
- Risks and rollback

Optional: save a copy under `.cursor/plans/` (gitignored) for your own session.

## Project pointers

- Commands: [AGENTS.md](../../../AGENTS.md)
- Design index: [docs/README.md](../../../docs/README.md)
