"""
AttentionX – Application Entry Point
Run with: python run.py
Or: uvicorn attentionx.backend.main:app --reload --port 8000
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "attentionx.backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["attentionx"],
        log_level="info",
    )
