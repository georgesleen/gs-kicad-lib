.PHONY: run help validate unit-test install import passive

run:
	uv run kicad-lib

help:
	@echo "run       : open the interactive TUI menu."
	@echo "install   : install this library and set environment variables in KiCad for portability."
	@echo "import    : interactively import a part from LCSC (shortcut, skips menu)."
	@echo "passive   : add a derived passive symbol using an LCSC ID (shortcut, skips menu)."
	@echo "validate  : Confirm current library complies with style guide."
	@echo "unit-test : Ensure that script logic passes unit testing"

install:
	scripts/install-git-hooks.sh
	scripts/setup-kicad.sh

import:
	uv run kicad-lib-import

passive:
	uv run kicad-lib-passive

validate:
	python3 scripts/check-symbol-fields.py

unit-test:
	uv run pytest

