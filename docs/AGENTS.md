# docs/AGENTS.md — Documentation Rules

Docs are research-critical. Do not rewrite aggressively.

## Protocol lock is sacred

- `docs/protocol.md` defines canonical metrics, units, regimes, inclusion criteria.
- Only edit protocol if your task is explicitly W0 and authorizes it.
- If protocol changes are authorized, update any duplicated rules in prompts/runbooks to keep docs consistent.

## Editing style

- Prefer minimal diffs.
- Preserve headings and structure.
- When adding a definition or rule, make it testable and unambiguous.
- Prefer short action-oriented bullets.

## Evidence discipline

If you add a factual claim that matters for measurement (e.g., upgrade date, fee semantics):
- add a short citation line or link in the doc
- record it in the task `Notes / Decisions` if it affects results

## Link/index hygiene

- Keep internal links valid (prefer repo-relative links).
- If you add/rename/remove a docs page, update related indexes/README pages that reference it.

## Procedure changes

- When changing operational procedures, include a clear before/after summary and reproduction commands.

## No scope creep

Do not expand the research plan unless explicitly assigned.
