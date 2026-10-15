"""Common normalized evidence schema shared by every adapter and module."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ENTITY_TYPES = (
    "user",
    "host",
    "process",
    "file",
    "registry",
    "socket",
    "ip",
    "domain",
    "service",
    "artifact",
    "vulnerability",
    "other",
)

# Fields covered by the integrity hash. Anything that changes the meaning of an
# event must be listed here, otherwise tampering could go unnoticed.
_HASHED_FIELDS = (
    "evidence_id",
    "timestamp",
    "source",
    "host",
    "user",
    "subject_type",
    "subject",
    "action",
    "object_type",
    "object",
    "evidence_type",
    "attributes",
)


class Evidence(BaseModel):
    """A single normalized piece of digital evidence."""

    model_config = ConfigDict(extra="ignore")

    evidence_id: str
    incident_id: str | None = None
    timestamp: datetime
    ingested_at: datetime | None = None
    source: str
    host: str | None = None
    user: str | None = None
    subject_type: str = "other"
    subject: str = ""
    action: str
    object_type: str = "other"
    object: str = ""
    evidence_type: str
    artifact_class: str = "disk_artifacts"
    attributes: dict[str, Any] = Field(default_factory=dict)
    raw_event_ref: str | None = None
    integrity_hash: str | None = None
    simulated: bool = True
    # Simulation only: evidence that exists on the host but has not been
    # collected yet. It can be retrieved by active acquisition (AF-VoI).
    latent: bool = False

    def canonical_material(self) -> str:
        payload = {}
        for f in _HASHED_FIELDS:
            v = getattr(self, f)
            payload[f] = v.isoformat() if isinstance(v, datetime) else v
        return json.dumps(payload, sort_keys=True, default=str)

    def compute_hash(self) -> str:
        return hashlib.sha256(self.canonical_material().encode("utf-8")).hexdigest()

    def seal(self) -> "Evidence":
        """Compute and attach the integrity hash (done once at ingestion)."""
        self.integrity_hash = self.compute_hash()
        return self

    def verify_integrity(self) -> bool:
        return self.integrity_hash is not None and self.integrity_hash == self.compute_hash()

    def short(self) -> str:
        return f"{self.evidence_id} {self.source}:{self.subject}-{self.action}->{self.object}"
