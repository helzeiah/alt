"""macOS Keychain access via /usr/bin/security. Not imported on Linux."""
import os
import pwd
import subprocess

_SECURITY = "/usr/bin/security"
_TIMEOUT = 5  # seconds — bail out if keychain is locked/unresponsive


class KeychainError(Exception):
    pass


def account_name() -> str:
    """Mirror Claude Code's getUsername(): $USER → pwd lookup → fallback."""
    name = os.environ.get("USER")
    if name:
        return name
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return "claude-code-user"


def get(service: str) -> str | None:
    """Return the stored password, or None if the item doesn't exist."""
    r = subprocess.run(
        [_SECURITY, "find-generic-password", "-s", service, "-w"],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    if r.returncode == 44:  # item not found — not an error
        return None
    if r.returncode != 0:
        raise KeychainError(f"keychain read failed (rc {r.returncode}): {r.stderr.strip()}")
    return r.stdout.strip() or None


def set(service: str, value: str) -> None:
    """Write value to keychain, creating or updating the entry.

    Uses subprocess list form (no shell) so the JSON credential string is
    passed directly to the OS — no encoding needed, no argv injection risk.
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
    """Delete a keychain entry. Silently succeeds if the item doesn't exist."""
    subprocess.run(
        [_SECURITY, "delete-generic-password", "-s", service],
        capture_output=True,
        timeout=_TIMEOUT,
    )
