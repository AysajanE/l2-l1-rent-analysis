**Meta-Block**

* **Scope:** (i) Review the current repo template + automation design (tasks/contracts/gates/swarm runner) for correctness and “runs unattended” reliability. (ii) Validate and tighten your proposed human kickstart procedure for truly continuous autonomous execution.
* **Confidence score:** 0.84 (high on what’s shown; medium on anything involving `scripts/sweep_tasks.py` behavior since its contents aren’t included here).
* **Perspective:** Ops/reliability + measurement discipline. Assume things will fail at 2am (auth, branch protection, tmux env, git divergence) and design so failures become *blocked tasks with crisp notes*, not silent stalls.

---

## 1) Is your human kickstart procedure basically correct?

**Yes — with the current `scripts/swarm.py` implementation, you almost certainly need BOTH loops**:

1. the **supervisor loop** that runs Worker+Judge on ready tasks, and
2. a **Planner sweep loop** that *moves task files by `State:`* so dependencies unblock.

Why: `done_task_ids()` only counts tasks that live under `.orchestrator/done/` *and* have `State: done`. A task that’s marked `State: done` but still sitting in `.orchestrator/backlog/` will **not** satisfy dependencies. So your “Planner sweep” is not optional; it’s a required part of autonomy *given the current code*.

That said, there are a few **real landmines / missing steps** in your procedure that will otherwise cause “silent stall” or inconsistent state.

---

## 2) What you’re missing / what I would change in the kickstart procedure (P0 issues)

### P0-A) tmux environment propagation for `SWARM_UNATTENDED_I_UNDERSTAND`

Your `export SWARM_UNATTENDED_I_UNDERSTAND=1` in the launching shell may **not** reliably propagate into the tmux “supervisor” window in all tmux/server situations.

* `scripts/swarm.py loop` re-checks `_require_unattended_ack()` inside the tmux window.
* If that env var isn’t visible inside the window, the loop will refuse to run unattended.

**Fix (robust): set it inside tmux explicitly** before starting the supervisor, or prefix the command that tmux runs.

Practical safe option:

```bash
tmux set-environment -g SWARM_UNATTENDED_I_UNDERSTAND 1
```

Then run your `tmux-start`.

If you want to avoid relying on tmux env behavior entirely, the best fix is to update `tmux_spawn_task_window()` to prefix commands with `SWARM_UNATTENDED_I_UNDERSTAND=1` when `--unattended` is used (template-side improvement; see section 4).

### P0-B) Git identity is required (automation will commit)

Your procedure doesn’t mention configuring git identity. But `swarm.py run-task` commits (claim + state update + results). Without `user.name` and `user.email`, commits can fail or get weird defaults.

Add once:

```bash
git config --global user.name  "swarm-bot"
git config --global user.email "swarm-bot@users.noreply.github.com"
```

(Use whatever identity you prefer.)

### P0-C) Your sweep loop currently ignores critical failures

This line is dangerous:

```bash
git push || true
```

If push fails (branch protection, non-fast-forward, auth expiry), your sweep loop will **pretend everything is fine**, but the repo won’t advance, so dependencies won’t unlock, and the swarm will stall.

Same issue with `git pull --ff-only origin main || true`: you can silently get stuck in a diverged state.

**Fix:** treat push/pull failure as a *hard error* (exit) or implement a deterministic “reset to origin/main” strategy (since it’s a disposable sandbox).

### P0-D) Branch protection vs “push sweeps to main”

Your sweep loop commits and pushes directly to `main`. Many repos block that via branch protection (“require PR”, “restrict who can push”).

If you truly want zero babysitting, you need **one** of these:

* allow direct pushes to `main` **from this automation identity**, OR
* make the sweep loop open a PR + auto-merge (adds overhead / PR spam), OR
* change the swarm design so sweeps aren’t needed to unlock dependencies (see section 3).

Right now, your procedure assumes direct push is allowed, but doesn’t state it as a hard prerequisite.

