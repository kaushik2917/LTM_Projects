"""Adapters for Sysmon, Windows Security and PowerShell events.

Each adapter converts a raw Windows-style event (``EventID`` + ``EventData``)
into a dict of normalized fields; the normalizer turns that into Evidence.
"""

from __future__ import annotations

import ntpath
from typing import Any

from fapt_guard.acquisition.base import RawEvent


def basename(path: str | None) -> str:
    if not path:
        return ""
    return ntpath.basename(str(path)).lower()


def strip_domain(user: str | None) -> str | None:
    if not user:
        return None
    return str(user).split("\\")[-1].split("@")[0]


def _ts(raw: RawEvent) -> Any:
    return raw.get("UtcTime") or raw.get("TimeCreated") or raw.get("timestamp")


def _base(raw: RawEvent, source: str) -> dict[str, Any]:
    ed = raw.get("EventData", {}) or {}
    return {
        "source": source,
        "host": raw.get("Computer") or raw.get("host"),
        "user": strip_domain(ed.get("User") or ed.get("TargetUserName") or raw.get("user")),
        "timestamp": _ts(raw),
        "raw_event_ref": raw.get("raw_event_ref") or f"{source}:{raw.get('EventID')}:{raw.get('RecordID', '')}",
        "attributes": {"event_id": raw.get("EventID")},
    }


# ---------------------------------------------------------------------------
# Sysmon
# ---------------------------------------------------------------------------
def adapt_sysmon(raw: RawEvent) -> dict[str, Any]:
    eid = int(raw.get("EventID", 0))
    ed = raw.get("EventData", {}) or {}
    out = _base(raw, "sysmon")
    out["artifact_class"] = "sysmon_logs"
    attrs = out["attributes"]

    if eid == 1:  # process create
        out.update(subject_type="process", subject=basename(ed.get("ParentImage")),
                   action="PROCESS_CREATE", object_type="process", object=basename(ed.get("Image")),
                   evidence_type="process_event")
        attrs.update(image_path=ed.get("Image"), command_line=ed.get("CommandLine", ""),
                     parent_command_line=ed.get("ParentCommandLine", ""), pid=ed.get("ProcessId"),
                     ppid=ed.get("ParentProcessId"), integrity_level=ed.get("IntegrityLevel"),
                     signed=ed.get("Signed", True), hashes=ed.get("Hashes"))
    elif eid == 3:  # network connection
        out.update(subject_type="process", subject=basename(ed.get("Image")), action="NETWORK_CONNECT",
                   object_type="ip", object=str(ed.get("DestinationIp")), evidence_type="network_connection")
        attrs.update(dst_port=ed.get("DestinationPort"), src_ip=ed.get("SourceIp"),
                     protocol=ed.get("Protocol", "tcp"), dst_hostname=ed.get("DestinationHostname"))
    elif eid == 5:
        out.update(subject_type="process", subject=basename(ed.get("Image")), action="PROCESS_TERMINATE",
                   object_type="process", object=basename(ed.get("Image")), evidence_type="process_event")
    elif eid == 2:
        out.update(subject_type="process", subject=basename(ed.get("Image")), action="FILE_TIME_CHANGE",
                   object_type="file", object=str(ed.get("TargetFilename")), evidence_type="file_event")
        attrs.update(previous_creation_time=ed.get("PreviousCreationUtcTime"),
                     new_creation_time=ed.get("CreationUtcTime"))
    elif eid == 4:
        out.update(subject_type="service", subject="sysmon", action="SERVICE_STATE_CHANGE",
                   object_type="service", object="sysmon", evidence_type="sensor_event")
        attrs.update(state=ed.get("State"))
    elif eid == 10:  # process access
        out.update(subject_type="process", subject=basename(ed.get("SourceImage")), action="PROCESS_ACCESS",
                   object_type="process", object=basename(ed.get("TargetImage")), evidence_type="process_access")
        attrs.update(granted_access=ed.get("GrantedAccess"), call_trace=ed.get("CallTrace"))
    elif eid == 11:
        out.update(subject_type="process", subject=basename(ed.get("Image")), action="FILE_CREATE",
                   object_type="file", object=str(ed.get("TargetFilename")), evidence_type="file_event")
    elif eid == 23 or eid == 26:
        out.update(subject_type="process", subject=basename(ed.get("Image")), action="FILE_DELETE",
                   object_type="file", object=str(ed.get("TargetFilename")), evidence_type="file_event")
    elif eid in (12, 13, 14):
        out.update(subject_type="process", subject=basename(ed.get("Image")), action="REGISTRY_SET",
                   object_type="registry", object=str(ed.get("TargetObject")), evidence_type="registry_event")
        attrs.update(details=ed.get("Details"))
        out["artifact_class"] = "sysmon_logs"
    elif eid == 22:
        out.update(subject_type="process", subject=basename(ed.get("Image")), action="DNS_QUERY",
                   object_type="domain", object=str(ed.get("QueryName")).lower(), evidence_type="dns_query")
        attrs.update(query_results=ed.get("QueryResults"))
    elif eid == 16:
        out.update(subject_type="service", subject="sysmon", action="SENSOR_CONFIG_CHANGE",
                   object_type="service", object="sysmon", evidence_type="sensor_event")
    else:
        out.update(subject_type="other", subject=str(ed.get("Image", "unknown")), action=f"SYSMON_{eid}",
                   object_type="other", object="", evidence_type="sysmon_other")
    if not out.get("user"):
        out["user"] = strip_domain(ed.get("User"))
    return out


