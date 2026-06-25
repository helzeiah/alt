"""Live account usage via Claude's OAuth endpoints.

Reads dollar-denominated spend for a Claude account using the same OAuth
credential Claude Code stores — no separate Admin/Analytics API key. Also
refreshes an expired access token from its stored refresh token, so usage can
be read for any saved profile without switching to it first.

Endpoints (undocumented; reverse-engineered, used by Claude Code itself):
  GET  https://api.anthropic.com/api/oauth/usage      — current spend/limits
  POST https://console.anthropic.com/v1/oauth/token   — refresh access token
"""
import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from alt.paths import alt_dir, alt_usage_cache_path

_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_BETA = "oauth-2025-04-20"
_CACHE_TTL = 60  # seconds; the usage endpoint rate-limits frequent polling
_REFRESH_BACKOFF_S = 1800  # after a token-endpoint 429, leave it alone this long
_TIMEOUT = 8.0

_ua_cache: str | None = None


class RateLimited(Exception):
    """Raised when an OAuth endpoint returns HTTP 429."""


@dataclass
class Spend:
    """Normalized spend snapshot for one account."""
    used_usd: float
    limit_usd: float | None
    percent: float
    severity: str | None       # e.g. "critical", or None
    remaining_usd: float | None
    enabled: bool
    disabled_reason: str | None

    @property
    def exhausted(self) -> bool:
        """Whether the account is out of quota regardless of any user threshold."""
        if not self.enabled or self.disabled_reason:
            return True
        if self.remaining_usd is not None and self.remaining_usd <= 0:
            return True
        return self.percent >= 100


def user_agent() -> str:
    """Return the User-Agent the OAuth endpoints expect.

    Both endpoints rate-limit aggressively (HTTP 429) without a claude-code
    User-Agent. The Claude Code version is resolved once and cached.

    Returns:
        A "claude-code/<version>" string.
    """
    global _ua_cache
    if _ua_cache is None:
        ver = "2.1.0"
        try:
            out = subprocess.run(
                ["claude", "--version"], capture_output=True, text=True, timeout=5
            ).stdout
            for tok in out.split():
                if tok and tok[0].isdigit() and "." in tok:
                    ver = tok
                    break
        except (OSError, subprocess.SubprocessError):
            pass
        _ua_cache = f"claude-code/{ver}"
    return _ua_cache


# ── credential blob helpers ──────────────────────────────────────────────────

