from __future__ import annotations

"""Audit log router: /api/v1/audit  (admin only)"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.platform.auth import require_admin
from src.platform.database import get_db
from src.platform.models.user import User
from src.platform.schemas.audit import AuditLogListResponse, AuditLogResponse
from src.platform.services import get_audit_logs

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="List audit log entries (admin only)",
)
def list_audit(
    offset:        int            = Query(0, ge=0),
    limit:         int            = Query(100, ge=1, le=1000),
    user_id:       Optional[int]  = Query(None),
    action:        Optional[str]  = Query(None),
    resource_type: Optional[str]  = Query(None),
    resource_id:   Optional[str]  = Query(None),
    db:            Session        = Depends(get_db),
    _:             User           = Depends(require_admin),
) -> AuditLogListResponse:
    items, total = get_audit_logs(
        db,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        offset=offset,
        limit=limit,
    )
    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(i) for i in items],
        total=total,
        offset=offset,
        limit=limit,
    )
