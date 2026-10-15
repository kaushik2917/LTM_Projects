"""MITRE ATT&CK knowledge base used by the rule-based and baseline models.

This is *model knowledge* (expert priors), not tuning thresholds: the technique
catalogue, tactic ordering, expert transition priors between techniques,
intent signatures and anti-forensic behaviours. Learned models (trained
transition statistics, TC-FAPN) can replace the priors without touching callers.
"""

from __future__ import annotations

TACTIC_ORDER = [
    "Reconnaissance",
    "Resource Development",
    "Initial Access",
    "Execution",
    "Persistence",
    "Privilege Escalation",
    "Defense Evasion",
    "Credential Access",
    "Discovery",
    "Lateral Movement",
    "Collection",
    "Command and Control",
    "Exfiltration",
    "Impact",
]

# Kill-chain progression rank used to decide the *current* attack stage.
# Command and Control is an enabling channel that is typically established
# early, so it is ranked alongside Execution rather than near the end.
STAGE_RANK = {
    "Reconnaissance": 0,
    "Resource Development": 1,
    "Initial Access": 2,
    "Execution": 3,
    "Command and Control": 3,
    "Persistence": 4,
    "Privilege Escalation": 5,
    "Defense Evasion": 6,
    "Credential Access": 7,
    "Discovery": 8,
    "Lateral Movement": 9,
    "Collection": 10,
    "Exfiltration": 11,
    "Impact": 12,
}

TECHNIQUES: dict[str, dict] = {
    "T1595": {"name": "Active Scanning", "tactic": "Reconnaissance"},
    "T1110.003": {"name": "Password Spraying", "tactic": "Credential Access"},
    "T1190": {"name": "Exploit Public-Facing Application", "tactic": "Initial Access"},
    "T1566.001": {"name": "Spearphishing Attachment", "tactic": "Initial Access"},
    "T1078": {"name": "Valid Accounts", "tactic": "Initial Access"},
    "T1059.001": {"name": "PowerShell", "tactic": "Execution"},
    "T1204.002": {"name": "Malicious File", "tactic": "Execution"},
    "T1071.001": {"name": "Web Protocols", "tactic": "Command and Control"},
    "T1105": {"name": "Ingress Tool Transfer", "tactic": "Command and Control"},
    "T1003.001": {"name": "LSASS Memory", "tactic": "Credential Access"},
    "T1558.003": {"name": "Kerberoasting", "tactic": "Credential Access"},
    "T1087.002": {"name": "Domain Account Discovery", "tactic": "Discovery"},
    "T1018": {"name": "Remote System Discovery", "tactic": "Discovery"},
    "T1021": {"name": "Remote Services", "tactic": "Lateral Movement"},
    "T1021.001": {"name": "Remote Desktop Protocol", "tactic": "Lateral Movement"},
    "T1021.002": {"name": "SMB/Windows Admin Shares", "tactic": "Lateral Movement"},
    "T1021.006": {"name": "Windows Remote Management", "tactic": "Lateral Movement"},
    "T1550.002": {"name": "Pass the Hash", "tactic": "Lateral Movement"},
    "T1547.001": {"name": "Registry Run Keys / Startup Folder", "tactic": "Persistence"},
    "T1053.005": {"name": "Scheduled Task", "tactic": "Persistence"},
    "T1070.001": {"name": "Clear Windows Event Logs", "tactic": "Defense Evasion"},
    "T1070.003": {"name": "Clear Command History", "tactic": "Defense Evasion"},
    "T1070.004": {"name": "File Deletion", "tactic": "Defense Evasion"},
    "T1070.006": {"name": "Timestomp", "tactic": "Defense Evasion"},
    "T1562.001": {"name": "Disable or Modify Tools", "tactic": "Defense Evasion"},
    "T1562.002": {"name": "Disable Windows Event Logging", "tactic": "Defense Evasion"},
    "T1560.001": {"name": "Archive via Utility", "tactic": "Collection"},
    "T1041": {"name": "Exfiltration Over C2 Channel", "tactic": "Exfiltration"},
    "T1486": {"name": "Data Encrypted for Impact", "tactic": "Impact"},
    "T1490": {"name": "Inhibit System Recovery", "tactic": "Impact"},
    "T1496": {"name": "Resource Hijacking", "tactic": "Impact"},
}

