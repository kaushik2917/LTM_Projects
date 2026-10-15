"""Forensic-side schemas: trust, integrity, utility, preservation and VoI."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TrustAssessment(BaseModel):
    evidence_id: str
    trust: float
    prior: float
    components: dict[str, float] = Field(default_factory=dict)
    corroborated_by: list[str] = Field(default_factory=list)
    contradicted_by: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    suspicious: bool = False


class IntegrityFinding(BaseModel):
    kind: str
    severity: float
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)


class IntegrityReport(BaseModel):
    graph_integrity_score: float
    suspected_poisoning: bool
    suspicious_nodes: list[str] = Field(default_factory=list)
    suspicious_edges: list[str] = Field(default_factory=list)
    missing_relationships: list[str] = Field(default_factory=list)
    timeline_anomalies: list[str] = Field(default_factory=list)
    suspicious_evidence: list[str] = Field(default_factory=list)
    findings: list[IntegrityFinding] = Field(default_factory=list)
    penalty_breakdown: dict[str, float] = Field(default_factory=dict)

    def evidence_flags(self) -> dict[str, list[str]]:
        """Map evidence id -> list of finding kinds that implicate it."""
        out: dict[str, list[str]] = {}
        for f in self.findings:
            for eid in f.evidence_ids:
                out.setdefault(eid, []).append(f.kind)
        return out


class ForensicArtifact(BaseModel):
    """A preservable unit of evidence on a host or collector (grouped by class)."""

    artifact_id: str
    artifact_class: str
    label: str
    host: str | None
    location: str = "host"
    volatility: float
    evidence_ids: list[str] = Field(default_factory=list)
    trust: float = 1.0
    implicit: bool = False       # exists on the host but was not collected as an event
    tampered: bool = False
    preserved_coverage: float = 0.0


class UtilityScore(BaseModel):
    artifact_id: str
    artifact_class: str
    utility: float
    components: dict[str, float] = Field(default_factory=dict)


class CustodyRecord(BaseModel):
    record_id: str
    timestamp: datetime
    actor: str
    action: str
    artifact_id: str
    sha256: str
    location: str
    note: str = ""


class PreservationTask(BaseModel):
    artifact_id: str
    artifact_class: str
    label: str
    host: str | None
    destroy_probability: float
    utility: float
    volatility: float
    priority: float
    preservation_action: str
    threatened_by: list[str] = Field(default_factory=list)
    reason: str = ""


class PreservationRecord(BaseModel):
    task: PreservationTask
    status: str                 # preserved | simulated | failed | not_supported
    provider: str
    coverage: float
    sha256: str | None = None
    location: str | None = None
    custody: list[CustodyRecord] = Field(default_factory=list)
    timestamp: datetime | None = None


class VoICandidate(BaseModel):
    evidence: str
    artifact_class: str
    expected_information_gain: float
    collection_cost: float
    delay_risk: float
    voi: float
    already_collected: bool = False


class VoIResult(BaseModel):
    current_uncertainty: float
    current_entropy_bits: float
    recommended_evidence: str | None
    expected_information_gain: float = 0.0
    estimated_collection_cost: float = 0.0
    delay_risk: float = 0.0
    safe_to_wait: bool = True
    triggered: bool = False
    reason: str = ""
    candidates: list[VoICandidate] = Field(default_factory=list)
    acquired_evidence_ids: list[str] = Field(default_factory=list)
    uncertainty_after: float | None = None
