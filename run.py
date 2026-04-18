"""
AttentionX - Application Entry Point
Run with: python run.py
"""

import sys
import socket
import os
from pathlib import Path

import uvicorn

import sitecustomize  # noqa: F401
from backend.main import app as fastapi_app


CURRENT_DIR = Path(__file__).resolve().parent

# Keep the repository root importable so `backend.*` works in flat deployments.
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))


def _port_is_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True when a local TCP port does not already accept connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def _find_available_port(start_port: int, stop_port: int = 8100) -> int:
    """Find the first available port in a small local range."""
    for port in range(start_port, stop_port + 1):
        if _port_is_available(port):
            return port
    raise RuntimeError(f"No available port found between {start_port} and {stop_port}")

if __name__ == "__main__":
    preferred_port = int(os.getenv("PORT", "8000"))
    port = _find_available_port(preferred_port)

    if port != preferred_port:
        print(f"Port {preferred_port} is busy. Starting on port {port} instead.")

    uvicorn.run(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
    )
