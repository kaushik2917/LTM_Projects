import json
from typing import Annotated, Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from app.datasets import DATA, rows, features, CONTEXT, AF_FEATURES, TRUST_FEATURES
from app.services import research_service as service
from app.services.attack_service import catalog

router = APIRouter(prefix="/api/research", tags=["Dataset research"])
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class DemonstrationRequest(BaseModel):
    cutoff_timestamp: str


class RevealRequest(BaseModel):
    prediction_id: str


@router.get("/prediction-benchmark")
def prediction_benchmark():
    from app.prediction_benchmark import report
    try:
        return report()
    except (ValueError, OSError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/prospective-prediction")
def prospective_prediction():
    from app.prospective_prediction import status
    try:
        return status()
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/prediction-benchmark/examples/{scenario_id}")
def prediction_benchmark_example(scenario_id: str):
    from app.prediction_benchmark import demonstration
    try:
        return demonstration(scenario_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/temporal-scenarios")
def temporal_scenarios():
    from app.temporal_experiment import scenarios
    try:
        return scenarios()
    except (ValueError, OSError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/temporal-scenarios/{scenario_id}/predict")
def temporal_demonstration(scenario_id: str, request: DemonstrationRequest):
    from app.temporal_experiment import demonstrate
    try:
        return demonstrate(scenario_id, request.cutoff_timestamp)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/temporal-scenarios/{scenario_id}/reveal")
def temporal_reveal(scenario_id: str, request: RevealRequest):
    from app.temporal_experiment import reveal
    try:
        return reveal(scenario_id, request.prediction_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/temporal-scenarios/{scenario_id}/report")
def temporal_report(scenario_id: str, request: RevealRequest):
    from app.temporal_experiment import demonstration_report
    try:
        return demonstration_report(scenario_id, request.prediction_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


class ImportRequest(BaseModel):
    filename: str
    limit: int = Field(100000, ge=1, le=1000000)


@router.post("/dataset/import")
def import_dataset(request: ImportRequest):
    from app.services.optc_service import import_optc
    root = (DATA / "optc").resolve()
    path = (root / request.filename).resolve()
    if path.parent != root or path.suffix not in (".gz", ".json", ".jsonl"):
        raise HTTPException(422, "Choose a .json, .jsonl or .gz file directly inside data/optc")
    if not path.is_file(): raise HTTPException(404, "Dataset file unavailable; place raw eCAR data in data/optc")
    try:
        result = import_optc(path, request.limit)
        from app.services.workflow_service import record
        record("RESEARCH", "dataset_import", result)
        return result
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/evaluations")
def evaluations():
    from app.services.metadata_service import model_report
    path = DATA / "models/evaluation_diagnostics.json"
    checks = DATA / "validation_report.json"
    return {"training": model_report(), "diagnostics": json.loads(path.read_text()) if path.exists() else None,
            "validation": json.loads(checks.read_text()) if checks.exists() else None}


@router.get("/future-prediction")
def future_prediction_evaluation():
    from app.services.future_prediction_service import evaluation_status
    return evaluation_status()


@router.post("/benchmark/run")
def run_benchmark():
    from app.services.benchmark_service import run_benchmark
    return run_benchmark()


@router.get("/examples")
def examples():
    try:
        return {"responses": features(rows("10")[0], CONTEXT),
                "anti-forensic": features(rows("11")[0], AF_FEATURES),
                "trust": features(rows("12")[0], TRUST_FEATURES),
                "purpose": "Dataset examples for interactive demonstration, not holdout evaluation"}
    except FileNotFoundError as exc:
        raise HTTPException(503, "Prepare the custom datasets first") from exc


class ResponseContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attack_stage: str
    technique_id: str
    attacker_intent: str
    asset_criticality: Unit
    baseline_attack_risk: Unit
    evidence_trust: Unit
    anti_forensic_risk: Unit
    prediction_uncertainty: Unit


class AntiForensicContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_prev_stage: str
    observed_current_stage: str
    current_technique_id: str
    attacker_intent: str
    evidence_trust: Unit
    graph_integrity_score: Unit


class TrustContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    missing_ratio: Unit
    timestamp_shift_seconds: Annotated[float, Field(allow_inf_nan=False)]
    edge_deleted: Literal[0, 1]
    fake_node: Literal[0, 1]
    fake_edge: Literal[0, 1]
    sensor_spoof: Literal[0, 1]
    duplicate_event: Literal[0, 1]
    contradiction_count: Annotated[int, Field(ge=0)]
    corroboration_count: Annotated[int, Field(ge=0)]
    source_reliability: Unit
    integrity_hash_valid: Literal[0, 1]
    sensor_health: Unit
    temporal_consistency: Unit
    graph_consistency: Unit
    corroboration_score: Unit


def invoke(function, context):
    try:
        return function(context.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/datasets")
def datasets():
    path = DATA / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {"datasets": []}
    report = DATA / "models" / "training_report.json"
    from app.services.optc_service import status
    return {**manifest, "optc": status(), "attack": {k: v for k, v in catalog().items() if k != "techniques"},
            "training": json.loads(report.read_text()) if report.exists() else None}


@router.post("/responses")
def responses(context: ResponseContext):
    return invoke(service.responses, context)


@router.post("/anti-forensic")
def anti_forensic(context: AntiForensicContext):
    return invoke(service.anti_forensic, context)


@router.post("/trust")
def trust(context: TrustContext):
    return invoke(service.trust, context)


@router.get("/benchmark")
def benchmark():
    path = DATA / "benchmark_report.json"
    if not path.exists():
        raise HTTPException(503, "Run python -m app.datasets evaluate first")
    return json.loads(path.read_text())


@router.get("/techniques/{technique_id}")
def technique(technique_id: str):
    entry = catalog()["techniques"].get(technique_id)
    if entry is None:
        raise HTTPException(404, "Technique unavailable in loaded catalog")
    return {"technique_id": technique_id, **entry}


@router.get("/optc/evidence")
def optc_evidence(incident: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    from app.services.optc_service import events
    return events(incident, limit, offset)


@router.get("/optc/graph")
def optc_graph(incident: str, limit: int = Query(1000, ge=1, le=5000)):
    from app.services.optc_service import graph
    return graph(incident, limit)
