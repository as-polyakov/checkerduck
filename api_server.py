#!/usr/bin/env python
"""
Entry point for running the API server
"""
import uvicorn
from checkerduck.api.server import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload during development
        log_level="info"
    )

