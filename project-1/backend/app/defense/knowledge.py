"""Versioned ATT&CK -> mitigation -> local-control mapping.

Mitigations come only from 'mitigates' relationships in the pinned ATT&CK
STIX bundle. Local controls are the configured, allowlisted response actions.
D3FEND is reported as NOT_LOADED until an approved source is supplied.
"""
from functools import lru_cache
import json

from app.datasets import DATA, sha256
from app.defense.store import config
from app.services.attack_service import catalog


def mitre_id(obj):
    return next((r["external_id"] for r in obj.get("external_references", []) if r.get("source_name") == "mitre-attack"), None)


@lru_cache(maxsize=1)
def mitigation_index():
    path = DATA / "mitre" / "enterprise-attack-19.2.json"
    if not path.exists():
        return {"status": "missing", "techniques": {}}
    objects = json.loads(path.read_text(encoding="utf-8"))["objects"]
    active = lambda o: not o.get("revoked") and not o.get("x_mitre_deprecated")
    mitigations = {o["id"]: {"mitigation_id": mitre_id(o), "name": o["name"]} for o in objects
                   if o.get("type") == "course-of-action" and active(o) and (mitre_id(o) or "").startswith("M")}
    patterns = {o["id"]: mitre_id(o) for o in objects if o.get("type") == "attack-pattern" and active(o)}
    techniques = {}
    for o in objects:
        if o.get("type") == "relationship" and o.get("relationship_type") == "mitigates" and active(o):
            if o["source_ref"] in mitigations and o["target_ref"] in patterns:
                techniques.setdefault(patterns[o["target_ref"]], []).append(mitigations[o["source_ref"]])
    return {"status": "loaded", "attack_version": "19.2", "sha256": sha256(path),
            "techniques": {k: sorted(v, key=lambda m: m["mitigation_id"]) for k, v in techniques.items()}}


def defensive_mapping(technique_id):
    settings = config()["defensive_mapping"]
    index = mitigation_index()
    known = technique_id in catalog()["techniques"]
    direct = index["techniques"].get(technique_id, [])
    parent = technique_id.split(".")[0] if technique_id and "." in technique_id else None
    inherited = [] if direct or not parent else index["techniques"].get(parent, [])
    rows = [{**m, "relationship": "direct" if direct else f"inherited_from_{parent}",
             "local_controls": settings["mitigation_controls"].get(m["mitigation_id"], [])} for m in (direct or inherited)]
    return {"technique_id": technique_id, "technique_known": known,
            "technique_name": catalog()["techniques"].get(technique_id, {}).get("name"),
            "mapping_version": settings["version"], "attack_version": index.get("attack_version"),
            "attack_bundle_sha256": index.get("sha256"), "mitigations": rows,
            "local_controls": sorted({c for r in rows for c in r["local_controls"]}), "d3fend": settings["d3fend"]}
