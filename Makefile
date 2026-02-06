.PHONY: gate

gate:
	python scripts/quality_gates.py

.PHONY: preflight

preflight:
	python scripts/preflight.py --profile base

.PHONY: preflight-onchain

preflight-onchain:
	python scripts/preflight.py --profile onchain

.PHONY: preflight-bigquery

preflight-bigquery:
	python scripts/preflight.py --profile bigquery --bq-smoke

.PHONY: test

test:
	python -m unittest discover -s tests

.PHONY: swarm-plan

swarm-plan:
	python scripts/swarm.py plan

.PHONY: swarm-tick

swarm-tick:
	python scripts/swarm.py tick

.PHONY: sweep

sweep:
	python scripts/sweep_tasks.py
