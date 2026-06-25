"""Account switching orchestration.

Coordinates credential I/O, OAuth metadata, and config updates in the
correct order for each operation.
"""
import json
import os
import sys
from pathlib import Path

from alt import credentials, profile as profile_mod, process as process_mod, usage
from alt.config import Config, ProfileMeta, load, now_iso, save
from alt.paths import alt_sessions_dir, claude_config_home
from alt.platform import CURRENT, Platform
from alt.usage import Spend


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
        # Heal a stale backup before activating it, so Claude Code receives a
        # live token instead of an expired one that would force a re-login.
        if usage.is_expired(target_token):
            fresh, err = _ensure_fresh(name, target_token, is_current=False)
            if fresh:
                target_token = fresh
            else:
                print(f'Warning: "{name}" token is expired and could not be '
                      f"refreshed ({err}). Claude Code may prompt you to log in.",
                      file=sys.stderr)
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


# ── usage & spend-aware switching ──────────────────────────────────────────────

def account_spend(
    name: str, config: Config, *, use_cache: bool = True
) -> tuple[Spend | None, str | None]:
    """Resolve the live spend for a profile, refreshing its token if expired.

    For the active profile the freshest credential (Claude Code's slot) is used;
    for others the saved backup is used. An expired token is refreshed from its
    stored refresh token and the rotated credential is persisted, so usage can be
    read without switching accounts.

    Args:
        name: Profile name.
        config: Current config.
        use_cache: Whether to serve a recent cached usage report first.

    Returns:
        (spend, None) on success, or (None, message) describing why it failed.
    """
    if use_cache:
        raw = usage.cached_raw(name)
        if raw is not None:
            spend = usage.parse_spend(raw)
            if spend:
                return spend, None

    is_current = config.current == name
    blob = credentials.read_active() if is_current else credentials.read_backup(name)
    if not blob:
        return None, "no saved credential"

    blob, err = _ensure_fresh(name, blob, is_current=is_current)
    if not blob:
        return None, err

    token = usage.access_token(blob)
    if not token:
        return None, "unreadable credential"
    try:
        raw = usage.fetch(token)
    except usage.RateLimited:
        return None, "rate limited — try again shortly"

    if raw is None:
        return None, "usage unavailable"
    usage.store_raw(name, raw)
    spend = usage.parse_spend(raw)
    if not spend:
        return None, "no spend data reported"
    return spend, None


def _ensure_fresh(
    name: str, blob: str, *, is_current: bool
) -> tuple[str | None, str | None]:
    """Refresh an expired credential and persist the rotated token.

    Only the active account is kept refreshed by Claude Code; saved backups go
    stale. This refreshes a stale token on demand and writes it back so the next
    switch hands Claude Code a live token instead of a dead one. Respects a
    post-429 backoff so alt never starves Claude Code's own refresh.

    Args:
        name: Profile name.
        blob: The current (possibly expired) credential blob.
        is_current: Whether this profile is the active account.

    Returns:
        (fresh_blob, None) on success, or (None, message) if it can't refresh.
    """
    if not usage.is_expired(blob):
        return blob, None
    if usage.in_refresh_backoff(name):
        return None, "token expired; refresh rate-limited — try again later"

    try:
        refreshed = usage.refresh_blob(blob)
    except usage.RateLimited:
        usage.mark_rate_limited(name)
        return None, "refresh rate-limited — backing off so Claude Code can refresh"
    if not refreshed:
        return None, f"token expired — run `alt add {name}` to re-save after login"

    usage.clear_backoff(name)
    credentials.write_backup(name, refreshed)
    if is_current:
        credentials.write_active(refreshed)
    return refreshed, None


def _effective_threshold(meta: ProfileMeta, config: Config) -> str:
    """Describe a profile's switch threshold for display."""
    if meta.switch_at_dollars is not None:
        return f"${meta.switch_at_dollars:,.2f}"
    if meta.switch_at_percent is not None:
        return f"{meta.switch_at_percent:.0f}%"
    return f"{config.default_switch_at_percent:.0f}% (default)"


def over_threshold(spend: Spend, meta: ProfileMeta, config: Config) -> bool:
    """Report whether a profile's spend has reached its switch threshold.

    Args:
        spend: The profile's current spend.
        meta: The profile's metadata (per-account overrides).
        config: Current config (holds the global default).

    Returns:
        True if exhausted or at/over the configured threshold.
    """
    if spend.exhausted:
        return True
    if meta.switch_at_dollars is not None:
        return spend.used_usd >= meta.switch_at_dollars
    pct = meta.switch_at_percent
    if pct is None:
        pct = config.default_switch_at_percent
    return spend.percent >= pct


def recommend_target(config: Config) -> str | None:
    """Find the next profile in priority order that still has headroom.

    Starts after the current profile and wraps around. Profiles whose usage
    can't be read (expired backups, network errors) are skipped.

    Args:
        config: Current config.

    Returns:
        A profile name with headroom, or None if none qualifies.
    """
    order = config.priority or list(config.profiles)
    if not order:
        return None
    cur = config.current
    start = order.index(cur) + 1 if cur in order else 0
    for name in order[start:] + order[:start]:
        if name == cur or name not in config.profiles:
            continue
        spend, _ = account_spend(name, config)
        if spend and not over_threshold(spend, config.profiles[name], config):
            return name
    return None


