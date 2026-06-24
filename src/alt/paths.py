import os
from pathlib import Path


# ── Claude Code paths ────────────────────────────────────────────────────────

def claude_config_home() -> Path:
    """~/.claude, or CLAUDE_CONFIG_DIR if the user has set it."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def claude_credentials_path() -> Path:
    """<config_home>/.credentials.json — where Claude Code stores the OAuth token on Linux."""
    return claude_config_home() / ".credentials.json"


def claude_global_config_path() -> Path:
    """~/.claude.json — stores oauthAccount metadata.

    Note: this file lives at the home-dir root, NOT inside ~/.claude/.
    When CLAUDE_CONFIG_DIR is set it moves to <CLAUDE_CONFIG_DIR>/.claude.json.
    Falls back to the legacy <config_home>/.config.json if that file exists.
    """
    legacy = claude_config_home() / ".config.json"
    if legacy.exists():
        return legacy
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env) if env else Path.home()
    return base / ".claude.json"


def claude_sessions_dir() -> Path:
    """~/.claude/sessions/ — one JSON file per running Claude process, named by PID."""
    return claude_config_home() / "sessions"


# ── alt paths ────────────────────────────────────────────────────────────────

def alt_dir() -> Path:
    return Path.home() / ".alt"


def alt_config_path() -> Path:
    return alt_dir() / "config.json"


def alt_credentials_dir() -> Path:
    """Stores per-profile backup credentials as base64 .enc files (Linux/fallback)."""
    return alt_dir() / "credentials"


def alt_sessions_dir() -> Path:
    """Per-profile CLAUDE_CONFIG_DIR roots used by `alt run`."""
    return alt_dir() / "sessions"
