"""PyInstaller entry point for the headless render CLI."""

from outreachos_backend.rendering.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
