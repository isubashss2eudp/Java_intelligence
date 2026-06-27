from __future__ import annotations

"""Audit logging service — append-only writes to the audit_logs table."""

import json
from typing import Optional

from sqlalchemy.orm import Session

from src.platform.models.audit import AuditLog


def log(
    db:            Session,
    action:        str,
    user_id:       Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id:   Optional[str] = None,
    details:       Optional[dict] = None,
    ip_address:    Optional[str] = None,
    user_agent:    Optional[str] = None,
    commit:        bool = True,
) -> AuditLog:
    """
    Append a single audit log entry.

    Args:
        db:            SQLAlchemy session.
        action:        Action constant (e.g. AuditLog.Actions.LOGIN).
        user_id:       Acting user's ID (None for unauthenticated actions).
        resource_type: Type of affected resource (e.g. "repository").
        resource_id:   ID or name of the affected resource.
        details:       Dict of extra context serialised to JSON.
        ip_address:    Client IP address.
        user_agent:    Client user-agent string.
        commit:        If True, commit immediately (default). Set False when
                       the caller manages the transaction.

    Returns:
        The created AuditLog ORM instance.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=json.dumps(details, default=str) if details else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def get_logs(
    db:            Session,
    user_id:       Optional[int] = None,
    action:        Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id:   Optional[str] = None,
    offset:        int = 0,
    limit:         int = 50,
) -> tuple[list[AuditLog], int]:
    """
    Query audit logs with optional filters.

    Returns:
        (items, total) tuple.
    """
    q = db.query(AuditLog)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if resource_id:
        q = q.filter(AuditLog.resource_id == str(resource_id))

    total = q.count()
    items = q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return items, total
