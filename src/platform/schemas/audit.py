from __future__ import annotations

"""Phase 9: Pydantic schemas — audit logs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id:            int
    user_id:       Optional[int]
    action:        str
    resource_type: Optional[str]
    resource_id:   Optional[str]
    details:       Optional[str]
    ip_address:    Optional[str]
    created_at:    datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items:  list[AuditLogResponse]
    total:  int
    offset: int
    limit:  int


class ChatRequest(BaseModel):
    query:         str
    repository_id: Optional[int] = None
    use_agents:    bool = True   # False = single RAG chain, True = multi-agent


class ChatResponse(BaseModel):
    answer:        str
    repository_id: Optional[int]
    used_agents:   bool
    sources:       list[str] = []
