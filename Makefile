.PHONY: validate unit-test

validate:
	uv run scripts/check-symbol-fields.py

unit-test:
	uv run pytest

install:
	scripts/install-git-hooks.sh
	scripts/setup-kicad.sh

import: install
	uv run scripts/easyeda-import.py
