# Handoff H127 — Swarm Framework Postmortem + Fullscale Roadmap (2026-02-10)

## Summary (1-3 sentences)

The swarm runner executed primarily **sample-mode** tasks and then became idle with `ready: []` because there are currently **no tasks with `State: backlog`** (folder `backlog/` is not the source of truth). The larger blocker for true end-to-end fullscale autonomy is structural: **isolated git worktrees cannot share untracked `data/processed/` artifacts**, and the judge currently allows tasks to be marked `done` without verifying required fullscale outputs.

This handoff documents root causes and proposes a robust BigQuery-backed shared artifact plane plus governance and judge tightening.

## Where We Are Now

### Control-plane state

- `python scripts/swarm.py plan` reports:
  - `ready: []`
  - all current tasks in `.orchestrator/backlog/` are `State: done`
  - only blocked tasks are in `.orchestrator/blocked/`:
    - `T070` (explicit `@human` direction change)
    - `T087` (deprecated/superseded by split tasks `T087A/B/C`)

### Repo outputs

- Recent merged work produced and committed sample-mode analysis artifacts (examples):
  - `reports/figures/rent_decomposition_sample.svg`
  - `reports/tables/rent_decomposition_sample.csv`
  - `reports/figures/blob_floor_binding_str_link_sample.svg`
  - `reports/tables/blob_floor_binding_str_link_sample.csv`
  - `reports/figures/burn_vs_issuance_sample.svg`
  - `reports/tables/burn_vs_issuance_sample.csv`

- Repo QC passes on `main`:
  - `make gate`
  - `make test`

### BigQuery environment

- Auth is working via CLI/OAuth sessions (no API keys committed).
- Default gcloud project observed: `l2-l1-causal-analysis`.
- Existing datasets present, including `eth_scaling_mart`.
- Existing artifact registry table observed: `eth_scaling_mart.artifact_manifest_v1`.

## What Happened (Root Causes)

### 1) “Why did it only run sample-mode?”

This was driven by task design and current system constraints:

- Many tasks are explicitly sample-mode tasks (by filename and by success criteria). Their scripts default to committed fixtures (`data/samples/...`) unless a full panel path is provided.
- Sample-mode is currently the only path that is:
  - deterministic,
  - CI-friendly,
  - PR-mergeable,
  - and does not require a shared data plane.

Fullscale tasks exist conceptually, but fullscale inputs are not reliably present across isolated worktrees (see the next root cause).

### 2) “Why is there backlog in the backlog folder but ready is empty?”

This is a control-plane semantics mismatch:

- `scripts/swarm.py` schedules tasks based on the **`State:` field** inside task files.
- It only considers tasks located in `.orchestrator/backlog/` whose `State: backlog` and dependencies are satisfied.
- The folder name is not authoritative. If a task remains physically in `.orchestrator/backlog/` but has `State: done`, it is not runnable.

Planner sweep (`python scripts/sweep_tasks.py`) is the intended mechanism to keep folder locations aligned with `State:`. If sweeps do not run, humans will misread the backlog folder as “pending work”.

### 3) “Fullscale cannot chain across worktrees” (most critical)

The framework currently uses isolated git worktrees per task, which is correct for safety and parallelism. However:

- Untracked outputs under `data/processed/` and `data/raw/` produced in one worktree are not visible in another worktree.
- Many fullscale steps expect those untracked artifacts to exist locally (e.g., panel builders reading `data/processed/...`), but in practice they are missing in downstream worktrees.

This means fullscale ETL -> panel -> analysis cannot compose unattended unless there is a shared artifact plane.

### 4) “Done semantics are too weak”

The judge currently promotes tasks to `done` when:
- gates pass (`make gate`, optionally `make test`), and
- path ownership is respected.

It does not enforce:
- task stop_conditions,
- “required outputs exist”,
- “full vs sample mode completion”,
- or downstream reproducibility checks.

This can lead to tasks being marked `done` even when Notes mention missing fullscale inputs/outputs. That makes the dependency graph look satisfied while fullscale artifacts do not exist.

### 5) Planner does not generate tasks

The current planner is a selector (heuristic or Claude) over existing tasks. It does not:
- create new tasks from the research plan,
- detect missing milestones and instantiate tasks,
- or maintain a long-horizon roadmap automatically.

So once the pre-authored backlog is exhausted, the system naturally stops.

## Why BigQuery Is The Right Shared Data Plane (and the cautions)

BigQuery is a strong choice for shared artifacts in this repo because:

- It is already authenticated and available in unattended mode via CLI/OAuth.
- It supports large-scale aggregation without exporting raw tx-level data to local disk.
- It can serve as the cross-worktree “shared memory” for derived datasets.

Cautions (must design around):

- BigQuery is not inherently append-only unless you enforce it. Overwrites can destroy reproducibility.
- Time travel is limited. Long-term reproducibility requires snapshot/version conventions.
- Raw tx/receipt level storage can become expensive. Prefer querying public datasets directly and storing only curated daily aggregates/panels.

