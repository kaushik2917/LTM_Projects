"""Canonical event schema and source adapters (Sysmon, Windows Security, Wazuh, OpTC eCAR).

Unavailable fields stay None. technique_* fields are only populated from a
validated label source; behavior-rule hits are kept separately as CANDIDATE.
"""
from datetime import datetime, timezone
import ipaddress
import ntpath
import re

from pydantic import BaseModel, ConfigDict, Field

from app.services.attack_service import map_event
from app.defense.store import config, sha

FORMATS = ("canonical", "sysmon", "windows_security", "wazuh", "ecar")


class CanonicalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    mode: str
    timestamp: str
    timestamp_utc: str
    timestamp_basis: str
    host_id: str
    hostname: str | None = None
    user: str | None = None
    process_id: int | None = None
    parent_process_id: int | None = None
    process_name: str | None = None
    image_path: str | None = None
    command_line: str | None = None
    parent_image: str | None = None
    action: str
    object_type: str | None = None
    object_id: str | None = None
    actor_id: str | None = None
    source_ip: str | None = None
    source_port: int | None = None
    destination_ip: str | None = None
    destination_port: int | None = None
    protocol: str | None = None
    event_source: str
    event_category: str
    source_event_code: str | None = None
    raw_event_reference: str | None = None
    raw_event_hash: str = Field(pattern="^[0-9a-f]{64}$")
    raw_hash_basis: str
    provenance: str
    collection_time: str
    sensor: str | None = None
    technique_id: str | None = None
    technique_name: str | None = None
    technique_confidence: float | None = None
    technique_label_source: str | None = None
    candidate_techniques: list[dict] = []
    quality_flags: list[str] = []
    schema_version: str
    parser_version: str


