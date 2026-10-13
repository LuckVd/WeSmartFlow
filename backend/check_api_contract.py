"""Fail fast when the published OpenAPI contract is ambiguous or incomplete."""

from __future__ import annotations

from main import app


def main() -> int:
    schema = app.openapi()
    operation_ids: list[str] = []
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                print(f"missing operationId: {method.upper()} {path}")
                return 1
            operation_ids.append(operation_id)
    duplicates = sorted(
        {item for item in operation_ids if operation_ids.count(item) > 1}
    )
    if duplicates:
        print("duplicate operationIds:", ", ".join(duplicates))
        return 1
    print(
        f"API contract OK: OpenAPI {schema.get('openapi')}, {len(operation_ids)} operations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
