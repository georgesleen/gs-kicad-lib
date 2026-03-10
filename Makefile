.PHONY: validate validate-symbol-fields

validate: validate-symbol-fields

validate-symbol-fields:
	python3 scripts/check-symbol-fields.py
