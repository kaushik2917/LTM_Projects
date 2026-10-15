"""Actual supplied benchmark checks; synthetic test results are not real validation."""
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app import synthetic_temporal as temporal
from app.temporal_prediction import evaluate
from app.services import workflow_service as workflow
from app.services.future_prediction_service import predict
from app.attack_normalization import audit_techniques, normalize
from app.services.attack_service import catalog


class SyntheticTemporalTests(unittest.TestCase):
    def setUp(self):
        # These regression tests reconstruct the preserved v1.0.1 artifact.
        self.legacy = patch("app.temporal_experiment.POINTER", Path("__legacy_test_no_v2_pointer__"))
        self.legacy.start()
        self.addCleanup(self.legacy.stop)

    @classmethod
    def setUpClass(cls):
        cls.contents = {name: (temporal.DIRECTORY / name).read_bytes() for name in temporal.FILES | {"dataset_manifest.json"}}
        cls.metadata, cls.groups, cls.records = temporal.validate(cls.contents)

    def mutate_csv(self, name, mutate):
        contents = dict(self.contents)
        rows = temporal.csv_rows(contents[name])
        mutate(rows)
        handle = io.StringIO(newline="")
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        contents[name] = handle.getvalue().encode()
        manifest = json.loads(contents["dataset_manifest.json"])
        manifest["files"][name] = {"sha256": hashlib.sha256(contents[name]).hexdigest(), "bytes": len(contents[name])}
        contents["dataset_manifest.json"] = json.dumps(manifest).encode()
        return contents

    def test_import_hashes_counts_and_supplied_partitions(self):
        meta = self.metadata
        self.assertEqual(meta["version"], "1.0.1")
        self.assertEqual((meta["scenario_count"], meta["event_count"], meta["sample_count"]), (600, 4175, 3575))
        self.assertEqual(meta["scenario_counts"], {"train": 480, "validation": 60, "test": 60})
        self.assertEqual(meta["sample_counts"], {"train": 2855, "validation": 360, "test": 360})
        self.assertTrue(all(not ids for ids in meta["scenario_overlap"].values()))
        self.assertEqual(meta["target_classes_absent_from_training"]["test"], ["T1547.001"])
        corrupted = dict(self.contents); corrupted["next_technique_samples.csv"] += b"\n"
        with self.assertRaisesRegex(ValueError, "SHA-256"): temporal.validate(corrupted)

    def test_reject_scenario_overlap_wrong_targets_and_future_evidence(self):
        for name, mutate, error in (
            ("temporal_evidence_events.csv", lambda rows: rows[0].update(split="test"), "multiple splits"),
            ("next_technique_samples.csv", lambda rows: rows[0].update(target_next_technique_id="T9999"), "target_next_technique_id"),
            ("next_technique_samples.csv", lambda rows: rows[0].update(supporting_evidence_ids=rows[0]["target_event_id"]), "supporting_evidence_ids"),
            ("next_technique_samples.csv", lambda rows: rows[0].update(split="test"), "split"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                temporal.validate(self.mutate_csv(name, mutate))

    def test_authoritative_timestamp_sorting(self):
        changed = self.mutate_csv("temporal_evidence_events.csv", lambda rows: rows.reverse())
        _, groups, records = temporal.validate(changed)
        self.assertEqual(groups, self.groups)
        self.assertEqual(records, self.records)

    def test_training_counts_and_saved_test_predictions_reproduce_metrics(self):
        model, report, reason = temporal.qualified_model()
        self.assertIsNone(reason)
        self.assertEqual(report["model_name"], "transition_frequency")
        _, normalized_groups, normalized = normalize(self.metadata, self.groups, self.records)
        train_targets = Counter(r["target_next_technique_id"] for r in normalized if r["split"] == "train")
        self.assertEqual(model.prior, train_targets)
        self.assertNotIn("T1547.001", model.classes_)
        self.assertNotIn("T1562.001", model.classes_)
        self.assertNotIn("T1077", model.classes_)
        rows = temporal.csv_rows(Path(report["test_predictions_path"]).read_bytes())
        self.assertEqual(len(rows), 360)
        actual = [r["true_technique"] for r in rows]
        p = [[json.loads(r["probabilities"])[c] for c in model.classes_] for r in rows]
        test_samples = [r for r in normalized if r["split"] == "test"]
        test_features = [temporal.sequence_features(normalized_groups[r["scenario_id"]][:int(r["prefix_length"])]) for r in test_samples]
        self.assertEqual(model.predict_proba(test_features), p)
        self.assertEqual([r["target_next_technique_id"] for r in test_samples], actual)
        metrics = evaluate(actual, p, model.classes_)
        self.assertEqual(metrics, report["evaluation"]["test"]["model"])
        self.assertEqual(sum(map(sum, metrics["confusion_matrix"])), 360)
        # An unseen true class contributes its full missing probability mass to Brier.
        self.assertEqual(evaluate(["UNSEEN"], [[1., 0.]], ["A", "B"])["multiclass_brier_score"], 2.)

    def test_catalog_normalization_and_complete_provenance(self):
        meta, groups, records = normalize(self.metadata, self.groups, self.records)
        audit = meta["normalization"]
        self.assertEqual(audit["mapping"]["T1077"], "T1021.002")
        self.assertEqual(audit["mapping"]["T1562.001"], "T1685")
        self.assertEqual(audit["merged_classes"], {"T1021.002": ["T1021.002", "T1077"]})
        self.assertEqual(len(audit["techniques"]), 20)
        self.assertIsNone(audit["source_attack_version"])
        self.assertEqual({r["original_id"] for r in audit["techniques"] if r["revoked"]}, {"T1077", "T1562.001"})
        self.assertTrue(all(tid in catalog()["techniques"] for tid in audit["mapping"].values()))
        self.assertEqual(len(records), 3575)
        self.assertEqual(meta["normalized_class_counts"], {"event_classes": 19, "target_classes": 18, "trained_target_classes": 16})
        self.assertEqual(sum(meta["event_class_distribution"].values()), 4175)
        self.assertEqual(sum(meta["target_class_distribution"].values()), 3575)
        self.assertEqual({r["normalized_tactic"] for r in audit["tactic_corrections"]}, {"Stealth", "Defense Impairment"})
        for raw, normalized in zip(self.records, records):
            for key in ("sample_id", "scenario_id", "split", "cutoff_timestamp", "supporting_evidence_ids", "target_event_id"):
                self.assertEqual(raw[key], normalized[key])
            self.assertEqual(normalized["target_next_technique_id"], audit["mapping"][raw["target_next_technique_id"]])
        with self.assertRaisesRegex(ValueError, "Invalid ATT&CK"): audit_techniques({"T9999": "Invalid"})
        _, report, reason = temporal.qualified_model()
        self.assertIsNone(reason)
        for key in ("model_name", "model_version", "algorithm", "training_dataset", "training_dataset_version", "training_scenarios", "validation_scenarios", "test_scenarios", "training_timestamp", "random_seed", "feature_definition", "target_definition"):
            self.assertIn(key, report)
        self.assertEqual(report["dataset"]["normalization"], audit)
        with patch.object(temporal, "catalog", return_value={**catalog(), "sha256": "changed"}):
            self.assertIn("catalog changed", temporal.qualified_model()[2])

    def test_transition_explanation_reconstructs_probability_from_training_only(self):
        events = workflow.snapshot("INC-00001")["evidence"]
        result = predict(events, "INC-00001", "2026-09-25T10:05:02")
        self.assertEqual(result["current_mapping_status"], "CANDIDATE")
        self.assertEqual(result["observed_technique_prefix"], ["T1059.001", "T1003.001"])
        self.assertTrue(all(e["timestamp"] <= result["cutoff_timestamp"] for e in result["observed_prefix"]))
        transition = result["transition_evidence"]
        _, _, records = normalize(self.metadata, self.groups, self.records)
        by_id = {r["sample_id"]: r for r in records}
        matched = [by_id[sample_id] for sample_id in transition["training_sample_ids"]]
        self.assertTrue(all(row["split"] == "train" for row in matched))
        self.assertEqual(len(matched), transition["total_training_samples"])
        counts = Counter(row["target_next_technique_id"] for row in matched)
        self.assertEqual(counts, transition["target_counts"])
        for p in result["predictions"]:
            self.assertEqual(p["probability"], counts[p["predicted_technique"]] / len(matched))
            self.assertIn(p["predicted_technique"], catalog()["techniques"])
        self.assertAlmostEqual(sum(p["probability"] for p in result["predictions"]), 1)
        # No implicit merging at display time: the model itself only has active IDs.
        self.assertEqual(result["predicted_technique_id"], "T1021.002")
        self.assertEqual(temporal.load_dataset()[0]["verified_sha256"], self.metadata["verified_sha256"])

    def test_inference_cutoff_evidence_and_no_target_features(self):
        events = workflow.snapshot("INC-00001")["evidence"]
        cutoff = events[3]["timestamp"]
        result = predict(events, "INC-00001", cutoff)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["supporting_evidence_ids"], [f"EV-{i:05}" for i in range(1, 5)])
        self.assertAlmostEqual(result["uncertainty"], temporal.entropy(list(result["probability_distribution"].values())))
        self.assertTrue(all(e["timestamp"] <= cutoff for e in result["observed_prefix"]))
        changed = deepcopy(events)
        for event in changed:
            event.update(target_next_technique_id="T9999", target_event_id="FUTURE", split="test")
        for event in changed[4:]: event.update(attack_technique_id="T1486", source="FUTURE")
        altered = predict(list(reversed(changed)), "INC-00001", cutoff)
        self.assertEqual(altered["features"], result["features"])
        self.assertEqual(altered["predictions"], result["predictions"])
        model, _, _ = temporal.qualified_model()
        actual = dict(zip(model.classes_, model.predict_proba([result["features"]])[0]))
        self.assertEqual({p["predicted_technique"]: p["probability"] for p in result["predictions"]}, actual)
        self.assertAlmostEqual(sum(actual.values()), 1.)
        full = predict(events, "INC-00001", events[-1]["timestamp"])
        self.assertEqual(full["supporting_evidence_ids"], [f"EV-{i:05}" for i in range(1, 7)])
        self.assertEqual(full["current_technique_id"], "T1003.001")
        self.assertNotIn("INC-00001", {r["incident_id"] for r in self.records})

    def test_record_provenance_failure_and_simulation_safety(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(workflow, "DB", Path(directory) / "audit.sqlite3"):
            client = TestClient(app)
            response = client.post("/api/workflow/INC-00001/prediction", json={"cutoff_timestamp": "2026-09-25T10:06:00"})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["status"], "available")
            saved = workflow.history("INC-00001")[0]["result"]
            for key in ("prediction_id", "incident_id", "timestamp", "cutoff_timestamp", "current_technique_id", "predicted_technique_id", "predicted_technique_name", "probability", "model_name", "model_version", "training_dataset", "training_dataset_version", "supporting_evidence_ids", "prediction_horizon", "synthetic_data", "uncertainty_status"):
                self.assertIn(key, saved)
            self.assertEqual(saved["prediction_id"], result["prediction_id"])
            self.assertEqual(client.post("/api/workflow/INC-00001/prediction", json={"cutoff_timestamp": "2026-09-25T10:06:00"}).json()["prediction_id"], result["prediction_id"])
            self.assertTrue(workflow.verify_chain("INC-00001")["verified"])
            self.assertEqual({r["kind"] for r in workflow.history("INC-00001")}, {"future_prediction"})
            with patch.object(temporal, "qualified_model", return_value=(None, None, "Dataset SHA-256 mismatch: test")):
                failure = client.post("/api/workflow/INC-00001/prediction", json={"cutoff_timestamp": "2026-09-25T10:06:00"}).json()
                self.assertEqual(failure["status"], "not_available")
                self.assertEqual(failure["predictions"], [])
                self.assertIn("SHA-256 mismatch", failure["reason"])


if __name__ == "__main__":
    unittest.main()
