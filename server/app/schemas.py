"""Pydantic request/response schemas for the REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentBase(BaseModel):
    name: str
    role: str = ""
    system_prompt: str = ""
    model: str = "fake"
    tools: list[str] = Field(default_factory=list)
    interaction_rules: dict[str, Any] = Field(default_factory=dict)
    guardrails: dict[str, Any] = Field(default_factory=dict)


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    tools: list[str] | None = None
    interaction_rules: dict[str, Any] | None = None
    guardrails: dict[str, Any] | None = None


class AgentOut(AgentBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowBase(BaseModel):
    name: str
    description: str = ""
    graph_spec: dict[str, Any] = Field(default_factory=dict)
    template_source: str = ""


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph_spec: dict[str, Any] | None = None


class WorkflowOut(WorkflowBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RunRequest(BaseModel):
    input: str
    thread_id: str = "default"


class MessageOut(BaseModel):
    id: str
    run_id: str | None
    sender: str
    recipient: str
    channel: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class UsageOut(BaseModel):
    id: str
    agent: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

    class Config:
        from_attributes = True


class RunOut(BaseModel):
    id: str
    workflow_id: str | None
    thread_id: str
    status: str
    input: str
    output: str
    error: str
    started_at: datetime
    finished_at: datetime | None

    class Config:
        from_attributes = True


class RunDetail(RunOut):
    messages: list[MessageOut] = Field(default_factory=list)
    usage: list[UsageOut] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_tokens: int = 0
