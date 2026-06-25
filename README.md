# alt

Switch between multiple Claude Code accounts without re-authenticating, and see
live spend on each one — built for juggling several accounts (e.g. multiple
Enterprise seats, each with its own usage budget).

`alt` swaps the OAuth credential Claude Code uses, so switching is seamless: on
Linux the credential file is re-read per request (instant); on macOS the Keychain
cache expires within ~30s (no restart needed).

## Features

- **Named profiles** with a priority/fallback order
- **Instant switching** in place, or fully isolated side-by-side sessions (`alt run`)
- **Live spend per account** in dollars — read with your existing login, no Admin
  or Analytics API key (`alt usage`)
- **Spend-aware guard hook** — recommends switching when the active account hits
  its limit; you accept by switching (never silent)
- **Reads any account without switching** — refreshes an expired saved token on
  demand so `alt usage --all` works across every profile
- **macOS Keychain** + **Linux file** credential storage
- **Zero dependencies** — Python stdlib only

## Install

```bash
git clone git@github.com:helzeiah/alt.git
cd alt && ./install.sh
```

Requires Python ≥ 3.10 and [`pipx`](https://pipx.pypa.io/). `install.sh` registers
the `alt` CLI and merges a `UserPromptSubmit` guard hook into
`~/.claude/settings.json` (idempotent — your existing settings are preserved).

## Quick start

```bash
# log into an account in Claude Code, then save it:
alt add work1
# log into another account, then:
alt add work2

# set fallback order:
alt priority work1 work2

# switch:
alt switch work2

# check spend:
alt usage              # active account
alt usage --all        # every profile
```

Inside Claude Code, run any command **token-free** with a `!` prefix — it executes
in the session shell with no model turn:

```
!alt switch work2
!alt usage --all
```

## Commands

| Command | Description |
| --- | --- |
| `alt add <name>` | Save the current login as a named profile |
| `alt switch <name>` | Switch to a profile (heals an expired token first) |
| `alt next` | Switch to the next profile in priority order |
| `alt list` | List profiles, priority rank, and the active one |
| `alt current` | Show the active profile |
| `alt usage [<name>]` `[--all]` | Show live spend vs. limit for an account, or all |
| `alt limit <name> [--percent N \| --dollars N \| --clear]` | Set/clear a per-account switch threshold |
| `alt limit --default --percent N` | Set the global default threshold |
| `alt priority [n1 n2 …]` | Set or show the priority order |
| `alt run <name> [-- args]` | Launch Claude in an isolated `CLAUDE_CONFIG_DIR` session |
| `alt remove <name>` | Delete a profile and its saved credential |

## Auto-switch on limit

The guard hook checks the active account's spend before each message. When it
reaches the switch threshold, it **blocks the prompt** and recommends the next
account with headroom:

```
⚠ Account 'work1' has reached its limit ($300.00/$300.00, 100%).
Recommended: switch to 'work2' ($268.80 left).
Accept with:  !alt switch work2   (or !alt next)
Then re-send your message.
```

The default threshold is **100%** (only at the full limit). Lower it per account
with `alt limit work1 --percent 90` (or `--dollars 270`), or globally with
`alt limit --default --percent 90`.

## How it works

Claude Code stores an OAuth credential — on macOS in the Keychain
(`Claude Code-credentials`), on Linux in `~/.claude/.credentials.json`. `alt` keeps
a backup copy per profile (Keychain entry `alt-<name>` on macOS, base64 file
`~/.alt/credentials/<name>.enc` on Linux) and swaps the active credential when you
switch. Profile metadata and priority live in `~/.alt/config.json`.

Live spend comes from the OAuth usage endpoint (`/api/oauth/usage`) using your
existing access token. A saved account's access token is short-lived; when it has
expired, `alt` refreshes it from the stored refresh token and persists the
rotation, so any account can be read or switched to without a manual re-login. A
backoff after rate-limit responses keeps `alt` from interfering with Claude Code's
own token refresh.

## Multi-device

Credentials are local and machine-specific (they are not in the repo). On a new
machine: clone, `./install.sh`, then log into each account and `alt add <name>`
again. Your `~/.alt/` config and credentials are never overwritten by an update —
`git pull && ./install.sh` adds new functionality while preserving your accounts.

## Uninstall

```bash
pipx uninstall alt
# then remove the UserPromptSubmit "alt guard" entry from ~/.claude/settings.json
# and, optionally, the ~/.alt directory
```
