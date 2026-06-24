"""Read and write the oauthAccount block in ~/.claude.json."""
import json
from typing import Any

from alt.paths import claude_global_config_path


def read_oauth_account() -> dict[str, Any] | None:
    """Read the oauthAccount field from ~/.claude.json.

    Returns:
        The oauthAccount dict, or None if the file or field is missing.
    """
    path = claude_global_config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("oauthAccount")
    except (json.JSONDecodeError, OSError):
        return None


def write_oauth_account(account: dict[str, Any]) -> None:
    """Update the oauthAccount field in ~/.claude.json, preserving all other fields.

    Args:
        account: The oauthAccount dict to write.
    """
    path = claude_global_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data["oauthAccount"] = account
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
