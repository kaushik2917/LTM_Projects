"""Response lifecycle. Requests are immutable; every state change is an appended transition."""
from datetime import datetime, timedelta, timezone
import json

from app.defense import executor
from app.defense.evidence import relate
from app.defense.store import audit, canonical, config, new_id, now, read, record, sha, transaction

FINAL = ("EXECUTED_DRY_RUN", "REFUSED", "ROLLED_BACK_DRY_RUN")


def transition(connection, response_id, state, details):
    entry = {"transition_id": new_id("TRN"), "response_id": response_id, "state": state, "created_at": now(), **details}
    connection.execute("INSERT INTO response_transitions VALUES (?,?,?,?,?)",
                       (entry["transition_id"], response_id, state, entry["created_at"], canonical(entry)))
    return entry


def create(connection, decision, prediction, risk, incident_id):
    """Insert containment requests for a decision, suppressing duplicates inside the cooldown."""
    cooldown = config()["policy"]["cooldown_seconds"]
    since = (datetime.now(timezone.utc) - timedelta(seconds=cooldown)).isoformat(timespec="microseconds")
    created, suppressed = [], []
    for candidate in decision["containment_candidates"]:
        key = sha({"mode": decision["mode"], "host": decision["host_id"], "action": candidate["action_type"], "parameters": candidate["parameters"]})
        prior = connection.execute("SELECT response_id FROM responses WHERE idempotency_key=? AND created_at>=? LIMIT 1", (key, since)).fetchone()
        if prior:
            suppressed.append({"action_type": candidate["action_type"], "duplicate_of": prior[0], "reason": f"Cooldown {cooldown}s"})
            continue
        response_id = new_id("RESP")
        command, rollback = executor.plan(candidate["action_type"], candidate["parameters"], response_id)
        body = {"response_id": response_id, "decision_id": decision["decision_id"], "policy_id": decision["policy_version"],
                "prediction_id": prediction["prediction_id"], "risk_id": risk["risk_id"], "incident_id": incident_id,
                "mode": decision["mode"], "host_id": decision["host_id"], "action_type": candidate["action_type"],
                "parameters": candidate["parameters"], "reversible": candidate["reversible"],
                "approval_required": candidate["approval_required"], "justification": candidate["justification"],
                "evidence_ids": risk["supporting_evidence_ids"], "requested_at": now(), "idempotency_key": key,
                "planned_command": command, "rollback_command": rollback, "trigger_event_id": prediction["event_id"]}
        connection.execute("INSERT INTO responses VALUES (?,?,?,?,?,?,?)", (response_id, decision["decision_id"], decision["mode"],
                           decision["host_id"], key, body["requested_at"], canonical(body)))
        initial = "PENDING_APPROVAL" if candidate["approval_required"] else "APPROVED"
        transition(connection, response_id, initial, {"actor": "policy-engine", "approved_by": None if candidate["approval_required"] else "policy:auto_execute_critical"})
        relate(connection, body["evidence_ids"], "supports_response", "response", response_id)
        audit(connection, "policy-engine", "response_requested", response_id, {"action_type": body["action_type"], "state": initial})
        created.append(body)
    return created, suppressed


def history(response_id):
    return [json.loads(r[0]) for r in read("SELECT record FROM response_transitions WHERE response_id=? ORDER BY created_at, rowid", (response_id,))]


def get(response_id):
    body = record("responses", "response_id", response_id)
    if body is None:
        raise LookupError("Response not found")
    states = history(response_id)
    return {**body, "state": states[-1]["state"] if states else None, "transitions": states}


def approve(response_id, analyst, comment):
    if not analyst or not analyst.strip():
        raise ValueError("Approval requires an analyst identity")
    def run(connection):
        current = get(response_id)
        if current["state"] != "PENDING_APPROVAL":
            raise ValueError(f"Response is {current['state']}, not PENDING_APPROVAL")
        entry = transition(connection, response_id, "APPROVED", {"actor": analyst, "approved_by": analyst, "approved_at": now(), "comment": comment})
        audit(connection, analyst, "response_approved", response_id, {"comment": comment})
        return entry
    transaction(run)
    return get(response_id)


def execute(response_id, actor):
    def run(connection):
        current = get(response_id)
        if current["state"] != "APPROVED":
            raise ValueError(f"Response is {current['state']}; only APPROVED responses can be executed")
        outcome = executor.execute(current)
        entry = transition(connection, response_id, outcome["state"], {"actor": actor, "executor": "fapt-guard-executor",
                           "executed_at": now(), **outcome})
        audit(connection, actor, "response_executed", response_id, {"state": outcome["state"], "host_action_executed": outcome["host_action_executed"]})
        return entry
    transaction(run)
    return get(response_id)


def rollback(response_id, actor):
    def run(connection):
        current = get(response_id)
        if current["state"] != "EXECUTED_DRY_RUN":
            raise ValueError(f"Response is {current['state']}; nothing to roll back")
        if not current["reversible"]:
            raise ValueError("Action is irreversible; rollback is not available")
        transition(connection, response_id, "ROLLED_BACK_DRY_RUN", {"actor": actor, "executed_at": now(), "host_action_executed": False,
                   "rollback_command": current["rollback_command"], "result": "Dry run: rollback recorded, not executed."})
        audit(connection, actor, "response_rolled_back", response_id, {"mode": "DRY_RUN"})
    transaction(run)
    return get(response_id)
