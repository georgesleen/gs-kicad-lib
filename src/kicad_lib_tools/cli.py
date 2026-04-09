from __future__ import annotations

import argparse


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a part from easyeda2kicad into this repo's KiCad libraries."
    )
    parser.add_argument("--lcsc-id", help="LCSC part ID, for example C2040")
    parser.add_argument("--symbol-lib", help="Target symbol library, for example GS_IC")
    parser.add_argument(
        "--footprint-lib", help="Target footprint library, for example GS_Connectors"
    )
    parser.add_argument(
        "--existing-footprint-lib",
        help="Existing footprint library to link to, for example GS_SO",
    )
    parser.add_argument(
        "--existing-footprint",
        help="Existing footprint name to link to, for example SOIC-8_5.3x5.3mm_P1.27mm",
    )
    parser.add_argument(
        "--models-dir",
        help="Model destination directory. Defaults to 3d-models/",
    )
    parser.add_argument("--manufacturer", help="Manufacturer symbol field value")
    parser.add_argument(
        "--mpn",
        help="MPN symbol field value",
    )
    parser.add_argument("--mfr-part", dest="mpn", help=argparse.SUPPRESS)
    parser.add_argument("--datasheet", help="Datasheet symbol field value")
    parser.add_argument("--description", help="Description symbol field value")
    parser.add_argument("--package", help="Package symbol field value")
    parser.add_argument(
        "--field-validation-override",
        help="Optional Field Validation Override reason",
    )
    parser.add_argument(
        "--spice-warning-override",
        help="Optional SPICE Warning Override reason",
    )
    parser.add_argument(
        "--converter-command",
        help="Command used to run the converter. Defaults to the sibling easyeda2kicad checkout.",
    )
    parser.add_argument(
        "--name",
        help="Optional staging directory name. Defaults to a slug derived from the LCSC ID.",
    )
    parser.add_argument(
        "--overwrite-symbol",
        action="store_true",
        help="Replace an existing symbol with the same name",
    )
    parser.add_argument(
        "--overwrite-footprint",
        action="store_true",
        help="Replace an existing footprint with the same filename",
    )
    parser.add_argument(
        "--overwrite-models",
        action="store_true",
        help="Replace existing 3D models with the same filename",
    )
    parser.add_argument(
        "--no-symbol",
        action="store_true",
        help="Do not import the generated symbol into the repo",
    )
    parser.add_argument(
        "--no-footprint",
        action="store_true",
        help="Do not import the generated footprint into the repo",
    )
    parser.add_argument(
        "--no-3d",
        action="store_true",
        help="Do not import generated 3D models into the repo",
    )
    parser.add_argument(
        "--footprint-link-mode",
        choices=("generated", "existing", "none"),
        help="How an imported symbol should link its Footprint field",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting for missing values",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print converter command and validation details",
    )
    return parser.parse_args(argv)
