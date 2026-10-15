"""Incident correlation: event -> evidence -> prediction -> risk -> policy -> response -> verification.

Incidents group risk assessments at or above the configured level for one
host and mode; a new incident opens when the gap since the last linked
event exceeds the configured window. Fixture INC-00001 is unaffected.
"""
from datetime import datetime
import json

from app.defense.store import canonical, config, new_id, now, read, record

ORDER = ("event", "evidence", "prediction", "risk", "decision", "response", "verification")
TABLES = {"event": ("events", "event_id"), "evidence": ("evidence", "evidence_id"), "prediction": ("predictions", "prediction_id"),
          "risk": ("risk_assessments", "risk_id"), "decision": ("policy_decisions", "decision_id"),
          "response": ("responses", "response_id"), "verification": ("verifications", "verification_id")}


def link(connection, incident_id, item_type, item_id):
    connection.execute("INSERT OR IGNORE INTO incident_links VALUES (?,?,?,?,?)", (new_id("LNK"), incident_id, item_type, item_id, now()))


def qualifies(level):
    names = [name for name, _ in config()["risk"]["levels"]]
    return names.index(level) >= names.index(config()["incidents"]["open_at_level"])


def attach(connection, event, risk_record):
    """Return the open incident for this host/mode, creating one if needed."""
    gap = config()["incidents"]["gap_minutes"] * 60
    row = connection.execute("SELECT incident_id FROM incidents WHERE mode=? AND host_id=? ORDER BY created_at DESC LIMIT 1",
                             (event["mode"], event["host_id"])).fetchone()
    if row:
        last = connection.execute("SELECT MAX(e.timestamp_utc) FROM incident_links l JOIN events e ON e.event_id = l.item_id "
                                  "WHERE l.incident_id=? AND l.item_type='event'", (row[0],)).fetchone()[0]
        if last and abs((datetime.fromisoformat(event["timestamp_utc"]) - datetime.fromisoformat(last)).total_seconds()) <= gap:
            return row[0]
    body = {"incident_id": new_id("INC-D"), "mode": event["mode"], "host_id": event["host_id"], "created_at": now(),
            "opened_by_risk_id": risk_record["risk_id"], "opened_at_level": risk_record["risk_level"],
            "first_event_time": event["timestamp_utc"], "title": f"{risk_record['risk_level']} risk on {event['host_id']}",
            "scope": "Correlated pipeline records for one host and mode; not an adjudicated attack."}
    connection.execute("INSERT INTO incidents VALUES (?,?,?,?,?)", (body["incident_id"], body["mode"], body["host_id"], body["created_at"], canonical(body)))
    return body["incident_id"]


def get(incident_id):
    body = record("incidents", "incident_id", incident_id)
    if body is None:
        raise LookupError("Incident not found")
    links = read("SELECT item_type, item_id FROM incident_links WHERE incident_id=? ORDER BY created_at, rowid", (incident_id,))
    chain = {kind: [i for t, i in links if t == kind] for kind in ORDER}
    risks = [record("risk_assessments", "risk_id", i) for i in chain["risk"]]
    peak = max(risks, key=lambda r: r["risk_score"]) if risks else None
    return {**body, "chain": chain, "counts": {k: len(v) for k, v in chain.items()},
            "peak_risk": {"risk_id": peak["risk_id"], "score": peak["risk_score"], "level": peak["risk_level"]} if peak else None,
            "latest_risk": {"risk_id": risks[-1]["risk_id"], "score": risks[-1]["risk_score"], "level": risks[-1]["risk_level"]} if risks else None}


def expand(incident_id, item_type):
    table, key = TABLES[item_type]
    return [record(table, key, i) for i in get(incident_id)["chain"][item_type]]


def listing(mode=None, limit=100):
    where, parameters = ("WHERE mode=?", (mode,)) if mode else ("", ())
    return [json.loads(r[0]) for r in read(f"SELECT record FROM incidents {where} ORDER BY created_at DESC LIMIT ?", (*parameters, limit))]
