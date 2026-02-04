# Handoff H113 — End-to-end docs restored + gated (avoid missing-doc drift)

## Summary (1–3 sentences)

Ensured the “end-to-end” planning docs referenced by tasks (`docs/end_to_end_*`) are treated as first-class repo artifacts: removed their ignore rules and made `make gate` fail if they are missing. This prevents workers from improvising around missing context during full-scale swarm runs.

## What changed / what exists now

- Files/paths:
  - `.gitignore`: no longer ignores `docs/end_to_end_research_plan.md` and `docs/end_to_end_data_collection_plan.md`.
  - `scripts/quality_gates.py`: `gate_repo_structure` now requires:
    - `docs/end_to_end_data_collection_plan.md`
    - `docs/end_to_end_research_plan.md`
- Outputs produced:
  - No new data artifacts; this is documentation availability + guardrail only.

## How to reproduce / verify

- Commands:
  - `make gate`
- Expected results:
  - `[repo_structure] ok=True ...` when the docs exist.
  - If either end-to-end doc is deleted from HEAD, `make gate` fails with a `repo_structure` missing-path entry.

## Assumptions / risks

- Assumes the repo posture is that `docs/end_to_end_*` are foundational planning docs (per the direction-change note in `.orchestrator/blocked/T070_remove_internal_docs_from_repo_head.md`).

## Open questions / next steps

- If the public-release posture changes (i.e., you truly want these docs absent from HEAD), update tasks (T080/T094/T095) to reference only `docs/protocol.md` + `contracts/*` and remove these docs from the repo-structure gate.