## Proposed Enhancements (Remedies)

### A) Introduce an explicit artifact plane with an artifact registry

Use BigQuery as the canonical store for fullscale artifacts and keep the repo as:
- protocol/contracts/registry source of truth,
- code,
- and small deterministic sample fixtures + figures.

Recommended approach:

1. Define artifact names and expected schemas.
   - Example artifacts:
     - `rollup_costs_daily_v1`
     - `rollup_costs_decomposition_daily_v1`
     - `vendor_l2_fees_daily`
     - `daily_rollup_panel_v1`
     - `daily_rollup_panel_v2`

2. Publish artifacts to BigQuery with versioning.
   - Prefer partitioned tables keyed by `as_of_date` or `run_id` rather than overwriting.
   - Version id should include at least: `as_of` date and git SHA.

3. Register artifacts in a single manifest table.
   - You already have `eth_scaling_mart.artifact_manifest_v1`. Reuse it.
   - Each publish writes a manifest row:
     - `artifact_name`, `version_id`, `storage_uri` (bq table), `min_date`, `max_date`, `dependencies`, `source_tables`, etc.

4. Downstream tasks resolve inputs from the artifact registry, not from `data/processed/...`.
   - Worktrees stay isolated but can all read the same BigQuery artifacts.

### B) Split sample tasks vs fullscale tasks (or add a formal `mode`)

To avoid ambiguous completion:

- Split tasks into:
  - `*_sample` tasks whose outputs are committed artifacts for CI.
  - `*_full` tasks whose outputs are BigQuery artifacts + small committed report outputs (figures/tables) only.

Alternative: add a required frontmatter `mode: sample|full` and enforce mode in the judge.

### C) Tighten judge semantics: outputs and stop conditions

Make `done` mean “the intended artifact exists”. Concretely:

- Verify declared `outputs:` exist.
  - For BigQuery outputs, outputs can be expressed as `bq://project.dataset.table` (new convention) and validated with `bq show`.
- Enforce stop_conditions:
  - If a stop condition is hit (e.g. missing fullscale inputs), the judge must set `State: blocked`.

This is the key fix to prevent a “green” graph that is missing fullscale deliverables.

### D) Integrate Planner sweep into unattended loop

To align human expectations:

- Add a periodic “Planner maintenance tick” that runs `scripts/sweep_tasks.py` and submits a PR.
- Auto-merge that PR (if checks pass).

This makes `.orchestrator/backlog/` reflect actual pending work and reduces operator confusion.

### E) Make network permission explicit per task

Current network rule is coarse: only W1/W2 get Codex sandbox network access.

To support BigQuery-backed fullscale runs cleanly:

- Add frontmatter: `allow_network: true` (or `required_tools: [bq]`).
- `scripts/swarm.py` should enable Codex network access only when the task declares it.

### F) Add a real planning loop (beyond selecting existing tasks)

Two staged approaches:

1. Deterministic milestone planner (safer v1)
   - A script reads required end-to-end milestones (artifact registry + report catalog) and ensures tasks exist.
   - It creates missing tasks from templates with deterministic content.

2. LLM-based task author (v2)
   - Claude generates task files based on gaps; must be gated by schema validation + ownership rules, and ideally staged behind `ready_for_review`.

## Concrete Next Steps (Minimal Path to True Fullscale)

1. Add an `artifact plane` contract:
   - Decide on BigQuery dataset(s) to use for this project’s fullscale artifacts (recommend a dedicated dataset or reuse `eth_scaling_mart` with distinct artifact_name prefix).
   - Decide snapshot/version conventions.

2. Implement publish/resolve utilities (W8 Ops/Automation):
   - `scripts/bq_artifacts.py publish` (load local CSV/Parquet to BQ + insert manifest row)
   - `scripts/bq_artifacts.py resolve` (given artifact_name and version policy -> bq table reference)

3. Refactor fullscale ETL tasks to publish outputs to BigQuery rather than local `data/processed`.
   - Start with `src/etl/l1_rollup_costs_bigquery.py` (already uses BQ for compute) and add optional `--publish` to store outputs in BQ.

4. Tighten the judge and task semantics (W8):
   - enforce outputs exist
   - enforce stop_conditions
   - formalize sample vs full

5. Make sweep automatic in unattended mode (W8).

## Assumptions / Risks

- Assumes BigQuery billing and quotas are acceptable for multi-year daily extraction.
- Assumes dataset locations match (US vs EU). Current datasets appear US.
- If BigQuery public Ethereum tables are missing blob receipt fields for some windows, you must fall back to RPC for those windows. The existing script already probes and fails fast.

## Reproduction / Verification Commands

- Current readiness snapshot:
  - `python scripts/swarm.py plan`
  - `python scripts/sweep_tasks.py --dry-run`

- Repo gates:
  - `make gate`
  - `make test`

- BigQuery inventory:
  - `gcloud config get-value project`
  - `bq ls` (datasets)
  - `bq show eth_scaling_mart.artifact_manifest_v1`
