"""Bounded streaming eCAR ingestion. Raw observations are retained in SQLite."""
from datetime import datetime, timezone
from contextlib import closing
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

from app.datasets import DATA, sha256
from app.services.attack_service import map_event

DB = DATA / "optc.sqlite3"


def connect(path=None):
    conn = sqlite3.connect(path or DB)
    conn.execute("CREATE TABLE IF NOT EXISTS events (digest TEXT PRIMARY KEY, event_id TEXT, incident TEXT, timestamp TEXT, normalized TEXT, raw BLOB)")
    conn.execute("CREATE INDEX IF NOT EXISTS events_timeline ON events(incident, timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS imports (file_hash TEXT, metadata TEXT)")
    return conn


def normalize(raw, digest, reference):
    for key in ("hostname", "actorID", "objectID", "object", "action"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise ValueError(f"Missing or invalid eCAR field: {key}")
    stamp = raw.get("timestamp", raw.get("timestamp_ms"))
    if isinstance(stamp, (int, float)):
        timestamp = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc)
    elif isinstance(stamp, str):
        timestamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("eCAR timestamp must include timezone")
    else:
        raise ValueError("Missing eCAR timestamp")
    timestamp = timestamp.astimezone(timezone.utc)
    return {"evidence_id": "OPTC-" + digest, "incident_id": f"OPTC:{raw['hostname']}:{timestamp.date()}",
        "timestamp": timestamp.isoformat(), "source": "optc_ecar", "host": raw["hostname"],
        "user": raw.get("principal"), "subject_type": "process", "subject": raw["actorID"],
        "action": raw["action"], "object_type": raw["object"].lower(), "object": raw["objectID"],
        "evidence_type": raw["object"].lower() + "_" + raw["action"].lower(),
        "properties": raw.get("properties", {}), "raw_event_ref": reference,
        "integrity_hash": digest, "integrity_scope": "exact_source_line_bytes",
        "simulated": False, "provenance": "DARPA OpTC controlled evaluation",
        "attack_mappings": map_event(raw), "trust_score": None,
        "source_event_id": raw.get("id"), "grouping": "host_day_not_confirmed_incident"}


def import_optc(path, limit=100000, db_path=None):
    if limit < 1:
        raise ValueError("limit must be positive")
    path = Path(path).resolve()
    opener = gzip.open if path.suffix == ".gz" else open
    summary = {"source": str(path), "imported": 0, "duplicates": 0, "rejected": 0,
               "errors": [], "limit": limit, "truncated": False, "file_name": path.name,
               "file_hash": sha256(path), "import_timestamp": datetime.now(timezone.utc).isoformat(),
               "dataset_id": "optc", "dataset_name": "DARPA OpTC", "preprocessing_version": "ecar-v1"}
    DATA.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        with conn, opener(path, "rb") as handle:
            for index, line in enumerate(handle, 1):
                if index > limit:
                    summary["truncated"] = True
                    break
                try:
                    raw = json.loads(line)
                    digest = hashlib.sha256(line).hexdigest()
                    event = normalize(raw, digest, f"{path.name}:line:{index}")
                    cursor = conn.execute("INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)",
                        (digest, raw.get("id"), event["incident_id"], event["timestamp"], json.dumps(event), line))
                    summary["imported" if cursor.rowcount else "duplicates"] += 1
                except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
                    summary["rejected"] += 1
                    if len(summary["errors"]) < 20:
                        summary["errors"].append({"line": index, "error": str(exc)})
            summary["number_of_events"] = summary["imported"]
            summary["number_of_rows"] = summary["imported"] + summary["duplicates"] + summary["rejected"]
            summary["processing_status"] = "partial" if summary["truncated"] else "processed" if summary["imported"] or summary["duplicates"] else "no_valid_events"
            conn.execute("INSERT INTO imports VALUES (?, ?)", (summary["file_hash"], json.dumps(summary)))
    finally:
        conn.close()
    return summary


def status():
    if not DB.exists():
        return {"status": "not_imported", "events": 0, "tc_fapn": "not_trained"}
    with closing(sqlite3.connect(DB)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        incidents = conn.execute("SELECT COUNT(DISTINCT incident) FROM events").fetchone()[0]
        exists = conn.execute("SELECT name FROM sqlite_master WHERE name='imports'").fetchone()
        imports = [json.loads(r[0]) for r in conn.execute("SELECT metadata FROM imports")] if exists else []
    return {"status": "imported" if count else "empty", "events": count, "incidents": incidents,
            "grouping": "host/day windows, not labeled attack incidents", "imports": imports, "tc_fapn": "not_trained"}


def events(incident=None, limit=100, offset=0, db_path=None):
    path = Path(db_path or DB)
    if not path.exists():
        return []
    sql, params = "SELECT normalized FROM events", []
    if incident:
        sql += " WHERE incident=?"
        params.append(incident)
    sql += " ORDER BY timestamp, digest LIMIT ? OFFSET ?"
    with closing(sqlite3.connect(path)) as conn:
        return [json.loads(r[0]) for r in conn.execute(sql, params + [limit, offset])]


def graph(incident, limit=1000):
    import networkx as nx
    evidence = events(incident, limit + 1)
    graph = nx.MultiDiGraph()
    unknown = "00000000-0000-0000-0000-000000000000"
    for event in evidence[:limit]:
        for field in ("subject", "object"):
            entity = event[field]
            # Never merge all missing IDs into one spurious high-degree node.
            node = f"{event['host']}:{entity}" if entity != unknown else f"unknown:{event['evidence_id']}:{field}"
            graph.add_node(node, entity_id=entity, type=event[field + "_type"], host=event["host"])
            event[field + "_node"] = node
        graph.add_edge(event["subject_node"], event["object_node"], key=event["evidence_id"],
            timestamp=event["timestamp"], action=event["action"], mappings=event["attack_mappings"], trust=None)
    return {"incident_id": incident, "directed": True, "multigraph": True,
        "nodes": [{"id": n, **attrs} for n, attrs in graph.nodes(data=True)],
        "edges": [{"source": u, "target": v, "evidence_id": key, **attrs} for u, v, key, attrs in graph.edges(keys=True, data=True)],
        "truncated": len(evidence) > limit, "grouping": "host_day_not_confirmed_attack",
        "prediction": {"status": "unavailable", "reason": "Ground-truth sequence labels and a trained progression model are required."}}
