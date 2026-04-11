"""AVOI Release Script — cross-platform (replaces release.sh)."""

import subprocess
import sys
import datetime


def main():
    if len(sys.argv) < 2:
        print("Usage: python release.py v0.1.0")
        sys.exit(1)

    version = sys.argv[1]
    if not version.startswith("v"):
        version = f"v{version}"

    print(f"Creating AVOI release {version}...")

    # Ensure we're on avoi/dev
    run("git", "checkout", "avoi/dev")

    # Run tests
    print("Running tests...")
    run("python3", "-m", "pytest", "avoi/tests/", "-q", check=False)

    # Merge to avoi/main
    run("git", "checkout", "avoi/main")
    run("git", "merge", "avoi/dev", "--no-ff", "-m", f"Release {version}")

    # Tag
    run("git", "tag", "-a", version, "-m", f"AVOI {version}")

    # Push
    run("git", "push", "origin", "avoi/main")
    run("git", "push", "origin", version)

    # Back to dev
    run("git", "checkout", "avoi/dev")

    print()
    print(f"✓ Released AVOI {version}")
    print("  Clients can update with: cd ~/avoi-agent && git pull")


def run(*args, check=True):
    result = subprocess.run(args, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error running: {' '.join(args)}")
        print(result.stderr)
        sys.exit(1)
    return result


if __name__ == "__main__":
    main()
