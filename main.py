"""Main entry point for GENUS application."""
import uvicorn
import sys
from genus.api import create_app_with_auth


def main():
    """Start the GENUS application server."""
    try:
        app = create_app_with_auth()
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
