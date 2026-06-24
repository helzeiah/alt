"""Detect live Claude Code processes by reading session files."""
import json
import os

from alt.paths import claude_sessions_dir
from alt.platform import CURRENT, Platform


def running_sessions() -> list[dict]:
    """Return session metadata for each live Claude Code process.

    Reads PID-named JSON files from the sessions directory and checks
    whether each process is still running.

    Returns:
        List of session dicts for live processes. Each dict contains at
        minimum a ``pid`` key plus whatever Claude Code wrote to the file.
    """
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
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass  # process exists but we can't signal it

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
    if CURRENT == Platform.MACOS:
        print("  The new account takes effect within ~30 seconds.")
    else:
        print("  The new account takes effect immediately on your next message.")
