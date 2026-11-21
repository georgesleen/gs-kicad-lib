.PHONY: run help validate unit-test typecheck lint format install import passive libraries

run:
	uv run kicad-lib

help:
	@echo "run       : open the interactive TUI menu."
	@echo "install   : install this library and set environment variables in KiCad for portability."
	@echo "import    : interactively import a part from LCSC (shortcut, skips menu)."
	@echo "passive   : add a derived passive symbol using an LCSC ID (shortcut, skips menu)."
	@echo "libraries : Regenerate LIBRARIES.md from symbols."
	@echo "validate  : Confirm current library complies with style guide."
	@echo "unit-test : Ensure that script logic passes unit testing"
	@echo "typecheck : Run mypy static type checking on src/"

install:
	scripts/install-git-hooks.sh
	uv run kicad-lib setup

import:
	uv run kicad-lib import

passive:
	uv run kicad-lib passive

libraries:
	uv run kicad-lib libraries-md

validate:
	uv run kicad-lib validate

unit-test:
	uv run pytest

typecheck:
	uv run mypy src/

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

