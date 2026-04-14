from typing import Any


def parse_graphql_errors(errors: Any) -> list[str]:
    """Normalize a GraphQL errors value to a flat list of message strings."""
    if not isinstance(errors, list):
        errors = [errors]
    return [e.get("message", str(e)) if isinstance(e, dict) else str(e) for e in errors]