def _format_spend(spend: Spend) -> str:
    """Render a Spend as a one-line summary."""
    limit = f"${spend.limit_usd:,.2f}" if spend.limit_usd is not None else "—"
    parts = [f"${spend.used_usd:,.2f} / {limit}", f"({spend.percent:.0f}%)"]
    if spend.severity:
        parts.append(f"⚠ {spend.severity}")
    if spend.remaining_usd is not None:
        parts.append(f"${spend.remaining_usd:,.2f} left")
    return "  ".join(parts)


def usage_report(name: str | None) -> None:
    """Print live spend for one profile (default: the active profile).

    Args:
        name: Profile name, or None for the active profile.
    """
    config = load()
    if name is None:
        name = config.current
        if not name:
            print("No active profile. Run: alt add <name>")
            return
    if name not in config.profiles:
        _no_such_profile(name, config)

    spend, err = account_spend(name, config, use_cache=False)
    email = config.profiles[name].email
    if spend:
        print(f"{name}  ({email})")
        print(f"  {_format_spend(spend)}")
        print(f"  switch at {_effective_threshold(config.profiles[name], config)}")
    else:
        print(f"{name}  ({email})\n  {err}")


def usage_all() -> None:
    """Print live spend for every saved profile, one line each."""
    config = load()
    if not config.profiles:
        print("No profiles saved. Run: alt add <name>")
        return

    order = [n for n in config.priority if n in config.profiles]
    order += [n for n in config.profiles if n not in order]

    print("Usage:")
    for name in order:
        marker = "→" if name == config.current else " "
        spend, err = account_spend(name, config, use_cache=False)
        detail = _format_spend(spend) if spend else f"({err})"
        print(f"  {marker} {name:<10} {detail}")


def set_limit(
    name: str,
    *,
    percent: float | None = None,
    dollars: float | None = None,
    clear: bool = False,
) -> None:
    """Set, clear, or show a profile's switch threshold.

    With no percent/dollars/clear, prints the current setting. Setting one of
    percent or dollars clears the other (they are mutually exclusive).

    Args:
        name: Profile name.
        percent: Recommend switching at this spend percentage.
        dollars: Recommend switching at this many dollars spent.
        clear: Remove any per-account override (fall back to the global default).
    """
    config = load()
    if name not in config.profiles:
        _no_such_profile(name, config)
    meta = config.profiles[name]

    if not clear and percent is None and dollars is None:
        print(f"{name}: switch at {_effective_threshold(meta, config)}")
        return

    if clear:
        meta.switch_at_percent = None
        meta.switch_at_dollars = None
    elif dollars is not None:
        meta.switch_at_dollars = dollars
        meta.switch_at_percent = None
    else:
        meta.switch_at_percent = percent
        meta.switch_at_dollars = None

    save(config)
    print(f"{name}: switch at {_effective_threshold(meta, config)}")


def set_default_limit(percent: float) -> None:
    """Set the global default switch threshold (percent).

    Args:
        percent: Default spend percentage at which to recommend switching.
    """
    config = load()
    config.default_switch_at_percent = percent
    save(config)
    print(f"Default: switch at {percent:.0f}%")


def guard() -> None:
    """UserPromptSubmit hook: recommend a switch when the active account is spent.

    Reads (and discards) the hook payload on stdin. If the active account is at
    or over its switch threshold, emits a ``decision: block`` JSON so Claude Code
    erases the prompt and shows the recommendation to the user — who accepts by
    switching, then re-sends. Fails open: any error leaves the prompt untouched.
    """
    try:
        sys.stdin.read()
    except Exception:
        pass

    try:
        config = load()
        cur = config.current
        if not cur or cur not in config.profiles:
            return

        spend, _ = account_spend(cur, config)
        if not spend or not over_threshold(spend, config.profiles[cur], config):
            return

        limit = f"${spend.limit_usd:,.2f}" if spend.limit_usd is not None else "limit"
        head = (f"⚠ Account '{cur}' has reached its limit "
                f"(${spend.used_usd:,.2f}/{limit}, {spend.percent:.0f}%).")

        target = recommend_target(config)
        if target:
            tspend, _ = account_spend(target, config)
            left = (f" (${tspend.remaining_usd:,.2f} left)"
                    if tspend and tspend.remaining_usd is not None else "")
            reason = (f"{head}\nRecommended: switch to '{target}'{left}.\n"
                      f"Accept with:  !alt switch {target}   (or !alt next)\n"
                      f"Then re-send your message.")
        else:
            reason = (f"{head}\nNo other saved account has headroom — "
                      f"run `!alt usage --all` to review.")

        print(json.dumps({"decision": "block", "reason": reason}))
    except Exception:
        return
