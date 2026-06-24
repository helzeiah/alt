"""Account switching orchestration.

Coordinates credential I/O, OAuth metadata, and config updates in the
correct order for each operation.
"""
import os
import sys
from pathlib import Path

from alt import credentials, profile as profile_mod, process as process_mod
from alt.config import Config, ProfileMeta, load, now_iso, save
from alt.paths import alt_sessions_dir, claude_config_home
from alt.platform import CURRENT, Platform


def add(name: str) -> None:
    """Save the currently active account as a named profile.

    Args:
        name: Profile name to create.
    """
    token = credentials.read_active()
    if not token:
        print("Error: no active credential found. Are you logged in to Claude Code?", file=sys.stderr)
        sys.exit(1)

    oauth = profile_mod.read_oauth_account()
    if not oauth:
        print("Error: no oauthAccount found in ~/.claude.json.", file=sys.stderr)
        sys.exit(1)

    credentials.write_backup(name, token)

    config = load()
    config.profiles[name] = ProfileMeta(
        name=name,
        email=oauth.get("emailAddress", ""),
        oauth_account=oauth,
        added_at=now_iso(),
    )
    if name not in config.priority:
        config.priority.append(name)
    config.current = name
    save(config)

    email = oauth.get("emailAddress", "unknown")
    print(f'Saved profile "{name}" ({email})')


def switch(name: str) -> None:
    """Swap credentials and OAuth metadata to the named profile.

    Saves the currently active token back to its own backup before
    overwriting, so switching away never loses the outgoing credential.

    Args:
        name: Profile name to switch to.
    """
    config = load()

    if name not in config.profiles:
        _no_such_profile(name, config)

    process_mod.warn_if_running()

    current = config.current
    if current and current != name and current in config.profiles:
        token = credentials.read_active()
        if token:
            credentials.write_backup(current, token)

    target_token = credentials.read_backup(name)
    if not target_token:
        print(
            f'Warning: no saved credential for "{name}". '
            "You may need to log in again.",
            file=sys.stderr,
        )
    else:
        credentials.write_active(target_token)

    profile_mod.write_oauth_account(config.profiles[name].oauth_account)
    config.current = name
    save(config)

    email = config.profiles[name].email
    print(f'Switched to "{name}" ({email})')
    if CURRENT == Platform.MACOS:
        print("Takes effect within ~30 seconds as the keychain cache expires.")
    else:
        print("Switch is immediate — next message uses the new account.")


def next_profile() -> None:
    """Switch to the next profile in priority order, wrapping around."""
    config = load()

    if not config.priority:
        print("Error: no priority order set.", file=sys.stderr)
        sys.exit(1)

    current = config.current
    if current in config.priority:
        idx = (config.priority.index(current) + 1) % len(config.priority)
    else:
        idx = 0

    switch(config.priority[idx])


def remove(name: str) -> None:
    """Delete a profile and its backed-up credential.

    Args:
        name: Profile name to remove.
    """
    config = load()
    if name not in config.profiles:
        _no_such_profile(name, config)

    credentials.delete_backup(name)
    del config.profiles[name]

    if name in config.priority:
        config.priority.remove(name)
    if config.current == name:
        config.current = config.priority[0] if config.priority else None

    save(config)
    print(f'Removed profile "{name}".')


def run(name: str, claude_args: list[str]) -> None:
    """Launch claude in a fully isolated CLAUDE_CONFIG_DIR session.

    Writes the profile's credential into a per-profile directory, symlinks
    shared Claude config into it, then execs claude with CLAUDE_CONFIG_DIR
    pointing there. Never returns.

    Args:
        name: Profile name to run as.
        claude_args: Extra arguments forwarded to claude.
    """
    config = load()
    if name not in config.profiles:
        _no_such_profile(name, config)

    token = credentials.read_backup(name)
    if not token:
        print(f'Error: no saved credential for "{name}".', file=sys.stderr)
        sys.exit(1)

    session_dir = alt_sessions_dir() / name
    session_dir.mkdir(parents=True, exist_ok=True)

    cred_file = session_dir / ".credentials.json"
    cred_file.write_text(token, encoding="utf-8")
    cred_file.chmod(0o600)

    _symlink_shared_config(session_dir)

    env = {
        k: v for k, v in os.environ.items()
        if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
    }
    env["CLAUDE_CONFIG_DIR"] = str(session_dir)

    email = config.profiles[name].email
    print(f'Launching Claude Code as "{name}" ({email})')
    print(f"Session dir: {session_dir}")

    os.execvpe("claude", ["claude"] + claude_args, env)


def _symlink_shared_config(session_dir: Path) -> None:
    """Symlink user-level Claude config files into an isolated session directory.

    Args:
        session_dir: The CLAUDE_CONFIG_DIR for the isolated session.
    """
    src_dir = claude_config_home()
    shared = ["settings.json", "commands", "CLAUDE.md", "keybindings.json"]

    for item in shared:
        src = src_dir / item
        dst = session_dir / item
        if not src.exists() or dst.exists():
            continue
        try:
            dst.symlink_to(src)
        except OSError:
            pass


def _no_such_profile(name: str, config: Config) -> None:
    """Print an error and exit when a profile name is not found.

    Args:
        name: The profile name that was requested.
        config: Current config, used to list available profiles.
    """
    available = ", ".join(config.profiles) or "(none)"
    print(f'Error: no profile named "{name}".', file=sys.stderr)
    print(f"Available: {available}", file=sys.stderr)
    sys.exit(1)
