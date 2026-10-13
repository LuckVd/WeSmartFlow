"""Export public OpenAPI and compact manifest for generated client assets."""

from __future__ import annotations

import json
from pathlib import Path

from api.manifest import write_manifest
from main import app

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend" / "src" / "api" / "generated"


def main() -> None:
    schema = app.openapi()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_manifest(schema, OUTPUT / "manifest.json")
    print(f"exported API contract to {OUTPUT}")


if __name__ == "__main__":
    main()
