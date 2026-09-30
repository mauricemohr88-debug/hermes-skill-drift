"""Create two synthetic Git commits and ten harmless skills in a new directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from hermes_skill_drift.demo import create_demo
except ModuleNotFoundError as exc:
    if exc.name != "hermes_skill_drift":
        raise
    # The legacy example also remains runnable directly from an uninstalled checkout.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from hermes_skill_drift.demo import create_demo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="A new, non-existing demo directory")
    args = parser.parse_args()
    print(json.dumps(create_demo(args.directory), indent=2))


if __name__ == "__main__":
    main()
