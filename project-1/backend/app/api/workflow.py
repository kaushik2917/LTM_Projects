from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from typing import Literal
from app.api.research import ResponseContext, Unit
from app.services import workflow_service as service

router = APIRouter(prefix="/api/workflow", tags=["Incident workflow"])


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: ResponseContext
    previous_stage: str
    graph_integrity: Unit


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment_id: str
    action: str


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cutoff_timestamp: str
    task: Literal["technique", "stage"] = "technique"


def call(function, *args):
    try:
        return function(*args)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, "Train research models before running an assessment") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{incident_id}/graph")
def graph(incident_id: str, upto: int | None = Query(None, ge=0), cutoff_timestamp: str | None = None):
    return call(service.graph, incident_id, upto, cutoff_timestamp)


@router.get("/{incident_id}/analysis")
def analysis(incident_id: str, upto: int | None = Query(None, ge=0), cutoff_timestamp: str | None = None):
    return call(service.analysis, incident_id, upto, True, cutoff_timestamp)


@router.post("/{incident_id}/prediction")
def prediction(incident_id: str, request: PredictionRequest):
    return call(service.run_prediction, incident_id, request.cutoff_timestamp, True, request.task)


@router.post("/{incident_id}/verify")
def verify(incident_id: str):
    return call(service.verification, incident_id)


@router.post("/{incident_id}/report/export")
def export(incident_id: str):
    return call(service.export_report, incident_id)


@router.get("/{incident_id}/report")
def report(incident_id: str):
    return call(service.report, incident_id)


@router.post("/{incident_id}/preserve")
def preserve(incident_id: str):
    return call(service.preserve, incident_id)


@router.post("/{incident_id}/assessment")
def assessment(incident_id: str, request: AssessmentRequest):
    return call(service.assessment, incident_id, request.context.model_dump(), request.previous_stage, request.graph_integrity)


@router.post("/{incident_id}/simulate")
def simulate(incident_id: str, request: SimulationRequest):
    return call(service.simulate, incident_id, request.assessment_id, request.action)
