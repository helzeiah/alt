"""Path resolution mirroring Claude Code's own lookup logic."""
import os
from pathlib import Path


# ── Claude Code paths ────────────────────────────────────────────────────────

def claude_config_home() -> Path:
    """Return the Claude config directory.

    Returns:
        CLAUDE_CONFIG_DIR if set, otherwise ~/.claude.
    """
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def claude_credentials_path() -> Path:
    """Return the path to Claude Code's OAuth token file (Linux).

    Returns:
        <config_home>/.credentials.json
    """
    return claude_config_home() / ".credentials.json"


def claude_global_config_path() -> Path:
    """Return the path to ~/.claude.json.

    This file lives at the home-dir root, not inside ~/.claude. When
    CLAUDE_CONFIG_DIR is set it moves to <CLAUDE_CONFIG_DIR>/.claude.json.
    Falls back to the legacy <config_home>/.config.json if that file exists.

    Returns:
        Path to the global Claude config file.
    """
    legacy = claude_config_home() / ".config.json"
    if legacy.exists():
        return legacy
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env) if env else Path.home()
    return base / ".claude.json"


def claude_sessions_dir() -> Path:
    """Return the directory containing per-process Claude session files.

    Returns:
        ~/.claude/sessions/
    """
    return claude_config_home() / "sessions"


# ── alt paths ────────────────────────────────────────────────────────────────

def alt_dir() -> Path:
    """Return the root directory for all alt data.

    Returns:
        ~/.alt/
    """
    return Path.home() / ".alt"


def alt_config_path() -> Path:
    """Return the path to alt's config file.

    Returns:
        ~/.alt/config.json
    """
    return alt_dir() / "config.json"


def alt_credentials_dir() -> Path:
    """Return the directory for per-profile backup credential files (Linux).

    Returns:
        ~/.alt/credentials/
    """
    return alt_dir() / "credentials"


def alt_sessions_dir() -> Path:
    """Return the directory for per-profile CLAUDE_CONFIG_DIR roots used by alt run.

    Returns:
        ~/.alt/sessions/
    """
    return alt_dir() / "sessions"
