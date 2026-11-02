"""Content-based import choices shared by the desktop upload endpoints."""
from threading import RLock
from typing import Literal

from fastapi import HTTPException

DuplicateAction = Literal["ask", "reuse", "import", "update"]
# Desktop uploads run in one backend process. Serialize the check and insert so
# concurrent imports cannot both bypass the prompt.
import_lock = RLock()


def reuse_duplicate(existing, action: DuplicateAction) -> bool:
    if existing is None or action == "import":
        return False
    if action in ("reuse", "update"):
        return True
    raise HTTPException(409, detail={
        "code": "duplicate_file",
        "message": "文件内容已存在，请选择使用原本记录、作为副本导入或更新信息导入。",
        "existing": {"id": str(existing.id), "name": existing.name},
    })
