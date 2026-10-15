"""Ingestion -> normalization -> evidence -> inference -> risk -> policy -> response -> incident.

process() is synchronous and idempotent per (mode, raw hash). submit() feeds a
bounded queue drained by one worker thread; a full queue is reported as
backpressure instead of growing without limit. A malformed event is
quarantined with its raw bytes and never stops the worker.
"""
from collections import deque
from datetime import datetime
import json
import logging
import queue
import threading
import time

from pydantic import ValidationError

from app.defense import evidence, incidents, inference, policy, responses, risk
from app.defense.events import normalize
from app.defense.store import audit, canonical, config, new_id, now, record, sha, transaction

log = logging.getLogger("fapt.defense")


class Health:
    def __init__(self):
        self.lock = threading.Lock()
        self.counters = {k: 0 for k in ("received", "accepted", "duplicates", "quarantined", "processed", "failed",
                                        "rejected_backpressure", "predictions", "abstentions", "responses_requested")}
        self.latency = {k: deque(maxlen=500) for k in ("processing_ms", "prediction_ms")}
        self.started_at = now()
        self.last_event_at = None
        self.last_error = None

    def count(self, key, amount=1):
        with self.lock:
            self.counters[key] += amount

    def observe(self, key, value):
        with self.lock:
            self.latency[key].append(value)

    def snapshot(self):
        with self.lock:
            stats = {k: {"count": len(v), "mean": sum(v) / len(v) if v else None, "max": max(v) if v else None} for k, v in self.latency.items()}
            elapsed = max((datetime.fromisoformat(now()) - datetime.fromisoformat(self.started_at)).total_seconds(), 1e-9)
            return {"started_at": self.started_at, "last_event_at": self.last_event_at, "last_error": self.last_error,
                    "counters": dict(self.counters), "latency_ms": stats,
                    "events_per_second_since_start": self.counters["processed"] / elapsed,
                    "failed_ingestion_rate": (self.counters["quarantined"] + self.counters["failed"]) / self.counters["received"] if self.counters["received"] else None}


HEALTH = Health()


def quarantine(raw, raw_bytes, source_format, mode, reason):
    data = raw_bytes if raw_bytes is not None else canonical(raw).encode("utf-8")
    item = {"id": new_id("QRN"), "received_at": now(), "reason": reason[:500], "raw_hash": sha(data)}
    def run(connection):
        connection.execute("INSERT INTO quarantine VALUES (?,?,?,?,?,?,?)", (item["id"], item["received_at"], mode, source_format, item["reason"], item["raw_hash"], data))
        audit(connection, "ingestion", "event_quarantined", item["id"], {"reason": item["reason"], "raw_hash": item["raw_hash"]})
    transaction(run)
    HEALTH.count("quarantined")
    return {"status": "quarantined", "quarantine_id": item["id"], "reason": item["reason"]}


def store_event(event, raw, raw_bytes):
    def run(connection):
        existing = connection.execute("SELECT event_id FROM events WHERE mode=? AND raw_event_hash=?", (event["mode"], event["raw_event_hash"])).fetchone()
        if existing:
            return None
        latest = connection.execute("SELECT MAX(timestamp_utc) FROM events WHERE mode=? AND host_id=?", (event["mode"], event["host_id"])).fetchone()[0]
        if latest and latest > event["timestamp_utc"]:
            event["quality_flags"] = [*event["quality_flags"], "out_of_order"]
        data = raw_bytes if raw_bytes is not None else canonical(raw).encode("utf-8")
        connection.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)", (event["event_id"], event["raw_event_hash"], event["mode"], event["host_id"],
                           event["timestamp_utc"], event["collection_time"], canonical(event), data))
        body = evidence.create(connection, event)
        audit(connection, "ingestion", "event_ingested", event["event_id"], {"evidence_id": body["evidence_id"], "raw_event_hash": event["raw_event_hash"], "mode": event["mode"]})
        return body
    return transaction(run)


def commit_assessment(event, prediction, risk_record, decision):
    def run(connection):
        incident_id = incidents.attach(connection, event, risk_record) if incidents.qualifies(risk_record["risk_level"]) else None
        created, suppressed = responses.create(connection, decision, prediction, risk_record, incident_id) if decision["containment_candidates"] else ([], [])
        stored_decision = {**decision, "incident_id": incident_id, "response_ids": [r["response_id"] for r in created], "suppressed_duplicates": suppressed}
        connection.execute("INSERT INTO predictions VALUES (?,?,?,?,?,?)", (prediction["prediction_id"], prediction["mode"], prediction["host_id"],
                           prediction["event_id"], prediction["prediction_timestamp"], canonical(prediction)))
        connection.execute("INSERT INTO risk_assessments VALUES (?,?,?,?,?,?)", (risk_record["risk_id"], prediction["prediction_id"], risk_record["mode"],
                           risk_record["host_id"], risk_record["created_at"], canonical(risk_record)))
        connection.execute("INSERT INTO policy_decisions VALUES (?,?,?,?,?)", (decision["decision_id"], risk_record["risk_id"], decision["mode"],
                           decision["created_at"], canonical(stored_decision)))
        evidence.relate(connection, prediction["supporting_evidence_ids"], "supports_prediction", "prediction", prediction["prediction_id"])
        evidence.relate(connection, risk_record["supporting_evidence_ids"], "supports_risk", "risk", risk_record["risk_id"])
        if incident_id:
            evidence.relate(connection, risk_record["supporting_evidence_ids"], "supports_incident", "incident", incident_id)
            items = [("event", i) for i in prediction["supporting_event_ids"]] + [("evidence", i) for i in prediction["supporting_evidence_ids"]]
            items += [("prediction", prediction["prediction_id"]), ("risk", risk_record["risk_id"]), ("decision", decision["decision_id"])]
            items += [("response", r["response_id"]) for r in created]
            for kind, item in items:
                incidents.link(connection, incident_id, kind, item)
        audit(connection, "pipeline", "assessment_recorded", prediction["prediction_id"], {"status": prediction["status"], "risk_id": risk_record["risk_id"],
              "risk_level": risk_record["risk_level"], "decision_id": decision["decision_id"], "incident_id": incident_id,
              "response_ids": stored_decision["response_ids"]})
        return stored_decision, created
    return transaction(run)


