import hmac
import json
import os
import threading
import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.defense import evidence, incidents, pipeline, responses, store, verification
from app.defense.knowledge import defensive_mapping

router = APIRouter(prefix="/api/defense", tags=["Real-time defense"])

Mode = Literal["LIVE", "LAB", "REPLAY"]
Format = Literal["canonical", "sysmon", "windows_security", "wazuh", "ecar"]


class Bucket:
    """Token-bucket rate limit for ingestion."""
    def __init__(self):
        self.lock = threading.Lock()
        self.tokens = None
        self.updated = time.monotonic()

    def take(self, amount):
        settings = store.config()["ingestion"]
        with self.lock:
            current = time.monotonic()
            capacity = settings["rate_limit_burst"]
            self.tokens = capacity if self.tokens is None else min(capacity, self.tokens + (current - self.updated) * settings["rate_limit_events_per_second"])
            self.updated = current
            if amount > self.tokens:
                return False
            self.tokens -= amount
            return True


BUCKET = Bucket()


def token_check(variable, authorization, required):
    expected = os.environ.get(variable)
    if not expected:
        if required:
            raise HTTPException(503, f"{variable} is not configured; response actions are disabled")
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "Invalid or missing bearer token")


def ingest_auth(authorization: str | None = Header(None)):
    token_check("FAPT_INGEST_TOKEN", authorization, required=False)


def analyst(authorization: str | None = Header(None), x_analyst_id: str | None = Header(None)):
    token_check("FAPT_RESPONSE_TOKEN", authorization, required=True)
    if not x_analyst_id or not x_analyst_id.strip():
        raise HTTPException(400, "X-Analyst-Id header is required for response actions")
    return x_analyst_id.strip()


def call(function, *args):
    try:
        return function(*args)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def found(value, name):
    if value is None:
        raise HTTPException(404, f"{name} not found")
    return value


def filters(mode, host_id):
    clauses, parameters = [], []
    if mode:
        clauses.append("mode=?"); parameters.append(mode)
    if host_id:
        clauses.append("host_id=?"); parameters.append(host_id.lower())
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", tuple(parameters)


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Mode
    source_format: Format
    events: list[dict] = Field(min_length=1)
    synchronous: bool = False


def admit(items, mode, source_format, synchronous):
    settings = store.config()["ingestion"]
    if len(items) > settings["max_batch_events"]:
        raise HTTPException(413, f"Batch exceeds {settings['max_batch_events']} events")
    if not BUCKET.take(len(items)):
        raise HTTPException(429, "Ingestion rate limit exceeded")
    if synchronous:
        return {"mode": mode, "results": [pipeline.process(raw, source_format, mode, raw_bytes) for raw, raw_bytes in items]}
    accepted = sum(pipeline.WORKER.submit(raw, source_format, mode, raw_bytes) for raw, raw_bytes in items)
    if accepted < len(items):
        raise HTTPException(429, f"Queue full: {accepted} of {len(items)} events queued; retry the remainder")
    return {"mode": mode, "queued": accepted, "queue_depth": pipeline.WORKER.depth()}


@router.post("/events", dependencies=[Depends(ingest_auth)])
def ingest(request: IngestRequest):
    return admit([(raw, None) for raw in request.events], request.mode, request.source_format, request.synchronous)


@router.post("/events/ndjson", dependencies=[Depends(ingest_auth)])
async def ingest_ndjson(request: Request, mode: Mode, source_format: Format, synchronous: bool = False):
    """One JSON object per line; exact received line bytes are preserved and hashed."""
    limit = store.config()["ingestion"]["max_event_bytes"]
    items = []
    for line in (await request.body()).splitlines():
        if not line.strip():
            continue
        if len(line) > limit:
            raise HTTPException(413, f"Event exceeds {limit} bytes")
        try:
            items.append((json.loads(line), line))
        except json.JSONDecodeError:
            items.append((None, line))
    if not items:
        raise HTTPException(422, "No events supplied")
    return admit(items, mode, source_format, synchronous)


