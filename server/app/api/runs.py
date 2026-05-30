"""Run listing and detail endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Run
from app.db.session import get_db
from app.schemas import MessageOut, RunDetail, RunOut, UsageOut

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db), limit: int = 50):
    return db.query(Run).order_by(Run.started_at.desc()).limit(limit).all()


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    messages = sorted(run.messages, key=lambda m: m.created_at)
    total_cost = round(sum(u.cost_usd for u in run.usage), 6)
    total_tokens = sum(u.prompt_tokens + u.completion_tokens for u in run.usage)
    detail = RunDetail.model_validate(run)
    detail.messages = [MessageOut.model_validate(m) for m in messages]
    detail.usage = [UsageOut.model_validate(u) for u in run.usage]
    detail.total_cost_usd = total_cost
    detail.total_tokens = total_tokens
    return detail
