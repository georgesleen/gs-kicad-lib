.PHONY: validate unit-test

validate:
	uv run scripts/check-symbol-fields.py

unit-test:
	uv run pytest
