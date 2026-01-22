# Optional GitHub workflows (opt-in)

This folder contains optional GitHub Actions workflows that are **not required** for the core swarm architecture.

These workflows can introduce operational risk (secrets management, unintended triggers). Keep them disabled unless you explicitly want this behavior.

## How to enable

1. Copy the workflow file(s) back into `.github/workflows/`.
2. Configure required GitHub repository secrets (see each workflow for details).
3. Review trigger conditions carefully (e.g., comment-based invocation vs. PR events).

## Notes

- Keep the core CI workflow (`.github/workflows/ci.yml`) enabled. It enforces `make gate` on PRs/pushes.
- If you enable agent-based workflows, prefer restrictive triggers and explicit allowlists.
