"""Adapter registry for heterogeneous telemetry.

``format`` in a raw event selects the adapter. Adding a new telemetry type means
registering one function that returns normalized fields.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fapt_guard.acquisition.base import RawEvent
from fapt_guard.acquisition.sysmon_adapter import (
    adapt_powershell,
    adapt_powershell_history,
    adapt_sysmon,
    adapt_windows_security,
    basename,
    strip_domain,
)

Adapter = Callable[[RawEvent], dict[str, Any]]


def adapt_flow(raw: RawEvent) -> dict[str, Any]:
    return {
        "source": "network_flow",
        "host": raw.get("host"),
        "user": None,
        "timestamp": raw.get("timestamp"),
        "raw_event_ref": raw.get("raw_event_ref") or f"flow:{raw.get('uid', '')}",
        "subject_type": "ip",
        "subject": str(raw.get("src_ip")),
        "action": "FLOW",
        "object_type": "ip",
        "object": str(raw.get("dst_ip")),
        "evidence_type": "network_flow",
        "artifact_class": "network_flow",
        "attributes": {k: raw.get(k) for k in ("dst_port", "proto", "bytes_out", "bytes_in", "duration", "uid")
                       if raw.get(k) is not None},
    }


def adapt_dns(raw: RawEvent) -> dict[str, Any]:
    return {
        "source": "dns",
        "host": raw.get("host"),
        "user": None,
        "timestamp": raw.get("timestamp"),
        "raw_event_ref": raw.get("raw_event_ref") or "dns",
        "subject_type": "ip",
        "subject": str(raw.get("client_ip")),
        "action": "DNS_QUERY",
        "object_type": "domain",
        "object": str(raw.get("query", "")).lower(),
        "evidence_type": "dns_query",
        "artifact_class": "dns_logs",
        "attributes": {"answers": raw.get("answers", []), "qtype": raw.get("qtype", "A")},
    }


def adapt_ids(raw: RawEvent) -> dict[str, Any]:
    sig = str(raw.get("signature", ""))
    action = "PORT_SCAN" if "scan" in sig.lower() else "IDS_ALERT"
    return {
        "source": raw.get("sensor", "ids"),
        "host": raw.get("host"),
        "user": None,
        "timestamp": raw.get("timestamp"),
        "raw_event_ref": raw.get("raw_event_ref") or f"ids:{raw.get('sid', '')}",
        "subject_type": "ip",
        "subject": str(raw.get("src_ip")),
        "action": action,
        "object_type": "ip",
        "object": str(raw.get("dst_ip")),
        "evidence_type": "ids_alert",
        "artifact_class": "network_flow",
        "attributes": {"signature": sig, "severity": raw.get("severity", 2), "dst_port": raw.get("dst_port"),
                       "count": raw.get("count", 1)},
    }


def adapt_threat_intel(raw: RawEvent) -> dict[str, Any]:
    ind = str(raw.get("indicator"))
    itype = raw.get("indicator_type", "ip")
    return {
        "source": "threat_intel",
        "host": None,
        "user": None,
        "timestamp": raw.get("timestamp"),
        "raw_event_ref": raw.get("raw_event_ref") or f"ti:{ind}",
        "subject_type": "other",
        "subject": raw.get("feed", "ti_feed"),
        "action": "TI_INDICATOR",
        "object_type": "domain" if itype == "domain" else "ip",
        "object": ind.lower(),
        "evidence_type": "threat_intel",
        "artifact_class": "threat_context",
        "attributes": {"reputation": float(raw.get("reputation", 0.0)), "tags": raw.get("tags", []),
                       "indicator_type": itype},
    }


def adapt_vulnerability(raw: RawEvent) -> dict[str, Any]:
    return {
        "source": "vulnerability_scanner",
        "host": raw.get("host"),
        "user": None,
        "timestamp": raw.get("timestamp"),
        "raw_event_ref": raw.get("raw_event_ref") or f"vuln:{raw.get('cve')}",
        "subject_type": "host",
        "subject": raw.get("host"),
        "action": "VULNERABILITY",
        "object_type": "vulnerability",
        "object": raw.get("cve", "unknown"),
        "evidence_type": "vulnerability",
        "artifact_class": "threat_context",
        "attributes": {"cvss": float(raw.get("cvss", 0.0)), "service": raw.get("service"),
                       "exposed": bool(raw.get("exposed", False))},
    }


def adapt_asset(raw: RawEvent) -> dict[str, Any]:
    return {
        "source": "asset_inventory",
        "host": raw.get("host"),
        "user": None,
        "timestamp": raw.get("timestamp"),
        "raw_event_ref": raw.get("raw_event_ref") or f"asset:{raw.get('host')}",
        "subject_type": "host",
        "subject": raw.get("host"),
        "action": "ASSET_INFO",
        "object_type": "host",
        "object": raw.get("host"),
        "evidence_type": "asset",
        "artifact_class": "threat_context",
        "attributes": {k: raw.get(k) for k in ("criticality", "role", "ip", "exposed_services", "disk_encryption",
                                               "historical_incidents", "owner") if raw.get(k) is not None},
    }


def adapt_generic(raw: RawEvent) -> dict[str, Any]:
    """Already (mostly) normalized events, e.g. posted to the API."""
    out = {k: raw.get(k) for k in ("source", "host", "user", "timestamp", "raw_event_ref", "subject_type",
                                   "subject", "action", "object_type", "object", "evidence_type",
                                   "artifact_class", "evidence_id", "incident_id")}
    out["attributes"] = dict(raw.get("attributes", {}) or {})
    out["user"] = strip_domain(out.get("user"))
    if out.get("subject_type") == "process":
        out["subject"] = basename(out.get("subject"))
    if out.get("object_type") == "process":
        out["object"] = basename(out.get("object"))
    return out


ADAPTERS: dict[str, Adapter] = {
    "sysmon": adapt_sysmon,
    "windows_security": adapt_windows_security,
    "winsec": adapt_windows_security,
    "powershell": adapt_powershell,
    "powershell_history": adapt_powershell_history,
    "flow": adapt_flow,
    "network_flow": adapt_flow,
    "dns": adapt_dns,
    "ids": adapt_ids,
    "firewall": adapt_ids,
    "threat_intel": adapt_threat_intel,
    "vulnerability": adapt_vulnerability,
    "asset": adapt_asset,
    "generic": adapt_generic,
}


def register_adapter(fmt: str, adapter: Adapter) -> None:
    ADAPTERS[fmt] = adapter


def adapt(raw: RawEvent) -> dict[str, Any]:
    fmt = raw.get("format") or ("generic" if "action" in raw else "unknown")
    if fmt not in ADAPTERS:
        raise ValueError(f"No adapter registered for raw event format '{fmt}'")
    fields = ADAPTERS[fmt](raw)
    # carry-through metadata used by the simulation / benchmark
    for k in ("evidence_id", "incident_id", "latent", "simulated", "ingested_at"):
        if raw.get(k) is not None and fields.get(k) is None:
            fields[k] = raw[k]
    return fields
