#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing alt..."

pipx install -e "$SCRIPT_DIR" --force --quiet

COMMANDS_DIR="$HOME/.claude/commands"
mkdir -p "$COMMANDS_DIR"
cp "$SCRIPT_DIR/commands/alt.md" "$COMMANDS_DIR/alt.md"

echo "Done."
echo ""
echo "  alt add <name>        save the current login as a profile"
echo "  alt switch <name>     switch accounts"
echo "  alt priority n1 n2    set fallback order"
echo "  alt run <name>        launch claude in an isolated session"
echo "  /alt <name>           switch from inside Claude Code"
