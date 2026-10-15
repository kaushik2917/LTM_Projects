"""Attack-side schemas: ATT&CK mappings and prediction outputs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TechniqueMapping(BaseModel):
    evidence_id: str
    technique_id: str
    technique_name: str
    tactic: str
    confidence: float
    rule_id: str
    supporting_evidence: list[str] = Field(default_factory=list)
    rationale: str = ""


class ScoredLabel(BaseModel):
    label: str               # technique id / tactic / intent key
    name: str = ""           # human-readable name
    probability: float
    tactic: str | None = None


class FeatureContribution(BaseModel):
    feature: str
    value: float
    contribution: float


class HostRisk(BaseModel):
    host: str
    attack_probability: float
    likely_attack_type: str
    likely_initial_technique: str
    contributions: list[FeatureContribution] = Field(default_factory=list)


class PreAttackPrediction(BaseModel):
    attack_probability: float
    likely_attack_type: str
    likely_target: str | None
    likely_initial_technique: str
    likely_initial_technique_name: str = ""
    confidence: float
    features: dict[str, float] = Field(default_factory=dict)
    contributions: list[FeatureContribution] = Field(default_factory=list)
    per_host: list[HostRisk] = Field(default_factory=list)
    model_version: str = ""
    alert: bool = False


class ProgressionPrediction(BaseModel):
    current_tactic: str | None
    current_technique_id: str | None
    current_technique_name: str | None
    observed_techniques: list[str] = Field(default_factory=list)
    next_tactic: str | None
    next_tactic_distribution: list[ScoredLabel] = Field(default_factory=list)
    next_technique: ScoredLabel | None = None
    next_technique_distribution: list[ScoredLabel] = Field(default_factory=list)
    intent: str | None = None
    intent_distribution: list[ScoredLabel] = Field(default_factory=list)
    confidence: float = 0.0
    uncertainty: float = 1.0
    uncertainty_components: dict[str, float] = Field(default_factory=dict)
    evidence_importance: dict[str, float] = Field(default_factory=dict)
    signals: list[str] = Field(default_factory=list)
    backend: str = "baseline"
    model_version: str = ""


class AntiForensicBehavior(BaseModel):
    behavior: str
    label: str
    technique_id: str
    probability: float
    threatened_artifact_classes: list[str] = Field(default_factory=list)
    drivers: list[str] = Field(default_factory=list)


class AntiForensicPrediction(BaseModel):
    predictions: list[AntiForensicBehavior] = Field(default_factory=list)
    destroy_probability_by_class: dict[str, float] = Field(default_factory=dict)
    model_version: str = ""

    def top(self, n: int = 3) -> list[AntiForensicBehavior]:
        return sorted(self.predictions, key=lambda b: -b.probability)[:n]


class PredictionSet(BaseModel):
    """Calibrated (conformal / empirical) prediction set over next techniques."""

    coverage_target: float
    method: str
    threshold: float
    techniques: list[ScoredLabel] = Field(default_factory=list)
    tactics: list[str] = Field(default_factory=list)
    set_size: int = 0
    acceptable: bool = True
    reasons: list[str] = Field(default_factory=list)

    @property
    def names(self) -> list[str]:
        return [t.name for t in self.techniques]