### P0-E) Supervisor repo state freshness

`swarm.py loop` does `git fetch origin` but it does **not** `git pull` main. If your sweep loop is in the **same checkout**, you’re fine because the working tree updates.

If your sweep loop is in a different checkout, the supervisor checkout will become stale and will make wrong choices.

So: either run both loops in the **same repo checkout** (as you wrote), or teach the supervisor loop to hard-sync to `origin/main` each tick.

---

## 3) A tighter “human kickstart” procedure I would use (as-is template)

This is the **same intent** as yours, but removes the “silent failure” risks.

### 0) One-time sandbox prerequisites

In the sandbox repo checkout:

```bash
git checkout main
git pull --ff-only origin main
make gate
make test

# hard requirements
command -v tmux
command -v codex
command -v gh
# (optional) command -v claude

gh auth status
git config user.name
git config user.email
python scripts/swarm.py plan
```

Also confirm GitHub repo settings consistent with your target autonomy level:

* auto-merge enabled,
* no required human reviews (including codeowner reviews) **if** you want true hands-off,
* required CI checks must pass for merge.

### 1) Start supervisor loop (Worker+Judge automation)

Do **both** of these to avoid tmux env gotchas:

```bash
export SWARM_UNATTENDED_I_UNDERSTAND=1
tmux set-environment -g SWARM_UNATTENDED_I_UNDERSTAND 1

python scripts/swarm.py tmux-start \
  --tmux-session swarm \
  --planner claude \
  --max-workers 2 \
  --interval-seconds 300 \
  --unattended \
  --create-pr \
  --auto-merge \
  --final-state done \
  --max-worker-seconds 1800 \
  --max-review-seconds 300
```

### 2) Start Planner sweep loop (same checkout; but fail loudly)

Use a “reset to origin/main” strategy to avoid divergence:

```bash
tmux new-window -t swarm -n planner 'bash -lc '"'"'
set -euo pipefail
while true; do
  git fetch origin
  git checkout -f main
  git reset --hard origin/main

  make sweep

  if ! git diff --quiet; then
    git add -A
    git commit -m "Planner sweep: align task folders with State"
    git push origin main
  fi

  sleep 60
done
'"'"''
```

If branch protection blocks direct pushes to main, **do not** keep `|| true`. Instead:

* either intentionally relax that protection for this repo/sandbox, or
* rewrite sweep to PR+auto-merge (more complex, noisier), or
* adopt the design change below so sweeps aren’t required for progress.

### 3) Monitor / stop

* Monitor: `tmux attach -t swarm`, `gh pr list`, GitHub Actions page.
* Stop: `tmux kill-session -t swarm`

---

## 4) Template review: what’s strong vs what still needs tightening

### What’s strong (you should keep)

* **Contracts + protocol lock precedence** is explicit and actually enforced culturally (AGENTS) *and partially enforced mechanically* (`gate_protocol_complete`, contract change discipline).
* **Task frontmatter + allowed/disallowed paths** is the correct “merge firewall” for agent swarms.
* **Gates are fast and deterministic** (good instinct). You’re avoiding the classic trap of “gates become a second pipeline”.
* **Swarm automation is pragmatic**: worktrees, PRs, optional auto-merge, timeouts. This is the right substrate for parallelism.

### P0/P1 issues I’d fix in the template (not just in your runbook)

#### P0-1) The sweep dependency is real — but you shouldn’t need an ad-hoc bash loop

Right now you require “external glue” (your bash sweep loop) for the system to make forward progress on dependencies.

Two better options:

**Option A (minimal behavior change): make `done_task_ids()` state-based, not folder-based.**
Scan all lifecycle folders and return task_ids where `State: done`, regardless of folder. Then sweeps are only for cleanliness, not progress.

Concretely: replace `done_task_ids()` with something like:

