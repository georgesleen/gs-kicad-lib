.PHONY: run help validate install import passive libraries update-tools

run:
	uv run partsmith

help:
	@echo "run          : open the interactive partsmith menu."
	@echo "install      : install git hooks and register the libraries in KiCad."
	@echo "import       : import a part from LCSC (skips the menu)."
	@echo "passive      : add a derived passive symbol from an LCSC ID (skips the menu)."
	@echo "libraries    : regenerate LIBRARIES.md from the symbols."
	@echo "validate     : check the symbol fields against the conventions."
	@echo "update-tools : update partsmith to the latest commit on its main branch."

install:
	scripts/install-git-hooks.sh
	uv run partsmith setup

import:
	uv run partsmith import

passive:
	uv run partsmith passive

libraries:
	uv run partsmith libraries-md

validate:
	uv run partsmith validate

update-tools:
	uv lock --upgrade-package kicad-partsmith
	uv sync