@router.get("/health")
def health():
    snapshot = pipeline.HEALTH.snapshot()
    alive = pipeline.WORKER.thread is not None and pipeline.WORKER.thread.is_alive()
    return {"status": "degraded" if snapshot["last_error"] else "ok", "worker_alive": alive,
            "queue_depth": pipeline.WORKER.depth(), **snapshot}


@router.get("/system/status")
def system_status():
    from app.services.future_prediction_service import qualified_model
    settings = store.config()
    _, meta, reason = qualified_model("technique")
    return {"config": store.config_ref(), "schema_version": settings["schema_version"], "modes": settings["modes"],
            "inference": {"qualified_model": None if reason else meta.get("model_name"), "gate_reason": reason,
                          "behavior": "ABSTAIN (monitor/preserve only)" if reason else "PREDICT with abstention thresholds"},
            "response_execution_mode": settings["response"]["execution_mode"],
            "response_actions_enabled": bool(os.environ.get("FAPT_RESPONSE_TOKEN")),
            "ingest_authentication": bool(os.environ.get("FAPT_INGEST_TOKEN")),
            "d3fend": settings["defensive_mapping"]["d3fend"], "store": str(store.DB.name)}


@router.get("/events")
def list_events(mode: Mode | None = None, host_id: str | None = None, limit: int = Query(100, ge=1, le=500)):
    where, parameters = filters(mode, host_id)
    return store.records("events", where, parameters, limit, "timestamp_utc DESC")


@router.get("/events/{event_id}")
def get_event(event_id: str):
    return found(store.record("events", "event_id", event_id), "Event")


@router.get("/quarantine")
def list_quarantine(limit: int = Query(100, ge=1, le=500)):
    rows = store.read("SELECT id, received_at, mode, source_format, reason, raw_hash FROM quarantine ORDER BY received_at DESC LIMIT ?", (limit,))
    return [dict(zip(("quarantine_id", "received_at", "mode", "source_format", "reason", "raw_hash"), row)) for row in rows]


@router.get("/evidence")
def list_evidence(mode: Mode | None = None, limit: int = Query(100, ge=1, le=500)):
    where, parameters = filters(mode, None)
    return store.records("evidence", where, parameters, limit)


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str):
    body = found(store.record("evidence", "evidence_id", evidence_id), "Evidence")
    incident_ids = [r[0] for r in store.read("SELECT DISTINCT incident_id FROM incident_links WHERE item_type='evidence' AND item_id=?", (evidence_id,))]
    return {**body, "incident_ids": incident_ids, "relations": evidence.relations(evidence_id), "integrity": evidence.verify(evidence_id)}


@router.get("/predictions")
def list_predictions(mode: Mode | None = None, host_id: str | None = None, limit: int = Query(100, ge=1, le=500)):
    where, parameters = filters(mode, host_id)
    return store.records("predictions", where, parameters, limit)


@router.get("/predictions/{prediction_id}")
def get_prediction(prediction_id: str):
    return found(store.record("predictions", "prediction_id", prediction_id), "Prediction")


@router.get("/risk")
def list_risk(mode: Mode | None = None, host_id: str | None = None, limit: int = Query(100, ge=1, le=500)):
    where, parameters = filters(mode, host_id)
    return store.records("risk_assessments", where, parameters, limit)


@router.get("/risk/{risk_id}")
def get_risk(risk_id: str):
    return found(store.record("risk_assessments", "risk_id", risk_id), "Risk assessment")


@router.get("/decisions/{decision_id}")
def get_decision(decision_id: str):
    return found(store.record("policy_decisions", "decision_id", decision_id), "Policy decision")


@router.get("/incidents")
def list_incidents(mode: Mode | None = None, limit: int = Query(100, ge=1, le=500)):
    return incidents.listing(mode, limit)


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, expand: bool = False):
    body = call(incidents.get, incident_id)
    if expand:
        body["records"] = {kind: incidents.expand(incident_id, kind) for kind in incidents.ORDER}
    return body


