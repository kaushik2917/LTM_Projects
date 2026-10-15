"""Forensic Safety Certificate schema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    evidence_id: str
    sha256: str | None
    trust: float
    integrity_verified: bool


class HumanOverride(BaseModel):
    analyst: str
    timestamp: datetime
    original_action: str
    original_decision: str
    new_action: str | None
    new_decision: str
    justification: str


class ForensicSafetyCertificate(BaseModel):
    certificate_id: str
    incident_id: str
    issued_at: datetime
    simulation_mode: bool

    recommended_action: str
    recommended_target: str | None
    autonomy_decision: str
    autonomy_reasons: list[str] = Field(default_factory=list)
    action_reversible: bool

    prediction: dict = Field(default_factory=dict)
    prediction_coverage: float
    prediction_set: list[str] = Field(default_factory=list)
    prediction_uncertainty: float
    prediction_confidence: float

    evidence_trust: float
    graph_integrity: float
    suspected_poisoning: bool

    expected_ers: float
    worst_case_ers: float
    residual_attack_risk: float
    worst_case_attack_risk: float
    business_impact: float

    supporting_evidence: list[str] = Field(default_factory=list)
    input_evidence: list[EvidenceReference] = Field(default_factory=list)
    preserved_artifacts: list[dict] = Field(default_factory=list)
    actions_evaluated: list[dict] = Field(default_factory=list)
    counterfactual_outcomes: list[dict] = Field(default_factory=list)
    active_acquisition: dict = Field(default_factory=dict)

    model_versions: dict[str, str] = Field(default_factory=dict)
    config_fingerprint: str = ""

    human_override: HumanOverride | None = None
    previous_certificate_hash: str | None = None
    certificate_hash: str | None = None
