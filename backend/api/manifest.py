"""Build deterministic API contract artifacts from FastAPI OpenAPI metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def build_manifest(openapi: dict[str, Any]) -> dict[str, Any]:
    """Create a compact, stable catalog useful to Web and mini-program clients."""

    operations = []
    for path, path_item in sorted((openapi.get("paths") or {}).items()):
        for method, operation in sorted(path_item.items()):
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operations.append(
                {
                    "operation_id": operation.get("operationId", ""),
                    "method": method.upper(),
                    "path": path,
                    "tags": operation.get("tags", []),
                    "request_schema": _schema_ref(operation.get("requestBody")),
                    "response_schemas": {
                        code: _schema_ref(response)
                        for code, response in sorted(
                            (operation.get("responses") or {}).items()
                        )
                    },
                }
            )
    body = {
        "openapi": openapi.get("openapi"),
        "version": openapi.get("info", {}).get("version"),
        "operations": operations,
    }
    encoded = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {**body, "contract_sha256": hashlib.sha256(encoded).hexdigest()}


def write_manifest(openapi: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(build_manifest(openapi), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def _schema_ref(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    if "$ref" in node:
        return str(node["$ref"])
    content = node.get("content") or {}
    for media in content.values():
        schema = media.get("schema") if isinstance(media, dict) else None
        if isinstance(schema, dict):
            if "$ref" in schema:
                return str(schema["$ref"])
            return schema.get("title", "")
    return ""
