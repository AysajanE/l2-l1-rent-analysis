.PHONY: gate

gate:
	python scripts/quality_gates.py

.PHONY: test

test:
	python -m unittest discover -s tests
