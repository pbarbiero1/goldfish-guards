"""goldfish-guards CLI — subcommand dispatch.

Each guard is a subcommand with its own argparse; this file only routes.
"""

import sys

from goldfish_guards import __version__

USAGE = """\
usage: goldfish-guards <command> [options]

commands:
  fold-completeness   A finding is FOLDED only when every target it names shows a diff.
  secret-scan         Standing secret-scanner: live-value, placement, token-shape.

options:
  -h, --help          show this message
  -V, --version       show version
"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-V", "--version"):
        print(f"goldfish-guards {__version__}")
        return 0
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if not argv:
        print(USAGE, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "fold-completeness":
        from goldfish_guards import fold_completeness

        return fold_completeness.main(rest)
    if cmd == "secret-scan":
        from goldfish_guards import secret_scan

        return secret_scan.main(rest)
    print(f"unknown command: {cmd}\n\n{USAGE}", file=sys.stderr)
    return 2


def main_entry():  # console_scripts wants a no-arg callable that exits
    raise SystemExit(main())