# ---------------------------------------------------------------------------
# Windows Security / System
# ---------------------------------------------------------------------------
def adapt_windows_security(raw: RawEvent) -> dict[str, Any]:
    eid = int(raw.get("EventID", 0))
    ed = raw.get("EventData", {}) or {}
    out = _base(raw, "windows_security")
    out["artifact_class"] = "authentication_logs"
    host = out["host"]
    attrs = out["attributes"]

    if eid in (4624, 4625):
        user = strip_domain(ed.get("TargetUserName"))
        out.update(user=user, subject_type="user", subject=user or "unknown",
                   action="LOGON_SUCCESS" if eid == 4624 else "LOGON_FAILURE",
                   object_type="host", object=host, evidence_type="authentication")
        attrs.update(logon_type=ed.get("LogonType"), src_ip=ed.get("IpAddress"),
                     workstation=ed.get("WorkstationName"), auth_package=ed.get("AuthenticationPackageName"),
                     logon_process=ed.get("LogonProcessName"), key_length=ed.get("KeyLength"))
    elif eid == 4648:
        user = strip_domain(ed.get("SubjectUserName"))
        target = ed.get("TargetServerName") or host
        out.update(user=user, subject_type="user", subject=user or "unknown", action="EXPLICIT_CREDENTIAL_LOGON",
                   object_type="host", object=target, evidence_type="authentication")
        attrs.update(target_user=strip_domain(ed.get("TargetUserName")), process=basename(ed.get("ProcessName")))
    elif eid in (4656, 4663):
        out.update(subject_type="process", subject=basename(ed.get("ProcessName")), action="HANDLE_REQUEST",
                   object_type="process", object=basename(ed.get("ObjectName")), evidence_type="process_access")
        attrs.update(access_mask=ed.get("AccessMask"))
        out["user"] = strip_domain(ed.get("SubjectUserName"))
    elif eid == 4688:
        out.update(subject_type="process", subject=basename(ed.get("ParentProcessName")), action="PROCESS_CREATE",
                   object_type="process", object=basename(ed.get("NewProcessName")), evidence_type="process_event")
        attrs.update(command_line=ed.get("CommandLine", ""))
        out["user"] = strip_domain(ed.get("SubjectUserName"))
    elif eid in (1102, 104):
        out.update(user=strip_domain(ed.get("SubjectUserName")), subject_type="user",
                   subject=strip_domain(ed.get("SubjectUserName")) or "unknown", action="LOG_CLEARED",
                   object_type="service", object=ed.get("Channel", "Security"), evidence_type="log_event")
    elif eid == 4769:
        user = strip_domain(ed.get("TargetUserName"))
        out.update(user=user, subject_type="user", subject=user or "unknown", action="TGS_REQUEST",
                   object_type="service", object=str(ed.get("ServiceName")), evidence_type="authentication")
        attrs.update(ticket_encryption=ed.get("TicketEncryptionType"), src_ip=ed.get("IpAddress"))
    elif eid == 5140:
        user = strip_domain(ed.get("SubjectUserName"))
        out.update(user=user, subject_type="user", subject=user or "unknown", action="SHARE_ACCESS",
                   object_type="file", object=str(ed.get("ShareName")), evidence_type="share_access")
        attrs.update(src_ip=ed.get("IpAddress"))
    elif eid == 7045:
        out.update(subject_type="service", subject="services.exe", action="SERVICE_INSTALL",
                   object_type="service", object=str(ed.get("ServiceName")).lower(), evidence_type="service_event")
        attrs.update(image_path=ed.get("ImagePath"))
        out["artifact_class"] = "authentication_logs"
    elif eid == 4698:
        out.update(user=strip_domain(ed.get("SubjectUserName")), subject_type="user",
                   subject=strip_domain(ed.get("SubjectUserName")) or "unknown", action="SCHEDULED_TASK_CREATE",
                   object_type="service", object=str(ed.get("TaskName")), evidence_type="scheduled_task")
    elif eid == 4719:
        out.update(user=strip_domain(ed.get("SubjectUserName")), subject_type="user",
                   subject=strip_domain(ed.get("SubjectUserName")) or "unknown", action="AUDIT_POLICY_CHANGE",
                   object_type="service", object="audit_policy", evidence_type="log_event")
    else:
        out.update(subject_type="other", subject="unknown", action=f"WINEVENT_{eid}",
                   object_type="other", object="", evidence_type="windows_other")
    return out


# ---------------------------------------------------------------------------
# PowerShell operational log & console history
# ---------------------------------------------------------------------------
def adapt_powershell(raw: RawEvent) -> dict[str, Any]:
    ed = raw.get("EventData", {}) or {}
    out = _base(raw, "powershell")
    out["artifact_class"] = "powershell_logs"
    out.update(subject_type="process", subject="powershell.exe", action="SCRIPT_BLOCK",
               object_type="other", object=f"scriptblock:{ed.get('ScriptBlockId', '')}",
               evidence_type="powershell_script")
    out["attributes"].update(script_text=ed.get("ScriptBlockText", ""))
    return out


def adapt_powershell_history(raw: RawEvent) -> dict[str, Any]:
    commands = raw.get("commands", [])
    return {
        "source": "powershell",
        "host": raw.get("host"),
        "user": strip_domain(raw.get("user")),
        "timestamp": raw.get("timestamp"),
        "raw_event_ref": raw.get("raw_event_ref") or "psreadline:ConsoleHost_history.txt",
        "subject_type": "user",
        "subject": strip_domain(raw.get("user")) or "unknown",
        "action": "COMMAND_HISTORY",
        "object_type": "file",
        "object": raw.get("path", "ConsoleHost_history.txt"),
        "evidence_type": "powershell_history",
        "artifact_class": "powershell_logs",
        "attributes": {"commands": commands, "script_text": "\n".join(commands)},
    }
