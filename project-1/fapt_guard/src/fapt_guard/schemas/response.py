"""Response-side schemas: survival profiles, counterfactuals, optimisation, autonomy."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ResponseAction(str, Enum):
    OBSERVE = "OBSERVE"
    INCREASE_MONITORING = "INCREASE_MONITORING"
    FORCE_MFA = "FORCE_MFA"
    RESTRICT_SERVICE = "RESTRICT_SERVICE"
    BLOCK_SOURCE = "BLOCK_SOURCE"
    DISABLE_ACCOUNT = "DISABLE_ACCOUNT"
    NETWORK_ISOLATE = "NETWORK_ISOLATE"
    KILL_PROCESS = "KILL_PROCESS"
    STOP_SERVICE = "STOP_SERVICE"
    SHUTDOWN_HOST = "SHUTDOWN_HOST"
    REIMAGE_HOST = "REIMAGE_HOST"


class AutonomyLevel(str, Enum):
    AUTO_EXECUTE = "AUTO_EXECUTE"
    AUTO_EXECUTE_IN_SIMULATION = "AUTO_EXECUTE_IN_SIMULATION"
    RECOMMEND = "RECOMMEND"
    ANALYST_APPROVAL = "ANALYST_APPROVAL"
    COLLECT_MORE_EVIDENCE = "COLLECT_MORE_EVIDENCE"


class ArtifactSurvival(BaseModel):
    artifact_id: str
    artifact_class: str
    host: str | None
    utility: float
    action_survival: float          # P(survive | action) before attacker behaviour
    attacker_destruction: float     # P(destroyed by attacker | action, state)
    preserved_coverage: float
    effective_survival: float
    drivers: list[str] = Field(default_factory=list)


class SurvivalProfile(BaseModel):
    action: str
    target_host: str | None
    survival_by_class: dict[str, float] = Field(default_factory=dict)
    artifacts: list[ArtifactSurvival] = Field(default_factory=list)
    original_utility: float = 0.0
    expected_preserved_utility: float = 0.0
    elc: float = 0.0
    ers: float = 1.0
    ers_without_preservation: float = 1.0
    model_version: str = ""


class CyberFuture(BaseModel):
    residual_attack_risk: float
    worst_case_attack_risk: float
    lateral_movement_probability: float
    propagation_probability: float
    likely_next_technique: str | None
    affected_systems: list[str] = Field(default_factory=list)
    attacker_adaptation: str = ""
    risk_by_scenario: dict[str, float] = Field(default_factory=dict)


class ForensicFuture(BaseModel):
    expected_ers: float
    worst_case_ers: float
    elc: float
    survival_by_class: dict[str, float] = Field(default_factory=dict)
    lost_volatile_artifacts: list[str] = Field(default_factory=list)
    evidence_trust_after: float = 1.0
    investigative_capability: float = 1.0
    ers_by_scenario: dict[str, float] = Field(default_factory=dict)


class Counterfactual(BaseModel):
    action: str
    label: str
    target: str | None
    cyber_future: CyberFuture
    forensic_future: ForensicFuture
    business_impact: float
    response_cost: float
    reversible: bool
    downtime_minutes: float
    opportunity_cost: float
    twin_after: dict = Field(default_factory=dict)


class ActionEvaluation(BaseModel):
    action: str
    label: str
    target: str | None
    attack_risk: float
    worst_case_attack_risk: float
    evidence_loss: float
    ers: float
    worst_case_ers: float
    business_impact: float
    response_cost: float
    uncertainty: float
    opportunity_cost: float
    objective_score: float
    weighted_components: dict[str, float] = Field(default_factory=dict)
    feasible: bool = True
    violations: list[str] = Field(default_factory=list)
    reversible: bool = True
    rank: int = 0


class OptimizationResult(BaseModel):
    best_action: str
    best_target: str | None
    evaluations: list[ActionEvaluation]
    weights: dict[str, float]
    rationale: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    tie_break: str | None = None

    def evaluation(self, action: str) -> ActionEvaluation | None:
        return next((e for e in self.evaluations if e.action == action), None)

    @property
    def best(self) -> ActionEvaluation:
        return self.evaluation(self.best_action)  # type: ignore[return-value]


class AutonomyDecision(BaseModel):
    decision: AutonomyLevel
    action: str
    target: str | None
    reasons: list[str] = Field(default_factory=list)
    triggered_rules: list[str] = Field(default_factory=list)
    inputs: dict[str, float | bool | int | str] = Field(default_factory=dict)


class ResponseExecution(BaseModel):
    action: str
    target: str | None
    status: str
    simulated: bool
    provider: str
    timestamp: datetime
    details: dict = Field(default_factory=dict)


class PreventiveRecommendation(BaseModel):
    action: str
    label: str
    target: str | None
    risk_reduction: float
    business_impact: float
    objective_score: float
    reason: str


class PreventionPlan(BaseModel):
    triggered: bool
    attack_probability: float
    recommendations: list[PreventiveRecommendation] = Field(default_factory=list)
    selected: PreventiveRecommendation | None = None
    prevented: bool = False
    status_reason: str = ""
