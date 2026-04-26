"""
AVOI CLI wrapper — the 'avoi' command.
This is the user-facing entry point.
It prints the AVOI banner, then launches the agent.
"""

import sys
import os

# Ensure the project root is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    """AVOI entry point."""
    from avoi.branding.banner import print_banner

    # Print AVOI branding
    print_banner()

    # Launch the agent CLI (same as the 'avoi' command)
    from avoi_cli.main import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
