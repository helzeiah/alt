"""Command-line interface. Parses arguments and delegates to switcher."""
import argparse
import sys

from alt import switcher
from alt.config import load, save


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alt",
        description="Manage multiple Claude Code accounts.",
    )
    sub = parser.add_subparsers(dest="cmd", metavar="command")
    sub.required = True

    p = sub.add_parser("add", help="Save the current login as a named profile.")
    p.add_argument("name", help="Profile name to create.")

    p = sub.add_parser("switch", help="Switch to a profile.")
    p.add_argument("name", help="Profile name to switch to.")

    p = sub.add_parser("list", help="List all profiles.")

    p = sub.add_parser("current", help="Show the active profile.")

    p = sub.add_parser("next", help="Switch to the next profile in priority order.")

    p = sub.add_parser("remove", help="Delete a profile and its saved credential.")
    p.add_argument("name", help="Profile name to remove.")

    p = sub.add_parser("priority", help="Set or show the priority order.")
    p.add_argument("names", nargs="*", metavar="name",
                   help="Profile names in priority order. Omit to show the current order.")

    p = sub.add_parser("run", help="Launch claude in an isolated session for a profile.")
    p.add_argument("name", help="Profile name to run as.")
    p.add_argument("args", nargs=argparse.REMAINDER,
                   help="Arguments forwarded to claude (use -- to separate).")

    args = parser.parse_args()

    match args.cmd:
        case "add":     switcher.add(args.name)
        case "switch":  switcher.switch(args.name)
        case "list":    _cmd_list()
        case "current": _cmd_current()
        case "next":    switcher.next_profile()
        case "remove":  switcher.remove(args.name)
        case "priority": _cmd_priority(args.names)
        case "run":
            claude_args = [a for a in args.args if a != "--"]
            switcher.run(args.name, claude_args)


def _cmd_list() -> None:
    """Print all profiles with priority rank and current marker."""
    config = load()

    if not config.profiles:
        print("No profiles saved. Run: alt add <name>")
        return

    priority = config.priority
    current = config.current

    ordered = [n for n in priority if n in config.profiles]
    unranked = [n for n in config.profiles if n not in priority]

    print("Profiles:")
    for i, name in enumerate(ordered, 1):
        p = config.profiles[name]
        marker = "→" if name == current else " "
        print(f"  {marker} [{i}] {name}  ({p.email})")

    for name in unranked:
        p = config.profiles[name]
        marker = "→" if name == current else " "
        print(f"  {marker}     {name}  ({p.email})")


def _cmd_current() -> None:
    """Print the active profile name and email."""
    config = load()
    if config.current and config.current in config.profiles:
        p = config.profiles[config.current]
        print(f"{config.current}  ({p.email})")
    else:
        print("No active profile. Run: alt add <name>")


def _cmd_priority(names: list[str]) -> None:
    """Set or display the priority order.

    Args:
        names: New priority order. If empty, prints the current order.
    """
    config = load()

    if not names:
        if not config.priority:
            print("No priority order set. Run: alt priority <name1> <name2> ...")
            return
        print("Priority order:")
        for i, name in enumerate(config.priority, 1):
            p = config.profiles.get(name)
            email = p.email if p else "unknown"
            print(f"  {i}. {name}  ({email})")
        return

    missing = [n for n in names if n not in config.profiles]
    if missing:
        print(f"Error: unknown profile(s): {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # Named profiles first; any not mentioned are appended at the end.
    rest = [n for n in config.profiles if n not in names]
    config.priority = names + rest
    save(config)

    print("Priority order set:")
    for i, name in enumerate(names, 1):
        p = config.profiles[name]
        print(f"  {i}. {name}  ({p.email})")
