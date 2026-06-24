"""macOS Keychain access via /usr/bin/security."""
import os
import pwd
import subprocess

_SECURITY = "/usr/bin/security"
_TIMEOUT = 5


class KeychainError(Exception):
    pass


def account_name() -> str:
    """Return the local username for keychain entries.

    Mirrors Claude Code's getUsername(): checks $USER, then the password
    database, then falls back to a constant.

    Returns:
        The current username string.
    """
    name = os.environ.get("USER")
    if name:
        return name
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return "claude-code-user"


def get(service: str) -> str | None:
    """Read a password from the keychain.

    Args:
        service: The keychain service name to look up.

    Returns:
        The stored password, or None if the item does not exist.

    Raises:
        KeychainError: If the keychain operation fails for any reason
            other than the item not being found.
    """
    r = subprocess.run(
        [_SECURITY, "find-generic-password", "-s", service, "-w"],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    if r.returncode == 44:
        return None
    if r.returncode != 0:
        raise KeychainError(f"keychain read failed (rc {r.returncode}): {r.stderr.strip()}")
    return r.stdout.strip() or None


def set(service: str, value: str) -> None:
    """Write a password to the keychain, creating or updating the entry.

    Uses subprocess list form so the value is passed directly to the OS
    without shell interpretation.

    Args:
        service: The keychain service name.
        value: The password to store.

    Raises:
        KeychainError: If the write fails.
    """
    r = subprocess.run(
        [_SECURITY, "add-generic-password", "-U", "-s", service, "-a", account_name(), "-w", value],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    if r.returncode != 0:
        raise KeychainError(f"keychain write failed (rc {r.returncode}): {r.stderr.strip()}")


def delete(service: str) -> None:
    """Delete a keychain entry. Succeeds silently if the item does not exist.

    Args:
        service: The keychain service name to delete.
    """
    subprocess.run(
        [_SECURITY, "delete-generic-password", "-s", service],
        capture_output=True,
        timeout=_TIMEOUT,
    )
