"""Append-only SQLite store for the real-time defense pipeline.

Separate from workflow.sqlite3 (fixture/simulation audit). Every table is
insert-only: triggers abort UPDATE/DELETE, and state changes are new rows.
"""
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import time
from uuid import uuid4

from app.datasets import DATA

DB = Path(os.environ.get("FAPT_DEFENSE_DB", DATA / "defense.sqlite3"))
CONFIG = Path(__file__).resolve().parents[2] / "config" / "defense.json"
CHAIN_METHOD = "sha256-canonical-json-v1"

TABLES = {
    "events": "event_id TEXT PRIMARY KEY, raw_event_hash TEXT NOT NULL, mode TEXT NOT NULL, host_id TEXT, timestamp_utc TEXT NOT NULL, collection_time TEXT NOT NULL, record TEXT NOT NULL, raw BLOB NOT NULL, UNIQUE(mode, raw_event_hash)",
    "quarantine": "id TEXT PRIMARY KEY, received_at TEXT NOT NULL, mode TEXT, source_format TEXT, reason TEXT NOT NULL, raw_hash TEXT NOT NULL, raw BLOB NOT NULL",
    "evidence": "evidence_id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, mode TEXT NOT NULL, created_at TEXT NOT NULL, sha256 TEXT NOT NULL, record TEXT NOT NULL",
    "evidence_relations": "id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL, relation TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL, created_at TEXT NOT NULL",
    "predictions": "prediction_id TEXT PRIMARY KEY, mode TEXT NOT NULL, host_id TEXT, event_id TEXT NOT NULL, created_at TEXT NOT NULL, record TEXT NOT NULL",
    "risk_assessments": "risk_id TEXT PRIMARY KEY, prediction_id TEXT NOT NULL, mode TEXT NOT NULL, host_id TEXT, created_at TEXT NOT NULL, record TEXT NOT NULL",
    "policy_decisions": "decision_id TEXT PRIMARY KEY, risk_id TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL, record TEXT NOT NULL",
    "responses": "response_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL, mode TEXT NOT NULL, host_id TEXT, idempotency_key TEXT NOT NULL, created_at TEXT NOT NULL, record TEXT NOT NULL",
    "response_transitions": "id TEXT PRIMARY KEY, response_id TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, record TEXT NOT NULL",
    "verifications": "verification_id TEXT PRIMARY KEY, response_id TEXT NOT NULL, created_at TEXT NOT NULL, record TEXT NOT NULL",
    "incidents": "incident_id TEXT PRIMARY KEY, mode TEXT NOT NULL, host_id TEXT, created_at TEXT NOT NULL, record TEXT NOT NULL",
    "incident_links": "id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, item_type TEXT NOT NULL, item_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(incident_id, item_type, item_id)",
    "audit_log": "seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL, item_id TEXT, payload TEXT NOT NULL, previous_hash TEXT, current_hash TEXT NOT NULL",
}
INDEXES = ["events(mode, host_id, timestamp_utc)", "predictions(mode, host_id, created_at)", "response_transitions(response_id)",
           "responses(idempotency_key, created_at)", "incident_links(incident_id)", "incident_links(item_type, item_id)",
           "evidence_relations(evidence_id)", "incidents(mode, host_id, created_at)", "verifications(response_id)"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id(prefix):
    return f"{prefix}-{uuid4().hex[:16].upper()}"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha(value):
    data = value if isinstance(value, bytes) else canonical(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def config():
    raw = CONFIG.read_bytes()
    return {**json.loads(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def config_ref():
    settings = config()
    return {"config_version": settings["version"], "config_sha256": settings["sha256"]}


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    for table, columns in TABLES.items():
        connection.execute(f"CREATE TABLE IF NOT EXISTS {table} ({columns})")
        for operation in ("UPDATE", "DELETE"):
            connection.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
                               f"BEGIN SELECT RAISE(ABORT, 'append-only table: {table}'); END")
    for index in INDEXES:
        name = "ix_" + index.replace("(", "_").replace(", ", "_").replace(")", "")
        connection.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {index}")
    return connection


def transaction(function, retries=None):
    """Run function(connection) in one IMMEDIATE transaction; retry only on lock contention."""
    attempts = retries if retries is not None else config()["ingestion"]["write_retries"]
    for attempt in range(attempts + 1):
        try:
            with closing(connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                return function(connection)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == attempts:
                raise
            time.sleep(0.05 * 2 ** attempt)


def read(sql, parameters=()):
    with closing(connect()) as connection:
        return connection.execute(sql, parameters).fetchall()


def audit(connection, actor, kind, item_id, payload):
    """Global hash chain over every pipeline decision (same method as workflow audit)."""
    last = connection.execute("SELECT current_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    entry = {"id": new_id("AUD"), "created_at": now(), "actor": actor, "kind": kind, "item_id": item_id,
             "payload": payload, "previous_hash": last[0] if last else None, "chain_method": CHAIN_METHOD}
    entry["current_hash"] = sha(entry)
    connection.execute("INSERT INTO audit_log (id, created_at, actor, kind, item_id, payload, previous_hash, current_hash) VALUES (?,?,?,?,?,?,?,?)",
                       (entry["id"], entry["created_at"], actor, kind, item_id, canonical(payload), entry["previous_hash"], entry["current_hash"]))
    return entry


def verify_audit_chain():
    rows = read("SELECT id, created_at, actor, kind, item_id, payload, previous_hash, current_hash FROM audit_log ORDER BY seq")
    previous, failures = None, []
    for id_, created, actor, kind, item, payload, prior, current in rows:
        entry = {"id": id_, "created_at": created, "actor": actor, "kind": kind, "item_id": item,
                 "payload": json.loads(payload), "previous_hash": prior, "chain_method": CHAIN_METHOD}
        if prior != previous or sha(entry) != current:
            failures.append(id_)
        previous = current
    return {"records": len(rows), "verified": not failures, "failures": failures,
            "limitation": "Local chain detects edits and internal deletion; no external anchor, so tail truncation or full replacement is not authenticated."}


def records(table, where="", parameters=(), limit=100, order="created_at DESC"):
    rows = read(f"SELECT record FROM {table} {where} ORDER BY {order} LIMIT ?", (*parameters, limit))
    return [json.loads(row[0]) for row in rows]


def record(table, key, value):
    row = read(f"SELECT record FROM {table} WHERE {key}=?", (value,))
    return json.loads(row[0][0]) if row else None
