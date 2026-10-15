"""Immutable evidence objects derived from stored telemetry events.

An evidence record is a preserved, hash-sealed description of one observed
event. It is evidence that the event was observed, not proof of an attack.
"""
from app.defense.store import canonical, config, new_id, now, read, sha

RELATIONS = ("supports_prediction", "supports_risk", "supports_incident", "supports_response", "contradicts_prediction")


def create(connection, event):
    settings = config()
    body = {"evidence_id": new_id("EVD"), "event_id": event["event_id"], "mode": event["mode"],
            "timestamp": event["timestamp_utc"], "source": event["event_source"], "host": event["host_id"],
            "user": event.get("user"), "action": event["action"], "object_type": event.get("object_type"),
            "object": event.get("object_id"), "raw_event_reference": event.get("raw_event_reference"),
            "raw_event_hash": event["raw_event_hash"], "raw_hash_basis": event["raw_hash_basis"],
            "evidence_type": f"{event['event_category']}_{event['action']}".lower(), "provenance": event["provenance"],
            "collection_timestamp": event["collection_time"], "created_at": now(),
            "parser_version": event["parser_version"], "schema_version": event["schema_version"],
            "config_version": settings["version"], "candidate_techniques": event.get("candidate_techniques", []),
            "quality_flags": event.get("quality_flags", []),
            "evidentiary_scope": "Preserved observation of a telemetry event; does not by itself establish malicious activity."}
    body["sha256"] = sha(body)
    connection.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?)", (body["evidence_id"], body["event_id"], body["mode"],
                       body["created_at"], body["sha256"], canonical(body)))
    return body


def relate(connection, evidence_ids, relation, target_type, target_id):
    if relation not in RELATIONS:
        raise ValueError(f"Unknown evidence relation: {relation}")
    created = now()
    for evidence_id in evidence_ids:
        connection.execute("INSERT INTO evidence_relations VALUES (?,?,?,?,?,?)",
                           (new_id("REL"), evidence_id, relation, target_type, target_id, created))


def for_events(event_ids):
    if not event_ids:
        return {}
    marks = ",".join("?" * len(event_ids))
    return {row[0]: row[1] for row in read(f"SELECT event_id, evidence_id FROM evidence WHERE event_id IN ({marks})", tuple(event_ids))}


def verify(evidence_id):
    """Recompute the evidence seal and the raw-byte hash of the linked event."""
    import json
    row = read("SELECT e.record, ev.raw, ev.record FROM evidence e JOIN events ev ON ev.event_id = e.event_id WHERE e.evidence_id=?", (evidence_id,))
    if not row:
        raise LookupError("Evidence not found")
    body, raw, event = json.loads(row[0][0]), row[0][1], json.loads(row[0][2])
    sealed = sha({k: v for k, v in body.items() if k != "sha256"}) == body["sha256"]
    raw_valid = (sha(bytes(raw)) if event["raw_hash_basis"] == "exact_received_bytes" else sha(json.loads(bytes(raw)))) == body["raw_event_hash"]
    return {"evidence_id": evidence_id, "record_seal_valid": sealed, "raw_event_hash_valid": raw_valid,
            "verified": sealed and raw_valid, "scope": "Local integrity of stored record and raw bytes; does not authenticate the original sensor."}


def relations(evidence_id):
    return [{"relation": r, "target_type": t, "target_id": i, "created_at": c} for r, t, i, c in
            read("SELECT relation, target_type, target_id, created_at FROM evidence_relations WHERE evidence_id=? ORDER BY created_at", (evidence_id,))]
