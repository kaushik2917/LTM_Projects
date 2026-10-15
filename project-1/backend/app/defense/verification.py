"""Response verification: did subsequent telemetry and reassessed risk change after the action?"""
from datetime import datetime, timedelta
import json

from app.defense import incidents, inference, responses, risk
from app.defense.store import audit, canonical, config, new_id, now, read, record, transaction


def classify(host_action_executed, telemetry_count, indicator_count, risk_before, risk_after, min_reduction):
    """Pure outcome rule. A dry run can never be credited with an effect."""
    if not host_action_executed:
        return "UNKNOWN", "Dry run: no host action was performed, so no effect can be attributed to the response."
    if telemetry_count == 0:
        return "UNKNOWN", "No subsequent telemetry from the host inside the verification window."
    if indicator_count > 0:
        return "FAILED", "Telemetry matching the contained target continued after the action."
    if risk_after is not None and risk_after <= risk_before * (1 - min_reduction):
        return "SUCCESS", "Target activity absent and reassessed risk fell by at least the configured reduction."
    return "PARTIAL_SUCCESS", "Target activity absent but reassessed risk did not fall enough."


def indicators(response, events):
    p = response["parameters"]
    match = {"BLOCK_DESTINATION_IP": lambda e: e.get("destination_ip") == p.get("destination_ip"),
             "TERMINATE_PROCESS": lambda e: e.get("process_id") == p.get("process_id") and e.get("process_name") == p.get("process_name"),
             "DISABLE_LOCAL_ACCOUNT": lambda e: (e.get("user") or "").split("\\")[-1].lower() == p.get("user", "").lower()}[response["action_type"]]
    return [e["event_id"] for e in events if match(e)]


def verify(response_id, actor):
    settings = config()["verification"]
    response = responses.get(response_id)
    executed = next((t for t in reversed(response["transitions"]) if t["state"].startswith("EXECUTED")), None)
    if executed is None:
        raise ValueError(f"Response is {response['state']}; verification needs an executed response")
    trigger = record("events", "event_id", response["trigger_event_id"])
    online = response["mode"] in ("LIVE", "LAB")
    # Replay: the action is anchored at the triggering event time (event-time estimand).
    action_time = executed["executed_at"] if online else trigger["timestamp_utc"]
    end = (datetime.fromisoformat(action_time) + timedelta(minutes=settings["window_minutes"])).isoformat(timespec="microseconds")
    later = [json.loads(r[0]) for r in read("SELECT record FROM events WHERE mode=? AND host_id=? AND timestamp_utc>? AND timestamp_utc<=? ORDER BY timestamp_utc",
                                             (response["mode"], response["host_id"], action_time, end))]
    hits = indicators(response, later)
    before = record("risk_assessments", "risk_id", response["risk_id"])
    after_prediction = after_risk = None
    if later:
        after_prediction = inference.infer(later[-1], force=True)
        window_events = [record("events", "event_id", i) for i in after_prediction["supporting_event_ids"]]
        after_risk = risk.assess(after_prediction, window_events)
    outcome, reason = classify(executed.get("host_action_executed", False), len(later), len(hits), before["risk_score"],
                               after_risk["risk_score"] if after_risk else None, settings["min_risk_reduction"])
    body = {"verification_id": new_id("VER"), "response_id": response_id, "created_at": now(), "actor": actor,
            "execution_state": executed["state"], "host_action_executed": executed.get("host_action_executed", False),
            "action_time": action_time, "window_end": end, "subsequent_event_count": len(later), "indicator_event_ids": hits,
            "risk_before": {"risk_id": before["risk_id"], "score": before["risk_score"], "level": before["risk_level"]},
            "risk_after": {"risk_id": after_risk["risk_id"], "score": after_risk["risk_score"], "level": after_risk["risk_level"]} if after_risk else None,
            "outcome": outcome, "reason": reason,
            "escalate": bool(after_risk and after_risk["risk_level"] in settings["escalate_levels"]) or (after_risk is None and before["risk_level"] in settings["escalate_levels"]),
            "verification_version": config()["version"]}
    def run(connection):
        if after_prediction:
            connection.execute("INSERT INTO predictions VALUES (?,?,?,?,?,?)", (after_prediction["prediction_id"], after_prediction["mode"],
                               after_prediction["host_id"], after_prediction["event_id"], after_prediction["prediction_timestamp"], canonical(after_prediction)))
            connection.execute("INSERT INTO risk_assessments VALUES (?,?,?,?,?,?)", (after_risk["risk_id"], after_prediction["prediction_id"],
                               after_risk["mode"], after_risk["host_id"], after_risk["created_at"], canonical(after_risk)))
        connection.execute("INSERT INTO verifications VALUES (?,?,?,?)", (body["verification_id"], response_id, body["created_at"], canonical(body)))
        if response.get("incident_id"):
            for kind, item in (("verification", body["verification_id"]), ("prediction", after_prediction and after_prediction["prediction_id"]),
                               ("risk", after_risk and after_risk["risk_id"])):
                if item:
                    incidents.link(connection, response["incident_id"], kind, item)
        audit(connection, actor, "response_verified", response_id, {"outcome": outcome, "escalate": body["escalate"]})
    transaction(run)
    return body


def latest(response_id):
    rows = read("SELECT record FROM verifications WHERE response_id=? ORDER BY created_at DESC LIMIT 1", (response_id,))
    return json.loads(rows[0][0]) if rows else None
