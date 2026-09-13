"""Standalone distribution entry point; scientific UI remains shared with Jana."""
import sys
from phase_studio.version import VERSION


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return 0
    from phase_studio.app import main as run_application
    return run_application()


if __name__ == "__main__":
    raise SystemExit(main())
