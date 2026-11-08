"""Helpers for writing and reading the audit trail from API routes."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import Request

from app.api.dependencies import ApiDependencies
from app.audit.log import AuditEvent


def record_audit(
    request: Request,
    dependencies: ApiDependencies,
    action: str,
    resource_type: str,
    resource_id: object | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    """Record a write. The actor is a hash of the API key (or the client IP), never the key.

    A failing audit store must not turn a completed write into an error for the client, so the
    failure is logged loudly instead of raised.
    """
    try:
        dependencies.audit_log.record(
            AuditEvent(
                actor=getattr(request.state, "client_identity", "unknown"),
                action=action,
                resource_type=resource_type,
                resource_id=None if resource_id is None else str(resource_id),
                details=dict(details or {}),
                request_id=getattr(request.state, "request_id", None),
            )
        )
    except Exception:
        logging.getLogger("unmeet.audit").exception(
            "audit write failed", extra={"action": action, "resource_type": resource_type}
        )
