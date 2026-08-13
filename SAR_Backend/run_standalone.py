from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _set_defaults(base: Path) -> None:
    os.environ.setdefault("ENV", "standalone")
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{(base / 'data' / 'sar.db').as_posix()}")
    os.environ.setdefault("TASK_EXECUTION_MODE", "inline")
    os.environ.setdefault("STORAGE_BACKEND", "local")
    os.environ.setdefault("RATE_LIMIT_REQUESTS", "0")
    os.environ.setdefault("LOCAL_STORAGE_DIR", str(base / "data" / "storage"))
    os.environ.setdefault("LOCAL_DATA_DIR", str(base / "data"))
    os.environ.setdefault("S3_BUCKET", "sar")
    os.environ.setdefault("FRONTEND_DIST_DIR", str(base / "frontend"))
    os.environ.setdefault("CORS_ALLOW_ORIGINS", "*")


def main() -> None:
    base = _base_dir()
    # Ensure PyInstaller onedir runtime can import local package `app`.
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    (base / "data").mkdir(parents=True, exist_ok=True)
    _set_defaults(base)
    port = int(os.environ.get("SAR_BACKEND_PORT", "8000"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
