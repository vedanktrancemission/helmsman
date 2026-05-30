"""Workflow template catalog endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.templates import list_templates

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def templates():
    return list_templates()
