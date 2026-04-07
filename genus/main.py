"""
GENUS API — Production entry point

Usage:
    uvicorn genus.main:app

    or:

    GENUS_API_KEY=secret uvicorn genus.main:app --host 0.0.0.0 --port 8000

Environment variables:
    GENUS_API_KEY   Required. API key for Bearer authentication.
"""

import os

from genus.api.app import create_app

_api_key = os.environ.get("GENUS_API_KEY", "")
if not _api_key:
    raise RuntimeError(
        "GENUS_API_KEY environment variable is not set. "
        "Set it before starting the API: GENUS_API_KEY=<key> uvicorn genus.main:app"
    )

app = create_app(api_key=_api_key, use_lifespan=True)
