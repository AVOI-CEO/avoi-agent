"""AVOI startup banner."""


AVOI_BANNER = r"""
    ___ _    _____ ___
   /   | |  / / _ \\_ _|
  / /| | | / / / / | |
 / ___ | |/ / /_/ /| |
/_/  |_|___/\\____/|___|

  Autonomous AI Agent Platform
"""

def print_banner(version: str = ""):
    """Print the AVOI startup banner."""
    print(AVOI_BANNER)
    if version:
        print(f"  v{version}")
    print()
