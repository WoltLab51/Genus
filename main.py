#!/usr/bin/env python
"""Start the GENUS API server."""

import os
import sys
import uvicorn

# Ensure API_KEY is set
if "API_KEY" not in os.environ:
    print("Error: API_KEY environment variable is required")
    print("Example: export API_KEY=your-secret-key")
    sys.exit(1)

if __name__ == "__main__":
    uvicorn.run(
        "genus.api.app:create_app",
        host="0.0.0.0",
        port=8000,
        factory=True,
        log_level="info"
    )
