#!/usr/bin/env python
"""Test that the application can start without errors."""

import os
import sys

# Set required API key
os.environ["API_KEY"] = "test-key-123"

try:
    from genus.api.app import create_app

    print("Creating application...")
    app = create_app()

    print("✓ Application created successfully")
    print("✓ All imports working")
    print("✓ No syntax errors")
    print("\nApplication is ready to run!")
    print("To start the server: export API_KEY=your-key && python main.py")

    sys.exit(0)
except Exception as e:
    print(f"✗ Error creating application: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