def utc(value, basis):
    """Parse a timestamp; naive values are rejected unless the source documents UTC."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc), basis + ":epoch_ms"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing timestamp")
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text.replace(" ", "T", 1) if "T" not in text else text)
    if parsed.tzinfo is None:
        if not basis.endswith("documented_utc"):
            raise ValueError("Timestamp has no timezone and the source does not document UTC")
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), basis


def integer(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def ip(value):
    if value in (None, "", "-"):
        return None
    return str(ipaddress.ip_address(str(value).strip()))


def account(value):
    if not value or str(value).strip() in ("-", ""):
        return None
    return str(value).strip()


def basename(path):
    return ntpath.basename(str(path)).lower() if path else None


SYSMON = {1: ("process", "PROCESS_CREATE"), 3: ("network", "NETWORK_CONNECT"), 5: ("process", "PROCESS_TERMINATE"),
          7: ("module", "IMAGE_LOAD"), 8: ("process", "CREATE_REMOTE_THREAD"), 10: ("process", "PROCESS_ACCESS"),
          11: ("file", "FILE_CREATE"), 12: ("registry", "REGISTRY_OBJECT"), 13: ("registry", "REGISTRY_SET_VALUE"),
          14: ("registry", "REGISTRY_RENAME"), 22: ("dns", "DNS_QUERY"), 23: ("file", "FILE_DELETE")}
SECURITY = {4624: ("authentication", "LOGON_SUCCESS"), 4625: ("authentication", "LOGON_FAILURE"),
            4634: ("authentication", "LOGOFF"), 4648: ("authentication", "EXPLICIT_CREDENTIAL_LOGON"),
            4688: ("process", "PROCESS_CREATE"), 4720: ("account", "ACCOUNT_CREATED"), 4725: ("account", "ACCOUNT_DISABLED")}


def windows(raw, source):
    """Sysmon / Security events in Windows XML-to-JSON shape: EventID, Computer, EventData."""
    code = integer(raw.get("EventID"))
    data = raw.get("EventData") or {}
    table = SYSMON if source == "sysmon" else SECURITY
    if code not in table:
        raise ValueError(f"Unsupported {source} EventID: {code}")
    category, action = table[code]
    if source == "sysmon" and data.get("UtcTime"):
        stamp, basis = utc(data["UtcTime"], "sysmon_UtcTime_documented_utc")
    else:
        stamp, basis = utc(raw.get("TimeCreated") or raw.get("SystemTime"), f"{source}_TimeCreated")
    image = data.get("Image") or data.get("NewProcessName") or data.get("SourceImage")
    if code == 4688:  # Security 4688: NewProcessId is the child, ProcessId is the creator (parent)
        pid, ppid = data.get("NewProcessId"), data.get("ProcessId")
    else:
        pid, ppid = data.get("ProcessId") or data.get("SourceProcessId"), data.get("ParentProcessId")
    obj_type, obj_id = {"network": ("flow", data.get("DestinationIp")), "file": ("file", data.get("TargetFilename")),
                        "registry": ("registry", data.get("TargetObject")), "dns": ("dns", data.get("QueryName")),
                        "module": ("module", data.get("ImageLoaded")), "authentication": ("host", raw.get("Computer")),
                        "account": ("account", data.get("TargetUserName"))}.get(category, ("process", data.get("TargetImage") or image))
    return {"timestamp": stamp, "timestamp_basis": basis, "hostname": raw.get("Computer"),
            "user": account(data.get("User") or data.get("TargetUserName") or data.get("SubjectUserName")),
            "process_id": integer(pid), "parent_process_id": integer(ppid),
            "image_path": image, "command_line": data.get("CommandLine"), "parent_image": data.get("ParentImage") or data.get("ParentProcessName"),
            "action": action, "object_type": obj_type, "object_id": obj_id, "actor_id": data.get("ProcessGuid") or data.get("SourceProcessGuid"),
            "source_ip": ip(data.get("SourceIp") or data.get("IpAddress")), "source_port": integer(data.get("SourcePort") or data.get("IpPort")),
            "destination_ip": ip(data.get("DestinationIp")), "destination_port": integer(data.get("DestinationPort")),
            "protocol": data.get("Protocol"), "event_source": source, "event_category": category, "source_event_code": str(code),
            "raw_event_reference": f"{source}:{raw.get('Channel', '')}:{code}:{raw.get('EventRecordID') or raw.get('RecordID') or ''}",
            "sensor": "Microsoft-Windows-Sysmon" if source == "sysmon" else "Microsoft-Windows-Security-Auditing"}


def wazuh(raw):
    """Wazuh eventchannel alert: data.win.system / data.win.eventdata (lowerCamel keys)."""
    win = (raw.get("data") or {}).get("win") or {}
    system, data = win.get("system") or {}, win.get("eventdata") or {}
    provider = str(system.get("providerName", ""))
    source = "sysmon" if "sysmon" in provider.lower() else "windows_security"
    event = {"EventID": system.get("eventID"), "Computer": system.get("computer") or (raw.get("agent") or {}).get("name"),
             "TimeCreated": system.get("systemTime"), "Channel": system.get("channel"), "EventRecordID": system.get("eventRecordID"),
             "EventData": {key[:1].upper() + key[1:]: value for key, value in data.items()}}
    result = windows(event, source)
    result.update(sensor=f"wazuh-agent:{(raw.get('agent') or {}).get('id', 'unknown')}/{result['sensor']}",
                  raw_event_reference=f"wazuh:{raw.get('id', '')}:{result['raw_event_reference']}")
    return result


def ecar(raw):
    """DARPA OpTC eCAR record (same required fields as services.optc_service)."""
    for key in ("hostname", "object", "action"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise ValueError(f"Missing or invalid eCAR field: {key}")
    stamp, basis = utc(raw.get("timestamp", raw.get("timestamp_ms")), "ecar_timestamp")
    props = raw.get("properties") or {}
    category = raw["object"].lower()
    return {"timestamp": stamp, "timestamp_basis": basis, "hostname": raw["hostname"], "user": account(raw.get("principal")),
            "process_id": integer(raw.get("pid")) if raw.get("pid", -1) not in (-1, None) else None,
            "parent_process_id": integer(raw.get("ppid")) if raw.get("ppid", -1) not in (-1, None) else None,
            "image_path": props.get("image_path"), "command_line": props.get("command_line"), "parent_image": props.get("parent_image_path"),
            "action": f"{raw['object']}_{raw['action']}".upper(), "object_type": category, "object_id": raw.get("objectID"),
            "actor_id": raw.get("actorID"), "source_ip": ip(props.get("src_ip")), "source_port": integer(props.get("src_port")),
            "destination_ip": ip(props.get("dest_ip")), "destination_port": integer(props.get("dest_port")),
            "protocol": str(props["l4protocol"]) if props.get("l4protocol") is not None else None,
            "event_source": "optc_ecar", "event_category": category, "source_event_code": raw["action"],
            "raw_event_reference": f"ecar:{raw.get('id', '')}", "sensor": "OpTC eCAR"}


def canonical_input(raw):
    allowed = set(CanonicalEvent.model_fields) - {"event_id", "mode", "timestamp_utc", "raw_event_hash", "raw_hash_basis",
        "collection_time", "schema_version", "parser_version", "candidate_techniques", "quality_flags", "timestamp_basis",
        "technique_id", "technique_name", "technique_confidence", "technique_label_source"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"Unknown canonical fields: {sorted(unknown)}")
    stamp, basis = utc(raw.get("timestamp"), "canonical_timestamp")
    for key in ("action", "event_source"):
        if not raw.get(key):
            raise ValueError(f"Missing canonical field: {key}")
    values = {k: raw.get(k) for k in allowed if k != "timestamp"}
    values.update(timestamp=stamp, timestamp_basis=basis, event_category=raw.get("event_category") or "unknown",
                  source_ip=ip(raw.get("source_ip")), destination_ip=ip(raw.get("destination_ip")))
    return values


def normalize(raw, source_format, mode, collection_time, raw_bytes=None):
    """Return a validated CanonicalEvent dict. Raises ValueError for malformed input (caller quarantines)."""
    settings = config()
    if mode not in settings["modes"]:
        raise ValueError(f"Unknown mode: {mode}")
    if source_format not in FORMATS:
        raise ValueError(f"Unknown source format: {source_format}")
    if not isinstance(raw, dict):
        raise ValueError("Event must be a JSON object")
    parsed = {"canonical": canonical_input, "sysmon": lambda r: windows(r, "sysmon"),
              "windows_security": lambda r: windows(r, "windows_security"), "wazuh": wazuh, "ecar": ecar}[source_format](raw)
    host = parsed.get("hostname")
    if not host:
        raise ValueError("Missing host name")
    raw_hash = sha(raw_bytes) if raw_bytes is not None else sha(raw)
    flags = []
    collected = datetime.fromisoformat(collection_time)
    if (parsed["timestamp"] - collected).total_seconds() > settings["ingestion"]["future_skew_seconds"]:
        flags.append("future_skew")
    if parsed.get("event_category") in ("process", "network", "module") and not (parsed.get("image_path") or parsed.get("process_id")):
        flags.append("missing_process")
    if not parsed.get("user"):
        flags.append("missing_user")
    image = parsed.get("image_path")
    candidates = map_event({"properties": {"command_line": parsed.get("command_line") or "", "image_path": image or ""}})
    stamp_text = parsed["timestamp"].isoformat(timespec="microseconds")
    event = {**parsed, "timestamp": stamp_text, "timestamp_utc": stamp_text,
             "event_id": "EVT-" + sha(f"{mode}:{raw_hash}".encode())[:24].upper(), "mode": mode, "host_id": host.lower(), "hostname": host,
             "process_name": basename(image), "raw_event_hash": raw_hash,
             "raw_hash_basis": "exact_received_bytes" if raw_bytes is not None else "canonical_json_of_received_object",
             "provenance": f"{mode}:{source_format}", "collection_time": collection_time,
             "technique_id": None, "technique_name": None, "technique_confidence": None, "technique_label_source": None,
             "candidate_techniques": [{"technique_id": c["technique_id"], "technique_name": c["name"], "tactics": c["tactics"],
                                       "assertion": "OBSERVED_CANDIDATE", "mapping_status": c["mapping_status"],
                                       "label_source": c["label_source"], "basis": c["basis"]} for c in candidates],
             "quality_flags": flags, "schema_version": settings["schema_version"], "parser_version": settings["parser_version"]}
    if event.get("command_line") is not None and not isinstance(event["command_line"], str):
        raise ValueError("command_line must be text")
    if re.search(r"[\x00]", str(event.get("command_line") or "")):
        raise ValueError("command_line contains NUL bytes")
    return CanonicalEvent(**event).model_dump()
