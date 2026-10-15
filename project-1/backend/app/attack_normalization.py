"""Normalize synthetic labels using explicit relationships in the pinned STIX bundle."""
from collections import Counter, defaultdict
import json
import re
from app.datasets import DATA, sha256
from app.services.attack_service import catalog

VERSION = "attack-stix-replacements-v1"


def audit_techniques(names):
    path = DATA / "mitre" / "enterprise-attack-19.2.json"
    objects = json.loads(path.read_text(encoding="utf-8"))["objects"]
    by_stix = {o["id"]: o for o in objects}
    patterns = {}
    for obj in objects:
        if obj["type"] == "attack-pattern":
            for ref in obj.get("external_references", []):
                if ref.get("source_name") == "mitre-attack": patterns[ref["external_id"]] = obj
    replacements = defaultdict(list)
    for obj in objects:
        if obj["type"] == "relationship" and obj.get("relationship_type") == "revoked-by" and not obj.get("revoked"):
            replacements[obj["source_ref"]].append(obj)
    rows, mapping = [], {}
    for tid, supplied_name in sorted(names.items()):
        obj = patterns.get(tid)
        if not re.fullmatch(r"T\d{4}(?:\.\d{3})?", tid) or obj is None:
            rows.append({"original_id": tid, "status": "invalid", "reason": "ID absent from pinned catalog"})
            continue
        origin, relationships, visited = obj, [], set()
        while obj.get("revoked") or obj.get("x_mitre_deprecated"):
            links = replacements[obj["id"]]
            if obj["id"] in visited or len(links) != 1:
                raise ValueError(f"No unambiguous active ATT&CK replacement for {tid}; review required")
            visited.add(obj["id"])
            relationships.append(links[0]["id"])
            obj = by_stix[links[0]["target_ref"]]
        normalized = next(r["external_id"] for r in obj["external_references"] if r.get("source_name") == "mitre-attack")
        if normalized not in catalog()["techniques"]: raise ValueError(f"Replacement not active: {normalized}")
        mapping[tid] = normalized
        rows.append({"original_id": tid, "supplied_name": supplied_name, "catalog_name": origin["name"],
            "status": "revoked" if origin.get("revoked") else "deprecated" if origin.get("x_mitre_deprecated") else "active",
            "revoked": bool(origin.get("revoked")), "deprecated": bool(origin.get("x_mitre_deprecated")),
            "name_mismatch": supplied_name != origin["name"], "original_object_version": origin.get("x_mitre_version"),
            "normalized_id": normalized, "normalized_name": obj["name"], "normalized_object_version": obj.get("x_mitre_version"),
            "replacement_relationship_ids": relationships})
    invalid = [r["original_id"] for r in rows if r["status"] == "invalid"]
    if invalid: raise ValueError(f"Invalid ATT&CK technique IDs: {invalid}")
    merged = defaultdict(list)
    for original, normalized in mapping.items(): merged[normalized].append(original)
    return {"preprocessing_version": VERSION, "catalog_version": catalog()["version"], "catalog_sha256": sha256(path),
        "source_attack_version": None, "source_technique_versions": None,
        "version_assessment": "Source ATT&CK release/object versions NOT AVAILABLE in manifest. Revoked labels demonstrate incompatibility with the pinned catalog; exact originating release cannot be established.",
        "techniques": rows, "mapping": mapping, "invalid_ids": invalid,
        "merged_classes": {key: value for key, value in merged.items() if len(value) > 1},
        "overlap_scope": "Explicit replacement aliases merged. Semantic behavior overlap between distinct active techniques is not automatically merged.",
        "policy": "Resolve unique STIX revoked-by chains to active IDs; reject unknown or unresolved inactive IDs. Canonical names come from pinned ATT&CK. Original dataset bytes remain unchanged."}


def normalize(metadata, groups, records):
    audit = audit_techniques(metadata["technique_names"])
    active = catalog()["techniques"]
    result, tactic_changes = {}, Counter()
    for scenario, events in groups.items():
        result[scenario] = []
        for event in events:
            tid = audit["mapping"][event["technique_id"]]
            tactics = active[tid]["tactics"]
            supplied_tactic = event["tactic"].lower().replace(" ", "-")
            if supplied_tactic in tactics:
                tactic = event["tactic"]
            elif len(tactics) == 1:
                tactic = tactics[0].replace("-", " ").title().replace(" And ", " and ")
                tactic_changes[(event["technique_id"], event["tactic"], tactic)] += 1
            else:
                raise ValueError(f"Ambiguous tactic normalization for {event['technique_id']}: {event['tactic']}")
            result[scenario].append({**event, "original_technique_id": event["technique_id"],
                "original_technique_name": event["technique_name"], "technique_id": tid, "technique_name": active[tid]["name"],
                "original_tactic": event["tactic"], "tactic": tactic,
                "canonical_tactics": active[tid]["tactics"]})
    audit["tactic_corrections"] = [{"original_technique_id": tid, "original_tactic": original, "normalized_tactic": normalized, "event_count": count}
        for (tid, original, normalized), count in sorted(tactic_changes.items())]
    samples = []
    for row in records:
        sequence = result[row["scenario_id"]]
        count = int(row["prefix_length"])
        observed, target = sequence[:count], sequence[count]
        samples.append({**row, "original_target_next_technique_id": row["target_next_technique_id"],
            "original_prefix_tactics": row["prefix_tactics"], "prefix_tactics": "|".join(e["tactic"] for e in observed),
            "original_target_next_tactic": row["target_next_tactic"], "target_next_tactic": target["tactic"],
            "current_technique_id": observed[-1]["technique_id"], "current_technique_name": observed[-1]["technique_name"],
            "prefix_technique_ids": "|".join(e["technique_id"] for e in observed),
            "target_next_technique_id": target["technique_id"], "target_next_technique_name": target["technique_name"]})
    targets = {part: {r["target_next_technique_id"] for r in samples if r["split"] == part} for part in ("train", "validation", "test")}
    normalized_names = {tid: active[tid]["name"] for tid in set(audit["mapping"].values())}
    meta = {**metadata, "original_technique_names": metadata["technique_names"], "technique_names": normalized_names,
        "original_event_class_distribution": metadata["event_class_distribution"],
        "original_target_class_distribution": metadata["target_class_distribution"],
        "event_class_distribution": dict(sorted(Counter(e["technique_id"] for es in result.values() for e in es).items())),
        "target_class_distribution": dict(sorted(Counter(r["target_next_technique_id"] for r in samples).items())),
        "normalized_class_counts": {"event_classes": len(normalized_names), "target_classes": len(set.union(*targets.values())), "trained_target_classes": len(targets["train"])},
        "normalization": audit, "labels_absent_from_active_catalog": [],
        "target_classes_absent_from_training": {p: sorted(ids - targets["train"]) for p, ids in targets.items()},
        "label_policy": audit["policy"]}
    return meta, result, samples