@router.get("/responses")
def list_responses(mode: Mode | None = None, limit: int = Query(100, ge=1, le=500)):
    where, parameters = filters(mode, None)
    return [responses.get(r["response_id"]) for r in store.records("responses", where, parameters, limit)]


@router.get("/responses/{response_id}")
def get_response(response_id: str):
    return call(responses.get, response_id)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field(min_length=1, max_length=2000)


@router.post("/responses/{response_id}/approve")
def approve(response_id: str, request: ApprovalRequest, actor: str = Depends(analyst)):
    return call(responses.approve, response_id, actor, request.comment)


@router.post("/responses/{response_id}/execute")
def execute(response_id: str, actor: str = Depends(analyst)):
    return call(responses.execute, response_id, actor)


@router.post("/responses/{response_id}/rollback")
def rollback(response_id: str, actor: str = Depends(analyst)):
    return call(responses.rollback, response_id, actor)


@router.post("/responses/{response_id}/verify")
def verify(response_id: str, actor: str = Depends(analyst)):
    return call(verification.verify, response_id, actor)


@router.get("/responses/{response_id}/verification")
def get_verification(response_id: str):
    call(responses.get, response_id)
    return found(verification.latest(response_id), "Verification")


@router.get("/models")
def models():
    from app.services.future_prediction_service import qualified_model
    result = {}
    for task in ("technique", "stage"):
        _, meta, reason = qualified_model(task)
        result[task] = {"qualified": reason is None, "reason": reason,
                        "model": {k: meta.get(k) for k in ("model_name", "model_version", "feature_version", "algorithm", "training_timestamp")} if meta else None}
    return {"live_inference_models": result,
            "excluded": "Synthetic models (synthetic_temporal, temporal_experiment, progression) are never applied to LIVE/LAB/REPLAY telemetry."}


@router.get("/policies")
def policies():
    settings = store.config()
    return {**store.config_ref(), "policy": settings["policy"], "risk": settings["risk"], "response": settings["response"],
            "inference": settings["inference"], "verification": settings["verification"], "incidents": settings["incidents"]}


@router.get("/mappings/{technique_id}")
def mapping(technique_id: str):
    return defensive_mapping(technique_id)


@router.get("/audit")
def audit_log(limit: int = Query(100, ge=1, le=500)):
    rows = store.read("SELECT id, created_at, actor, kind, item_id, payload, previous_hash, current_hash FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,))
    return [{"id": r[0], "created_at": r[1], "actor": r[2], "kind": r[3], "item_id": r[4], "payload": json.loads(r[5]),
             "previous_hash": r[6], "current_hash": r[7]} for r in rows]


@router.get("/audit/verify")
def audit_verify():
    return store.verify_audit_chain()


@router.get("/metrics")
def metrics(mode: Mode):
    """Per-mode operational and pipeline metrics. Modes are never pooled."""
    count = lambda table: store.read(f"SELECT COUNT(*) FROM {table} WHERE mode=?", (mode,))[0][0]
    predictions = store.records("predictions", "WHERE mode=?", (mode,), 100000)
    states = {}
    for row in store.records("responses", "WHERE mode=?", (mode,), 100000):
        state = responses.get(row["response_id"])["state"]
        states[state] = states.get(state, 0) + 1
    outcomes = {}
    for (text,) in store.read("SELECT v.record FROM verifications v JOIN responses r ON r.response_id = v.response_id WHERE r.mode=?", (mode,)):
        outcome = json.loads(text)["outcome"]
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {"mode": mode, "events": count("events"), "evidence": count("evidence"), "predictions": len(predictions),
            "abstained": sum(p["status"] == "ABSTAINED" for p in predictions), "predicted": sum(p["status"] == "PREDICTED" for p in predictions),
            "incidents": count("incidents"), "responses_by_state": states, "verification_outcomes": outcomes,
            "prediction_accuracy": None, "prediction_accuracy_reason": "NOT MEASURED: no independently validated future-technique labels exist for this telemetry.",
            "prevention_success_rate": None, "prevention_success_reason": "NOT MEASURED: dry-run responses cannot change host state."}
