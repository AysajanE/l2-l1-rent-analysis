# Ready for review

Tasks that a Worker believes are complete and are awaiting Judge verification.

- Worker sets `State: ready_for_review` in the task file.
- Planner (or a sweep script) moves the task file here.
- Judge runs gates/tests and either:
  - requests fixes (State: active), or
  - approves (State: done) and Planner moves to `done/`.