```py
def done_task_ids() -> set[str]:
    out: set[str] = set()
    for sub in ["active", "backlog", "ready_for_review", "blocked", "done"]:
        for t in list_tasks(task_dir(sub)):
            if t.state == "done":
                out.add(t.task_id)
    return out
```

**Option B (stronger separation): add a first-class `swarm.py sweep-loop` subcommand.**
So the template itself owns the “Planner sweep loop” and can implement sane git sync (fetch/reset) + commit/push + optional PR.

If you want real autonomy for other teams, Option B is the reusable one.

#### P0-2) Supervisor loop freshness (source-of-truth drift)

`cmd_loop()` fetches but doesn’t sync working tree. In a long-running unattended system, you’ll eventually run into “local main drift”.

If you keep “same checkout for sweep and supervisor,” it works. But it’s fragile and undocumented as a hard constraint.

Fix options:

* In supervisor tick: `git fetch origin && git reset --hard origin/main` (safe because supervisor doesn’t make local edits).
* Or pass `--base-branch origin/main` and always read tasks from a pulled working tree (still need pull for file tree).

#### P1-3) Path ownership enforcement currently allows task-file moves (violates your own governance)

In `scripts/swarm.py`, you intentionally whitelist the task file **in any lifecycle folder**:

```py
task_paths = {f".orchestrator/{d}/{task_file.name}" for d in ...}
```

That means a worker could “accidentally” `git mv` the task file across lifecycle folders and your ownership check would still say OK — contradicting “Planner only moves tasks”.

If you want the automation to actually enforce the governance you wrote, tighten it:

* allow edits only to the **current** `task_file` path, not the same filename in other folders;
* allow `.orchestrator/handoff/`;
* disallow everything else under `.orchestrator/`.

That makes “Planner sweep” the only mechanism that moves tasks.

#### P1-4) Manual runbook vs automation command mismatch (Codex)

Your manual runbook shows:

```bash
codex -p "Role: Worker..."
```

But automation uses:

```bash
codex exec --sandbox ... -C <dir> "<prompt>"
```

That’s a real usability footgun: people will copy the runbook and get different behavior than automation.

Fix: update `docs/runbook_swarm.md` to show the same codex invocation style used by `scripts/swarm.py` (or vice versa).

#### P1-5) “Stuck PR / failing CI” has no recovery loop

Current behavior:

* if CI fails, auto-merge won’t happen,
* PR stays open,
* task remains claimed,
* swarm won’t start downstream tasks,
* but nothing reassigns a worker to fix it.

That’s fine for Stage 2, but it’s exactly the “babysitting” point you’re trying to eliminate.

Template-level improvement:

* add a periodic check: find claimed tasks whose PR is failing or stale → run a “repair” worker pass (bounded) → update notes → re-run gates.

Even a crude version (one retry after N hours) is enough to avoid deadlocks.

#### P2-6) Small contract/dictionary semantics clarification

Your protocol says: if either `L2Fees_{i,t}` or `RentPaid_{i,t}` is missing for a rollup-day, exclude that rollup-day from sums.
Your data dictionary marks `l2_fees_eth` and `rent_paid_eth` as **Nullable: no**.

This can be consistent *only if* your panel construction rule is: “rows exist iff both values exist.”
If that’s the intent, write it explicitly (either in the dictionary or the protocol). Otherwise you’ll get downstream agents arguing about whether missing should be encoded as null vs row omission.

---

## 5) Bottom line

* **Your kickstart procedure is directionally correct** for the current code: supervisor loop + sweep loop is the right mental model.
* **But** you need to tighten it in three places to avoid “silent stalls”:

  1. tmux env propagation for unattended ack,
  2. git identity + auth checks,
  3. sweep loop must fail loudly (and/or reset to origin/main) and must account for branch protection.

If you want to reduce babysitting materially, the highest-leverage template change is: **stop making dependency-unblocking depend on physical folder moves** (scan `State: done` across all task dirs), or bake the sweep loop into `scripts/swarm.py` so users don’t invent brittle bash glue.