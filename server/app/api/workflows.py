"""Workflow CRUD, template instantiation, and run trigger."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Workflow
from app.db.session import get_db
from app.runtime.compiler import WorkflowSpecError, validate_spec
from app.runtime.executor import run_workflow
from app.schemas import RunOut, RunRequest, WorkflowCreate, WorkflowOut, WorkflowUpdate
from app.templates import get_template

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class InstantiateTemplate(BaseModel):
    template_key: str
    name: str | None = None


@router.get("", response_model=list[WorkflowOut])
def list_workflows(db: Session = Depends(get_db)):
    return db.query(Workflow).order_by(Workflow.created_at).all()


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    if payload.graph_spec:
        try:
            validate_spec(payload.graph_spec)
        except WorkflowSpecError as exc:
            raise HTTPException(422, str(exc)) from exc
    wf = Workflow(**payload.model_dump())
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


@router.post("/from-template", response_model=WorkflowOut, status_code=201)
def create_from_template(payload: InstantiateTemplate, db: Session = Depends(get_db)):
    tpl = get_template(payload.template_key)
    if not tpl:
        raise HTTPException(404, "template not found")
    wf = Workflow(
        name=payload.name or tpl["name"],
        description=tpl["description"],
        graph_spec=tpl["graph_spec"],
        template_source=tpl["key"],
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(404, "workflow not found")
    return wf


@router.patch("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(workflow_id: str, payload: WorkflowUpdate, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(404, "workflow not found")
    data = payload.model_dump(exclude_unset=True)
    if "graph_spec" in data and data["graph_spec"]:
        try:
            validate_spec(data["graph_spec"])
        except WorkflowSpecError as exc:
            raise HTTPException(422, str(exc)) from exc
    for key, value in data.items():
        setattr(wf, key, value)
    db.commit()
    db.refresh(wf)
    return wf


@router.post("/{workflow_id}/run", response_model=RunOut)
async def trigger_run(workflow_id: str, payload: RunRequest, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(404, "workflow not found")
    return await run_workflow(db, wf, payload.input, payload.thread_id)
