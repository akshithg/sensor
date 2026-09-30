"""Build the static GitHub Pages version of the SENSOR Lite demo."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from sensor_lite.demo_data import build_demo

PACKAGE_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PACKAGE_ROOT / "web"
STATIC_DATA_META = '    <meta name="sensor-demo-data" content="./demo.json" />\n'
STATIC_ASSETS = ("app.js", "favicon.svg", "styles.css")


def build_static_site(output: Path) -> None:
    """Write a self-contained, read-only demo to ``output``.

    Args:
        output: Directory that will contain the generated Pages files.
    """
    output.mkdir(parents=True, exist_ok=True)

    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    marker = (
        '    <meta name="description" content="SENSOR Lite graph-based code evolution demo" />\n'
    )
    if marker not in index:
        raise ValueError("web/index.html is missing the static-data insertion point")

    (output / "index.html").write_text(
        index.replace(marker, marker + STATIC_DATA_META),
        encoding="utf-8",
    )
    for asset in STATIC_ASSETS:
        shutil.copyfile(WEB_ROOT / asset, output / asset)

    (output / "demo.json").write_text(
        json.dumps(build_demo(), indent=2) + "\n",
        encoding="utf-8",
    )
    (output / ".nojekyll").touch()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Build the static SENSOR Lite GitHub Pages site")
    parser.add_argument("--output", type=Path, default=Path("docs"))
    return parser.parse_args()


def main() -> None:
    """Build the static site from the bundled web assets and demo data."""
    args = parse_args()
    build_static_site(args.output)
    print(f"Static site written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
