"""Pinned STIX catalog. Rules emit hypotheses, not ground-truth labels."""
from functools import lru_cache
import json
from app.datasets import DATA, sha256


@lru_cache(maxsize=1)
def catalog():
    path = DATA / "mitre" / "enterprise-attack-19.2.json"
    if not path.exists():
        return {"status": "missing", "version": "19.2", "techniques": {}}
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if bundle.get("type") != "bundle":
        raise ValueError("ATT&CK file is not a STIX bundle")
    techniques = {}
    for obj in bundle["objects"]:
        if obj.get("type") != "attack-pattern" or obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack" and ref.get("external_id", "").startswith("T"):
                techniques[ref["external_id"]] = {"name": obj["name"], "stix_id": obj["id"],
                    "tactics": [p["phase_name"] for p in obj.get("kill_chain_phases", []) if p["kill_chain_name"] == "mitre-attack"]}
    return {"status": "loaded", "version": "19.2", "sha256": sha256(path), "techniques": techniques}


def map_event(raw):
    props = raw.get("properties", {})
    command = str(props.get("command_line", "")).lower()
    image = str(props.get("image_path", "")).lower()
    ids = []
    if "powershell" in image or "powershell" in command:
        ids.append(("T1059.001", "PowerShell executable/command observed"))
    if "wevtutil" in command and (" cl " in command or "clear-log" in command):
        ids.append(("T1070.001", "Event-log clearing command observed"))
    if "vssadmin" in command and "delete" in command and "shadow" in command:
        ids.append(("T1490", "Shadow-copy deletion command observed"))
    if "comsvcs.dll" in command and "minidump" in command and ("rundll32" in image or "rundll32" in command):
        ids.append(("T1003.001", "LSASS-memory-related MiniDump pattern observed"))
    techniques = catalog()["techniques"]
    return [{"technique_id": tid, **techniques[tid], "basis": reason,
             "label_source": "behavior_rule", "confidence": None, "mapping_status": "CANDIDATE",
             "mapping_reason": reason, "confidence_reason": "Deterministic rule match; no calibrated confidence available"}
            for tid, reason in ids if tid in techniques]
