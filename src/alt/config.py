"""alt configuration: profile metadata and priority ordering.

Stored at ~/.alt/config.json. Written atomically so a crash during save
never leaves a corrupt file.
"""
import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from alt.paths import alt_config_path, alt_dir

_VERSION = 1


@dataclass
class ProfileMeta:
    """Metadata for a saved account profile."""
    name: str
    email: str
    oauth_account: dict[str, Any]
    added_at: str  # ISO 8601 UTC


@dataclass
class Config:
    """alt's persisted state."""
    version: int = _VERSION
    priority: list[str] = field(default_factory=list)
    current: str | None = None
    profiles: dict[str, ProfileMeta] = field(default_factory=dict)


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Returns:
        Current UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def load() -> Config:
    """Load config from disk, returning an empty Config if the file is missing.

    Returns:
        The current Config.
    """
    path = alt_config_path()
    if not path.exists():
        return Config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Config()

    profiles = {
        name: ProfileMeta(**data)
        for name, data in raw.get("profiles", {}).items()
    }
    return Config(
        version=raw.get("version", _VERSION),
        priority=raw.get("priority", []),
        current=raw.get("current"),
        profiles=profiles,
    )


def save(config: Config) -> None:
    """Write config to disk atomically.

    Args:
        config: The Config to persist.
    """
    path = alt_config_path()
    alt_dir().mkdir(mode=0o700, parents=True, exist_ok=True)

    data = {
        "version": config.version,
        "priority": config.priority,
        "current": config.current,
        "profiles": {name: asdict(p) for name, p in config.profiles.items()},
    }

    fd, tmp = tempfile.mkstemp(dir=str(alt_dir()), suffix=".tmp")
    try:
        os.write(fd, json.dumps(data, indent=2).encode())
        os.close(fd)
        fd = -1
        os.chmod(tmp, 0o600)
        os.replace(tmp, str(path))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
