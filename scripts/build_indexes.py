#!/usr/bin/env python3
"""Build symbol and footprint indexes from KiCad libraries."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.web.symbol_index import generate_indexes, get_default_indexes_dir
from src.web.kicad_paths import get_kicad_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build KiCad library indexes")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output directory for JSON indexes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detected paths",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Rebuild even if the system fingerprint is unchanged",
    )
    args = parser.parse_args()

    output_dir = args.output or get_default_indexes_dir()

    if args.verbose:
        paths = get_kicad_paths()
        print("Detected KiCad paths:")
        print(f"  Symbols: {paths.system_symbols}")
        print(f"  Footprints: {paths.system_footprints}")
        print(f"  User library: {paths.user_library}")
        print()

    print(f"Building indexes in {output_dir}...")

    try:
        sym_count, fp_count = generate_indexes(output_dir, force=args.force)
        print(f"  Symbols: {sym_count} entries")
        print(f"  Footprints: {fp_count} entries")
        print("Done!")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
