.PHONY: help validate unit-test install import

help:
	echo @"install   : install this library and set environment variables in KiCad for portability"
	echo @"import    : interactively import a part from LCSC"
	echo @"validate  : Confirm current library complies with style guide. Errors for missing procurement fields and warnings for missing SPICE models"
	echo @"unit-test : Ensure that script logic passes unit testing"

install:
	scripts/install-git-hooks.sh
	scripts/setup-kicad.sh

import: install
	uv run scripts/easyeda-import.py

validate:
	uv run scripts/check-symbol-fields.py

unit-test:
	uv run pytest
