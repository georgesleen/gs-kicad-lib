.PHONY: help validate unit-test install import passive

help:
	@echo "install   : install this library and set environment variables in KiCad for portability."
	@echo "import    : interactively import a part from LCSC."
	@echo "passive   : add a derived passive symbol using an LCSC ID."
	@echo "validate  : Confirm current library complies with style guide. Errors for missing procurement fields and warnings for missing SPICE models"
	@echo "unit-test : Ensure that script logic passes unit testing"

install:
	scripts/install-git-hooks.sh
	scripts/setup-kicad.sh

import:
	uv run scripts/easyeda-import.py

passive:
	uv run scripts/create-passive.py

validate:
	python3 scripts/check-symbol-fields.py

unit-test:
	uv run pytest
