.PHONY: verify

verify:
	npm run tag:check
	npm run docs:check
	uv run python scripts/quality_gate.py
