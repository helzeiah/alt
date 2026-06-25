#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing alt..."

pipx install -e "$SCRIPT_DIR" --force --quiet

# Register the UserPromptSubmit guard hook in ~/.claude/settings.json, preserving
# any existing settings. Idempotent: skips if an `alt guard` hook already exists.
python3 - <<'PY'
import json, os
from pathlib import Path

path = Path.home() / ".claude" / "settings.json"
settings = {}
if path.exists():
    try:
        settings = json.loads(path.read_text())
    except Exception:
        print("  warning: ~/.claude/settings.json is not valid JSON; "
              "skipping hook install. Add it manually:")
        print('    "hooks": {"UserPromptSubmit": [{"hooks": '
              '[{"type": "command", "command": "alt guard"}]}]}')
        raise SystemExit(0)

hooks = settings.setdefault("hooks", {})
ups = hooks.setdefault("UserPromptSubmit", [])

def has_guard(groups):
    for g in groups:
        for h in g.get("hooks", []):
            if h.get("command") == "alt guard":
                return True
    return False

if has_guard(ups):
    print("  guard hook already installed")
else:
    ups.append({"hooks": [{"type": "command", "command": "alt guard"}]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2))
    print("  installed UserPromptSubmit guard hook")
PY

echo "Done."
echo ""
echo "  alt add <name>          save the current login as a profile"
echo "  alt switch <name>       switch accounts"
echo "  alt usage [--all]       show live spend for an account (or all)"
echo "  alt limit <name> ...    set the spend threshold for auto-recommend"
echo "  alt priority n1 n2      set fallback order"
echo "  alt run <name>          launch claude in an isolated session"
echo ""
echo "Inside Claude Code, run any of these token-free with a '!' prefix,"
echo "e.g.  !alt switch <name>   or   !alt usage --all"
echo ""
echo "The guard hook recommends switching when an account hits its limit."
echo "To remove it, delete the UserPromptSubmit entry in ~/.claude/settings.json."
