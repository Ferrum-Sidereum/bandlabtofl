"""``python -m bl2flp`` entry point."""

from __future__ import annotations

import sys

from .cli import main as cli_main


def main() -> int:
    if len(sys.argv) == 1:
        from .gui import main as gui_main

        gui_main()
        return 0
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
