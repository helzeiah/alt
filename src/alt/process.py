"""Detect running Claude Code instances by reading ~/.claude/sessions/.

Session files are named by PID (e.g. 17664.json). We check liveness with
os.kill(pid, 0) — sends no signal, just checks if the process exists.
"""
import json
import os

from alt.paths import claude_sessions_dir


def running_sessions() -> list[dict]:
    """Return session metadata for each live Claude Code process."""
    sessions_dir = claude_sessions_dir()
    if not sessions_dir.exists():
        return []

    live = []
    for path in sessions_dir.glob("*.json"):
        try:
            pid = int(path.stem)
        except ValueError:
            continue

        try:
            os.kill(pid, 0)  # raises if process doesn't exist
        except ProcessLookupError:
            continue
        except PermissionError:
            pass  # process exists but we can't signal it — count it as live

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["pid"] = pid
            live.append(data)
        except (json.JSONDecodeError, OSError):
            live.append({"pid": pid})

    return live


def warn_if_running() -> None:
    """Print a warning if any live Claude Code sessions are detected."""
    sessions = running_sessions()
    if not sessions:
        return

    pids = ", ".join(str(s["pid"]) for s in sessions)
    print(f"Warning: {len(sessions)} running Claude Code session(s) detected (PID {pids}).")
    print("  The credential swap will take effect within ~30s on macOS.")
    print("  On Linux it is instant — the next message will use the new account.")