# Prediction granularity: RDP and WinRM collapse into the parent "Remote
# Services" label; SMB/Admin Shares stays separate because its containment and
# evidence profile (file-share artefacts, service creation) differ.
PREDICTION_LABEL_MAP = {"T1021.001": "T1021", "T1021.006": "T1021"}


def prediction_label(technique_id: str) -> str:
    return PREDICTION_LABEL_MAP.get(technique_id, technique_id)


PREDICTION_LABELS: list[str] = sorted({prediction_label(t) for t in TECHNIQUES})


def technique_name(tid: str | None) -> str:
    if not tid:
        return ""
    return TECHNIQUES.get(tid, {}).get("name", tid)


def technique_tactic(tid: str | None) -> str | None:
    if not tid:
        return None
    return TECHNIQUES.get(tid, {}).get("tactic")


# ---------------------------------------------------------------------------
# Expert transition priors P(next technique | current technique)
# ---------------------------------------------------------------------------
_LM_FOLLOW = {"T1070.001": 0.20, "T1490": 0.18, "T1560.001": 0.14, "T1021.002": 0.10,
              "T1486": 0.16, "T1053.005": 0.08, "T1003.001": 0.08, "T1041": 0.06}
_PERSIST_FOLLOW = {"T1071.001": 0.28, "T1562.001": 0.20, "T1003.001": 0.20,
                   "T1087.002": 0.14, "T1496": 0.12, "T1070.006": 0.06}
_CLEANUP_FOLLOW = {"T1041": 0.30, "T1486": 0.30, "T1070.001": 0.40}

EXPERT_TRANSITIONS: dict[str, dict[str, float]] = {
    "T1595": {"T1110.003": 0.35, "T1190": 0.35, "T1078": 0.20, "T1566.001": 0.10},
    "T1110.003": {"T1078": 0.85, "T1110.003": 0.15},
    "T1190": {"T1059.001": 0.50, "T1105": 0.30, "T1078": 0.20},
    "T1566.001": {"T1204.002": 0.60, "T1059.001": 0.40},
    "T1078": {"T1059.001": 0.45, "T1087.002": 0.15, "T1021": 0.12, "T1547.001": 0.10, "T1003.001": 0.18},
    "T1204.002": {"T1059.001": 0.35, "T1071.001": 0.25, "T1003.001": 0.20, "T1547.001": 0.20},
    "T1059.001": {"T1071.001": 0.35, "T1105": 0.30, "T1003.001": 0.15, "T1547.001": 0.10, "T1087.002": 0.10},
    "T1071.001": {"T1105": 0.40, "T1003.001": 0.20, "T1087.002": 0.15, "T1547.001": 0.10, "T1041": 0.15},
    "T1105": {"T1204.002": 0.45, "T1003.001": 0.25, "T1053.005": 0.15, "T1547.001": 0.15},
    "T1003.001": {"T1021": 0.30, "T1078": 0.17, "T1021.002": 0.15, "T1550.002": 0.10,
                  "T1087.002": 0.08, "T1070.001": 0.08, "T1558.003": 0.06, "T1018": 0.06},
    "T1558.003": {"T1078": 0.40, "T1021": 0.30, "T1021.002": 0.30},
    "T1087.002": {"T1018": 0.40, "T1003.001": 0.30, "T1558.003": 0.30},
    "T1018": {"T1021": 0.45, "T1021.002": 0.25, "T1003.001": 0.20, "T1550.002": 0.10},
    "T1021": dict(_LM_FOLLOW),
    "T1021.002": dict(_LM_FOLLOW),
    "T1550.002": dict(_LM_FOLLOW),
    "T1547.001": dict(_PERSIST_FOLLOW),
    "T1053.005": dict(_PERSIST_FOLLOW),
    "T1562.001": {"T1496": 0.40, "T1070.001": 0.30, "T1486": 0.30},
    "T1562.002": {"T1070.001": 0.40, "T1486": 0.30, "T1490": 0.30},
    "T1070.001": {"T1490": 0.50, "T1486": 0.30, "T1041": 0.20},
    "T1490": {"T1486": 0.90, "T1070.001": 0.10},
    "T1560.001": {"T1041": 0.90, "T1070.003": 0.10},
    "T1041": {"T1070.003": 0.40, "T1070.001": 0.40, "T1070.004": 0.20},
    "T1486": {"T1070.001": 0.60, "T1490": 0.40},
    "T1496": {"T1070.006": 0.50, "T1562.001": 0.50},
    "T1070.003": dict(_CLEANUP_FOLLOW),
    "T1070.004": dict(_CLEANUP_FOLLOW),
    "T1070.006": dict(_CLEANUP_FOLLOW),
}

