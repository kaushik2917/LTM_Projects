from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Incident(BaseModel):
    incident_id: str
    title: str

    severity: Literal[
        "low",
        "medium",
        "high",
        "critical"
    ]

    status: Literal[
        "active",
        "investigating",
        "contained",
        "closed"
    ]

    detected_at: datetime

    affected_host: str
    affected_user: str | None = None

    current_tactic: str
    current_technique_id: str
    current_technique_name: str

    evidence_count: int

    simulated: bool = True