def process(raw, source_format, mode, raw_bytes=None):
    started = time.perf_counter()
    HEALTH.count("received")
    try:
        event = normalize(raw, source_format, mode, now(), raw_bytes)
    except (ValueError, TypeError, KeyError, ValidationError) as exc:
        return quarantine(raw, raw_bytes, source_format, mode, f"{type(exc).__name__}: {exc}")
    body = store_event(event, raw, raw_bytes)
    if body is None:
        HEALTH.count("duplicates")
        return {"status": "duplicate", "event_id": event["event_id"]}
    HEALTH.count("accepted")
    HEALTH.last_event_at = event["collection_time"]
    result = {"status": "accepted", "event_id": event["event_id"], "evidence_id": body["evidence_id"], "prediction": None}
    try:
        prediction = inference.infer(event)
        if prediction is not None:
            HEALTH.count("predictions")
            HEALTH.count("abstentions", prediction["status"] == "ABSTAINED")
            HEALTH.observe("prediction_ms", prediction.get("latency_ms") or 0.0)
            window_events = [record("events", "event_id", i) for i in prediction["supporting_event_ids"]]
            risk_record = risk.assess(prediction, window_events)
            decision = policy.decide(risk_record, prediction, event)
            stored, created = commit_assessment(event, prediction, risk_record, decision)
            HEALTH.count("responses_requested", len(created))
            result.update(prediction={"prediction_id": prediction["prediction_id"], "status": prediction["status"], "abstain_reason": prediction["abstain_reason"],
                                      "predicted_technique_id": prediction["predicted_technique_id"], "probability": prediction["probability"]},
                          risk={"risk_id": risk_record["risk_id"], "risk_score": risk_record["risk_score"], "risk_level": risk_record["risk_level"]},
                          decision={"decision_id": stored["decision_id"], "internal_actions": stored["internal_actions"], "reasons": stored["reasons"]},
                          incident_id=stored["incident_id"], response_ids=stored["response_ids"])
    except Exception as exc:  # The event and its evidence are already preserved; record and continue.
        log.exception("Defense pipeline stage failed for %s", event["event_id"])
        HEALTH.count("failed")
        HEALTH.last_error = f"{type(exc).__name__}: {exc}"
        transaction(lambda c: audit(c, "pipeline", "pipeline_error", event["event_id"], {"error": HEALTH.last_error}))
        result.update(status="accepted_with_pipeline_error", error=HEALTH.last_error)
    HEALTH.count("processed")
    HEALTH.observe("processing_ms", (time.perf_counter() - started) * 1000)
    return result


class Worker:
    def __init__(self):
        self.queue = None
        self.thread = None
        self.lock = threading.Lock()

    def ensure(self):
        with self.lock:
            if self.queue is None:
                self.queue = queue.Queue(maxsize=config()["ingestion"]["queue_capacity"])
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run, name="fapt-defense-worker", daemon=True)
                self.thread.start()

    def submit(self, raw, source_format, mode, raw_bytes=None):
        self.ensure()
        try:
            self.queue.put_nowait((raw, source_format, mode, raw_bytes))
            return True
        except queue.Full:
            HEALTH.count("rejected_backpressure")
            return False

    def run(self):
        while True:
            item = self.queue.get()
            try:
                process(*item)
            except Exception as exc:  # Storage failure after retries: count and keep draining.
                log.exception("Defense worker failed")
                HEALTH.count("failed")
                HEALTH.last_error = f"{type(exc).__name__}: {exc}"
            finally:
                self.queue.task_done()

    def depth(self):
        return self.queue.qsize() if self.queue else 0


WORKER = Worker()


def replay(path, source_format, mode="REPLAY"):
    """Synchronously replay a JSON-lines telemetry file. Never mixes with LIVE (mode is stored on every row)."""
    if mode == "LIVE":
        raise ValueError("Replay cannot be recorded as LIVE")
    summary = {}
    with open(path, "rb") as handle:
        for line in handle:
            line = line.rstrip(b"\r\n")
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                result = quarantine(None, line, source_format, mode, f"JSONDecodeError: {exc}")
            else:
                result = process(raw, source_format, mode, raw_bytes=line)
            summary[result["status"]] = summary.get(result["status"], 0) + 1
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Replay JSON-lines telemetry into the defense pipeline (REPLAY or LAB mode).")
    parser.add_argument("path")
    parser.add_argument("--format", required=True, choices=("canonical", "sysmon", "windows_security", "wazuh", "ecar"))
    parser.add_argument("--mode", default="REPLAY", choices=("REPLAY", "LAB"))
    arguments = parser.parse_args()
    print(json.dumps(replay(arguments.path, arguments.format, arguments.mode), indent=2))
