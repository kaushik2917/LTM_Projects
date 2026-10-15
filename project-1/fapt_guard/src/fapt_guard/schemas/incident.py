"""Incident schema."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
Status = Literal["pre_attack", "active", "investigating", "contained", "prevented", "closed"]


class Incident(BaseModel):
    incident_id: str
    title: str = "Untitled incident"
    status: Status = "active"
    severity: Severity = "medium"
    created_at: datetime
    updated_at: datetime
    hosts: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    primary_host: str | None = None
    primary_user: str | None = None
    current_tactic: str | None = None
    current_technique_id: str | None = None
    current_technique_name: str | None = None
    simulated: bool = True
