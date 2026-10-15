from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    evidence_id: str
    incident_id: str

    timestamp: datetime

    source: Literal[
        "sysmon",
        "windows_event",
        "firewall",
        "dns",
        "network",
        "process",
        "authentication",
        "memory",
        "simulated",
    ]

    host: str
    user: str | None = None

    subject_type: Literal[
        "process",
        "file",
        "user",
        "host",
        "ip",
        "socket",
        "registry",
        "memory",
        "other",
    ]

    subject: str

    action: str

    object_type: Literal[
        "process",
        "file",
        "user",
        "host",
        "ip",
        "socket",
        "registry",
        "memory",
        "other",
    ]

    object: str

    evidence_type: str

    attack_technique_id: str | None = None
    attack_technique_name: str | None = None

    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    integrity_hash: str | None = Field(default=None, pattern="^[0-9a-fA-F]{64}$")

    volatility: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)

    simulated: bool = True