# ---------------------------------------------------------------------------
# Attacker intents
# ---------------------------------------------------------------------------
INTENTS: dict[str, dict] = {
    "ransomware": {"label": "Ransomware deployment", "prior": 0.35},
    "data_theft": {"label": "Data theft / espionage", "prior": 0.30},
    "cryptojacking": {"label": "Cryptojacking", "prior": 0.15},
    "access_persistence": {"label": "Access brokering / long-term persistence", "prior": 0.20},
}

# P(technique observed | intent) - naive-Bayes style likelihoods.
INTENT_TECHNIQUE_AFFINITY: dict[str, dict[str, float]] = {
    "ransomware": {
        "T1003.001": 0.80, "T1021": 0.80, "T1021.002": 0.80, "T1550.002": 0.60, "T1490": 0.95,
        "T1486": 0.99, "T1070.001": 0.70, "T1078": 0.60, "T1558.003": 0.50, "T1059.001": 0.60,
        "T1087.002": 0.50, "T1562.001": 0.40, "T1041": 0.25, "T1560.001": 0.20, "T1496": 0.02,
        "T1547.001": 0.30, "T1105": 0.60, "T1071.001": 0.60,
    },
    "data_theft": {
        "T1560.001": 0.90, "T1041": 0.95, "T1003.001": 0.60, "T1021": 0.60, "T1021.002": 0.50,
        "T1087.002": 0.60, "T1018": 0.60, "T1547.001": 0.60, "T1070.003": 0.60, "T1486": 0.02,
        "T1490": 0.02, "T1496": 0.02, "T1071.001": 0.80, "T1070.001": 0.30, "T1059.001": 0.60,
    },
    "cryptojacking": {
        "T1496": 0.99, "T1053.005": 0.70, "T1562.001": 0.70, "T1105": 0.80, "T1003.001": 0.15,
        "T1021": 0.20, "T1021.002": 0.20, "T1486": 0.01, "T1041": 0.05, "T1190": 0.50,
        "T1560.001": 0.03, "T1490": 0.03,
    },
    "access_persistence": {
        "T1547.001": 0.90, "T1053.005": 0.70, "T1078": 0.80, "T1071.001": 0.80, "T1070.006": 0.70,
        "T1003.001": 0.40, "T1486": 0.02, "T1041": 0.10, "T1490": 0.02, "T1496": 0.05,
    },
}
DEFAULT_AFFINITY = 0.30

# Context signals that shift intent likelihoods (multiplicative).
INTENT_CONTEXT_SIGNALS = {
    "ti_tag_ransomware": {"ransomware": 3.0},
    "ti_tag_apt": {"data_theft": 2.5},
    "ti_tag_miner": {"cryptojacking": 3.0},
    "backup_or_admin_account": {"ransomware": 1.8},
    "high_value_server_target": {"ransomware": 1.3, "data_theft": 1.3},
    "large_outbound_transfer": {"data_theft": 3.0},
}

