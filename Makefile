.PHONY: gate

gate:
	python scripts/quality_gates.py

.PHONY: test

test:
	python -m unittest discover -s tests

.PHONY: swarm-plan

swarm-plan:
	python scripts/swarm.py plan

.PHONY: swarm-tick

swarm-tick:
	python scripts/swarm.py tick
