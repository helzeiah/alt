"""Platform-aware credential I/O.

Provides two pairs of read/write functions:
  active  — the credential slot Claude Code reads
  backup  — alt's own per-profile copies
"""
import base64
import os
import tempfile
from pathlib import Path

from alt.platform import CURRENT, Platform
from alt.paths import claude_credentials_path, alt_credentials_dir

if CURRENT == Platform.MACOS:
    from alt import keychain  # type: ignore[attr-defined]

_ACTIVE_SERVICE = "Claude Code-credentials"
_BACKUP_SERVICE_PREFIX = "alt"


def _atomic_write(path: Path, data: str, mode: int = 0o600) -> None:
    """Write data to path via a temp file then os.replace(), preventing partial writes.

    Args:
        path: Destination file path.
        data: String content to write.
        mode: File permission bits.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, data.encode())
        os.close(fd)
        fd = -1
        if os.name != "nt":
            os.chmod(tmp, mode)
        os.replace(tmp, str(path))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _enc_path(name: str) -> Path:
    return alt_credentials_dir() / f"{name}.enc"


# ── active credential ────────────────────────────────────────────────────────

def read_active() -> str | None:
    """Read the credential Claude Code is currently using.

    Returns:
        The raw credential string, or None if not found.
    """
    if CURRENT == Platform.MACOS:
        return keychain.get(_ACTIVE_SERVICE)

    cred_file = claude_credentials_path()
    if cred_file.exists():
        return cred_file.read_text(encoding="utf-8").strip() or None
    return None


def write_active(value: str) -> None:
    """Write to Claude Code's active credential slot.

    Args:
        value: The credential string to make active.
    """
    if CURRENT == Platform.MACOS:
        keychain.set(_ACTIVE_SERVICE, value)
        return

    _atomic_write(claude_credentials_path(), value)


def delete_active() -> None:
    """Remove Claude Code's active credential."""
    if CURRENT == Platform.MACOS:
        keychain.delete(_ACTIVE_SERVICE)
        return

    cred_file = claude_credentials_path()
    if cred_file.exists():
        cred_file.unlink()


# ── backup credentials ───────────────────────────────────────────────────────

def read_backup(name: str) -> str | None:
    """Read alt's saved copy of a profile's credential.

    Args:
        name: Profile name.

    Returns:
        The credential string, or None if no backup exists.
    """
    if CURRENT == Platform.MACOS:
        return keychain.get(f"{_BACKUP_SERVICE_PREFIX}-{name}")

    enc = _enc_path(name)
    if not enc.exists():
        return None
    try:
        return base64.b64decode(enc.read_text().strip()).decode()
    except Exception:
        return None


def write_backup(name: str, value: str) -> None:
    """Save a profile's credential into alt's backup store.

    Args:
        name: Profile name.
        value: The credential string to back up.
    """
    if CURRENT == Platform.MACOS:
        keychain.set(f"{_BACKUP_SERVICE_PREFIX}-{name}", value)
        return

    alt_credentials_dir().mkdir(parents=True, exist_ok=True)
    encoded = base64.b64encode(value.encode()).decode()
    _atomic_write(_enc_path(name), encoded)


def delete_backup(name: str) -> None:
    """Remove alt's saved copy of a profile's credential.

    Args:
        name: Profile name.
    """
    if CURRENT == Platform.MACOS:
        keychain.delete(f"{_BACKUP_SERVICE_PREFIX}-{name}")
        return

    enc = _enc_path(name)
    if enc.exists():
        enc.unlink()