# ---------------------------------------------------------------------------
# Anti-forensic behaviours (AFIP)
# ---------------------------------------------------------------------------
# weights: logistic weights over AFIP features (see prediction/anti_forensic.py)
ANTI_FORENSIC_BEHAVIORS: dict[str, dict] = {
    "clear_windows_event_logs": {
        "label": "Clear Windows event logs", "technique": "T1070.001",
        "threatens": {"authentication_logs": 1.0, "sysmon_logs": 0.9},
        "bias": -2.6,
        "weights": {"seq_reach": 3.0, "intent_ransomware": 2.2, "intent_data_theft": 0.8,
                    "credential_access": 1.1, "admin_privileges": 0.9, "lateral_signal": 0.8,
                    "observed_defense_evasion": 1.0},
    },
    "delete_powershell_history": {
        "label": "Delete PowerShell history", "technique": "T1070.003",
        "threatens": {"powershell_logs": 1.0},
        "bias": -2.4,
        "weights": {"seq_reach": 3.0, "powershell_used": 1.4, "intent_data_theft": 1.2,
                    "intent_ransomware": 0.6, "observed_defense_evasion": 0.8},
    },
    "disable_sysmon": {
        "label": "Disable Sysmon", "technique": "T1562.001",
        "threatens": {"sysmon_logs": 0.6},
        "bias": -2.3,
        "weights": {"seq_reach": 2.5, "admin_privileges": 1.1, "intent_ransomware": 1.3,
                    "intent_cryptojacking": 1.5, "credential_access": 0.6, "lateral_signal": 0.5},
    },
    "disable_audit_subsystem": {
        "label": "Disable audit subsystem", "technique": "T1562.002",
        "threatens": {"authentication_logs": 0.6},
        "bias": -3.0,
        "weights": {"seq_reach": 2.0, "admin_privileges": 1.0, "intent_ransomware": 0.9,
                    "observed_defense_evasion": 0.8},
    },
    "remove_malware": {
        "label": "Remove malware / tools", "technique": "T1070.004",
        "threatens": {"disk_artifacts": 0.8, "process_state": 0.4},
        "bias": -2.5,
        "weights": {"seq_reach": 2.0, "malware_on_disk": 1.4, "intent_data_theft": 1.0,
                    "intent_access_persistence": 0.6},
    },
    "timestomp_files": {
        "label": "Timestomp files", "technique": "T1070.006",
        "threatens": {"disk_artifacts": 0.3},
        "bias": -3.0,
        "weights": {"seq_reach": 2.5, "malware_on_disk": 1.0, "intent_access_persistence": 1.8},
    },
    "wipe_files": {
        "label": "Wipe files", "technique": "T1070.004",
        "threatens": {"disk_artifacts": 0.9},
        "bias": -3.4,
        "weights": {"seq_reach": 1.0, "intent_ransomware": 1.0, "malware_on_disk": 0.8},
    },
    "modify_logs": {
        "label": "Modify / selectively delete logs", "technique": "T1070",
        "threatens": {"authentication_logs": 0.5, "sysmon_logs": 0.5},
        "bias": -3.2,
        "weights": {"seq_reach": 1.5, "admin_privileges": 1.0, "intent_data_theft": 1.0,
                    "intent_access_persistence": 0.8},
    },
    "fabricate_events": {
        "label": "Fabricate / inject events", "technique": "T1070",
        "threatens": {},
        "bias": -3.8,
        "weights": {"admin_privileges": 0.8, "intent_data_theft": 0.8, "poisoning_signal": 3.0},
    },
    "disable_monitoring_agents": {
        "label": "Disable monitoring / EDR agents", "technique": "T1562.001",
        "threatens": {"sysmon_logs": 0.5, "network_connections": 0.3},
        "bias": -2.8,
        "weights": {"seq_reach": 2.0, "admin_privileges": 1.0, "intent_cryptojacking": 1.3,
                    "intent_ransomware": 0.9},
    },
}

# Evidence types that reveal attacker preparation for a *specific* next step
# (precursor signals) and how they shift the next-technique distribution.
PRECURSOR_SIGNALS = {
    "explicit_credential_remote": {
        "boost": {"T1021": 2.2, "T1021.002": 1.6, "T1078": 1.5, "T1550.002": 1.2},
        "text": "explicit use of harvested credentials against a remote host",
    },
    "remote_session_command": {
        "boost": {"T1021": 3.0, "T1021.002": 1.3},
        "text": "PowerShell history contains remote-session commands (Enter-PSSession / Invoke-Command)",
    },
    "admin_share_command": {
        "boost": {"T1021.002": 3.0},
        "text": "command history references administrative shares (\\\\host\\ADMIN$ / C$)",
    },
    "log_clear_command": {
        "boost": {"T1070.001": 3.0},
        "text": "command history references event-log clearing utilities",
    },
    "shadow_copy_command": {
        "boost": {"T1490": 3.0},
        "text": "command history references shadow-copy deletion",
    },
    "archive_command": {
        "boost": {"T1560.001": 3.0, "T1041": 1.5},
        "text": "command history references archiving utilities",
    },
}
