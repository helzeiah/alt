"""Read and write the oauthAccount block in ~/.claude.json.

This file holds account metadata (email, org, billing type, etc.) that Claude
Code displays in the UI. It is separate from the OAuth token itself, which
lives in the keychain (macOS) or .credentials.json (Linux).

We update oauthAccount in-place so all other Claude Code settings are preserved.
"""
import json
from typing import Any

from alt.paths import claude_global_config_path


def read_oauth_account() -> dict[str, Any] | None:
    path = claude_global_config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("oauthAccount")
    except (json.JSONDecodeError, OSError):
        return None


def write_oauth_account(account: dict[str, Any]) -> None:
    path = claude_global_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data["oauthAccount"] = account
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