def access_token(blob: str) -> str | None:
    """Extract the access token from a stored credential blob.

    Args:
        blob: Raw credential JSON as stored by Claude Code / alt.

    Returns:
        The access token, or None if the blob can't be parsed.
    """
    try:
        return json.loads(blob)["claudeAiOauth"]["accessToken"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def is_expired(blob: str, *, skew_s: int = 60) -> bool:
    """Report whether a credential blob's access token has expired.

    Args:
        blob: Raw credential JSON.
        skew_s: Treat tokens expiring within this many seconds as expired.

    Returns:
        True if expired, unparseable, or missing an expiry.
    """
    try:
        exp_ms = json.loads(blob)["claudeAiOauth"]["expiresAt"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return True
    return exp_ms / 1000 <= time.time() + skew_s


# ── network ──────────────────────────────────────────────────────────────────

def refresh_blob(blob: str) -> str | None:
    """Mint a fresh access token from a blob's refresh token.

    Reconstructs the full credential blob, preserving every non-token field
    (scopes, subscriptionType, rateLimitTier, ...) and updating only the access
    token, refresh token (it rotates), and expiry.

    Args:
        blob: Raw credential JSON containing a valid refresh token.

    Returns:
        The new credential JSON string, or None if the refresh token is
        missing/invalid.

    Raises:
        RateLimited: The token endpoint returned HTTP 429.
    """
    try:
        data = json.loads(blob)
        oauth = data["claudeAiOauth"]
        refresh_token = oauth["refreshToken"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None

    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": _CLIENT_ID,
    }).encode()
    req = urllib.request.Request(_TOKEN_URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "User-Agent": user_agent(),
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            tok = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited()
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    new_access = tok.get("access_token")
    if not new_access:
        return None
    oauth["accessToken"] = new_access
    if tok.get("refresh_token"):
        oauth["refreshToken"] = tok["refresh_token"]
    if tok.get("expires_in"):
        oauth["expiresAt"] = int(time.time() * 1000) + int(tok["expires_in"]) * 1000
    return json.dumps(data)


def fetch(token: str) -> dict | None:
    """Fetch the raw usage report for an access token.

    Args:
        token: A valid OAuth access token.

    Returns:
        The parsed usage JSON, or None on network/parse error.

    Raises:
        RateLimited: The usage endpoint returned HTTP 429.
    """
    req = urllib.request.Request(_USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": _BETA,
        "User-Agent": user_agent(),
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited()
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def parse_spend(raw: dict) -> Spend | None:
    """Normalize a raw usage report into a Spend.

    Prefers the stable ``spend`` block; falls back to ``extra_usage`` for
    accounts that report only the legacy shape.

    Args:
        raw: A usage report from :func:`fetch`.

    Returns:
        A Spend, or None if no recognized spend data is present.
    """
    spend = raw.get("spend")
    if isinstance(spend, dict) and spend.get("used"):
        used = _money(spend.get("used"))
        limit = _money(spend.get("limit"))
        remaining = None if limit is None else round(limit - used, 2)
        return Spend(
            used_usd=used,
            limit_usd=limit,
            percent=float(spend.get("percent", 0)),
            severity=spend.get("severity"),
            remaining_usd=remaining,
            enabled=bool(spend.get("enabled", True)),
            disabled_reason=spend.get("disabled_reason"),
        )

    extra = raw.get("extra_usage")
    if isinstance(extra, dict) and extra.get("monthly_limit") is not None:
        used = float(extra.get("used_credits") or 0) / 100
        limit = float(extra["monthly_limit"]) / 100
        return Spend(
            used_usd=round(used, 2),
            limit_usd=round(limit, 2),
            percent=float(extra.get("utilization") or 0),
            severity=None,
            remaining_usd=round(limit - used, 2),
            enabled=bool(extra.get("is_enabled", True)),
            disabled_reason=extra.get("disabled_reason"),
        )
    return None


def _money(obj: object) -> float:
    """Convert a {amount_minor, exponent} money object to a float of major units."""
    if not isinstance(obj, dict):
        return 0.0
    minor = obj.get("amount_minor", 0)
    exp = obj.get("exponent", 2)
    return round(minor / (10 ** exp), 2)


# ── cache ────────────────────────────────────────────────────────────────────

def _read_cache() -> dict:
    try:
        return json.loads(alt_usage_cache_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cached_raw(name: str) -> dict | None:
    """Return a profile's cached usage report if still fresh.

    Args:
        name: Profile name.

    Returns:
        The cached usage JSON, or None if absent or older than the TTL.
    """
    entry = _read_cache().get(name)
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > _CACHE_TTL:
        return None
    return entry.get("raw")


def store_raw(name: str, raw: dict) -> None:
    """Cache a profile's usage report.

    Args:
        name: Profile name.
        raw: The usage JSON to cache.
    """
    cache = _read_cache()
    cache[name] = {"ts": time.time(), "raw": raw}
    path = alt_usage_cache_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache), encoding="utf-8")
    tmp.replace(path)


# ── refresh backoff ────────────────────────────────────────────────────────────
# The token endpoint rate-limits hard, and Claude Code shares that limit to keep
# the active account refreshed. After a 429 we leave the endpoint alone for a
# while so alt never starves Claude Code's own refresh (which would force a login).

def _backoff_path():
    return alt_dir() / "refresh-backoff.json"


def in_refresh_backoff(name: str) -> bool:
    """Report whether a profile's token endpoint is in post-429 backoff.

    Args:
        name: Profile name.

    Returns:
        True if a 429 was seen within the backoff window.
    """
    try:
        data = json.loads(_backoff_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return time.time() - data.get(name, 0) < _REFRESH_BACKOFF_S


def mark_rate_limited(name: str) -> None:
    """Record that a profile's token endpoint returned 429.

    Args:
        name: Profile name.
    """
    path = _backoff_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data[name] = time.time()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def clear_backoff(name: str) -> None:
    """Clear a profile's backoff after a successful refresh.

    Args:
        name: Profile name.
    """
    path = _backoff_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if data.pop(name, None) is not None:
        path.write_text(json.dumps(data), encoding="utf-8")
