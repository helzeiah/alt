Switch the active Claude Code account.

Based on $ARGUMENTS:
- A profile name → run `alt switch $ARGUMENTS`
- "next"         → run `alt next`
- "list"         → run `alt list`

Report the result. If the profile does not exist, run `alt list` to show
what is available.

On Linux the credential file is re-read per request, so the switch takes
effect on the next message. On macOS the keychain is cached for ~30 seconds,
so the switch takes effect automatically — no restart needed.
