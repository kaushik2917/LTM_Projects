"""End-to-end v2 calculations, independent partitions and reveal boundary."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app import temporal_experiment as experiment
from app.synthetic_temporal import sequence_features
from app.temporal_prediction import evaluate, entropy, prefix
from app.services import workflow_service as workflow
from app.services.research_service import responses
from app.datasets import sha256


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.report = experiment.load()
        cls.bundle = json.loads(experiment.DATASET.read_text(encoding="utf-8"))

    def test_splits_and_duplicate_scenarios(self):
        checks = experiment.validate(self.bundle)
        groups = list(checks["scenario_ids"].values())
        for i, group in enumerate(groups):
            for other in groups[i+1:]: self.assertFalse(set(group) & set(other))
        changed = deepcopy(self.bundle)
        changed["scenarios"].append({**changed["scenarios"][0], "split": "test"})
        with self.assertRaisesRegex(ValueError, "Duplicate scenario"): experiment.validate(changed)
        changed = deepcopy(self.bundle)
        changed["scenarios"][0]["events"][0]["next_technique_id"] = "T9999"
        with self.assertRaisesRegex(ValueError, "Incorrect next label"): experiment.validate(changed)

    def test_correct_incorrect_pending_and_first_labelled_future(self):
        p = {"T1021.002": .8, "T1041": .2}
        cutoff = "2026-01-01T00:00:00Z"
        events = [{"timestamp": cutoff, "technique_id": "T1003.001"},
                  {"timestamp": "2026-01-01T00:01:00Z", "technique_id": None},
                  {"timestamp": "2026-01-01T00:02:00Z", "technique_id": "T1021.002"}]
        result = experiment.outcome(events, cutoff, p)
        self.assertTrue(result["evaluation"]["correct"])
        self.assertEqual(result["evaluation"]["prediction_rank"], 1)
        events[-1]["technique_id"] = "T1041"
        self.assertFalse(experiment.outcome(events, cutoff, p)["evaluation"]["correct"])
        self.assertEqual(experiment.outcome(events[:1], cutoff, p)["evaluation"]["status"], "PENDING_GROUND_TRUTH")
        self.assertIsNone(experiment.outcome(events[:1], cutoff, p)["evaluation"]["correct"])

    def test_cutoff_hidden_labels_cannot_change_features_or_probabilities(self):
        s = next(s for s in self.bundle["scenarios"] if s["split"] == "test")
        base = {"incident_id": s["incident_id"], "cutoff_timestamp": s["cutoff_timestamp"]}
        inventory = {e["evidence_id"] for e in s["events"]}
        first = experiment.infer(s["events"], base, inventory)
        changed = deepcopy(s["events"])
        for e in changed:
            e.update(next_technique_id="T9999", next_event_timestamp="2099-01-01T00:00:00Z")
            if e["evidence_id"] not in first["input_evidence_ids"]:
                e.update(technique_id="T1486", action="FUTURE", source="FUTURE")
        second = experiment.infer(changed, base, inventory)
        self.assertEqual(first["features"], second["features"])
        self.assertEqual(first["probability_distribution"], second["probability_distribution"])
        target = experiment.ground_truth(s["events"], s["cutoff_timestamp"])
        self.assertNotIn(target["evidence_id"], first["input_evidence_ids"])
        for values in (first["raw_probabilities"], first["calibrated_probabilities"]):
            self.assertAlmostEqual(sum(values.values()), 1.)
            self.assertTrue(all(0 <= p <= 1 for p in values.values()))
        self.assertAlmostEqual(first["uncertainty"], entropy(list(first["probability_distribution"].values())))
        self.assertEqual(entropy([1., 0.]), 0.)
        self.assertAlmostEqual(entropy([.25]*4), 1.)

    def test_recalculate_metrics_calibration_and_conformal_from_frozen_model(self):
        labels = self.model.classes_
        by_id = {s["scenario_id"]: s for s in self.bundle["scenarios"]}
        for part, records in self.report["predictions"].items():
            raw, calibrated, actual = [], [], []
            for r in records:
                s = by_id[r["scenario_id"]]
                self.assertEqual(s["split"], part)
                observed, _ = prefix(s["events"], r["cutoff_timestamp"])
                p = self.model.predict_proba([sequence_features(observed)])[0]
                c = experiment.scale(p, self.report["calibration"]["temperature"])
                self.assertEqual(dict(zip(labels, p)), r["raw_probabilities"])
                self.assertEqual(dict(zip(labels, c)), r["calibrated_probabilities"])
                self.assertNotIn(r["target_event_id"], r["input_evidence_ids"])
                raw.append(p); calibrated.append(c); actual.append(r["target"])
            self.assertEqual(evaluate(actual, calibrated, labels), self.report["partition_metrics"][part]["calibrated"])
        conformal_records = self.report["predictions"]["calibration_conformal"]
        scores = [1-r["calibrated_probabilities"][r["target"]] for r in conformal_records]
        threshold = sorted(scores)[68]  # ceil((75+1)*.9) = 69, 1-based order statistic
        self.assertEqual(experiment.conformal_quantile(scores), threshold)
        test = self.report["predictions"]["test"]
        sets = [experiment.prediction_set(list(r["calibrated_probabilities"].values()), labels, threshold) for r in test]
        coverage = sum(r["target"] in s for r,s in zip(test,sets))/len(test)
        self.assertEqual(coverage, self.report["conformal"]["measured_coverage"])
        self.assertEqual(self.report["calibration"]["ECE"], self.report["partition_metrics"]["calibration_conformal"]["calibrated"]["expected_calibration_error"])
        self.assertEqual(sum(map(sum, self.report["metrics"]["confusion_matrix"])), len(test))

    def test_reproducible_generation_without_overwriting_original(self):
        original_hash = sha256(experiment.DATASET)
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment, "DATASET", Path(directory)/"scenarios.json"):
            experiment.generate()
            self.assertEqual(sha256(experiment.DATASET), original_hash)

    def test_demo_api_reveal_audit_and_live_pending(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(workflow, "DB", Path(directory)/"audit.db"):
            client = TestClient(app)
            s = client.get("/api/research/temporal-scenarios").json()[0]
            url = f"/api/research/temporal-scenarios/{s['scenario_id']}"
            self.assertEqual(client.post(url+"/reveal", json={"prediction_id": "missing"}).status_code, 422)
            result = client.post(url+"/predict", json={"cutoff_timestamp": s["default_cutoff"]}).json()
            self.assertIsNone(result["ground_truth"]["event"])
            self.assertNotIn("next_technique_id", json.dumps(result["observed_prefix"]))
            hidden_report = client.post(url+"/report", json={"prediction_id": result["prediction_id"]}).json()
            self.assertIsNone(hidden_report["future_attack_prediction"]["ground_truth"]["event"])
            revealed = client.post(url+"/reveal", json={"prediction_id": result["prediction_id"]}).json()
            self.assertEqual(revealed["ground_truth"]["status"], "OBSERVED")
            self.assertEqual(result["probability_distribution"], revealed["probability_distribution"])
            self.assertNotIn(revealed["ground_truth"]["event"]["evidence_id"], result["input_evidence_ids"])
            self.assertTrue(workflow.verify_chain(s["incident_id"])["verified"])
            exported = client.post(url+"/report", json={"prediction_id": result["prediction_id"]}).json()
            self.assertEqual(exported["future_attack_prediction"]["evaluation"], revealed["evaluation"])
            self.assertFalse(exported["host_action_executed"])
            pending = workflow.run_prediction("INC-00001")
            self.assertEqual(pending["ground_truth"]["status"], "PENDING")
            self.assertIsNone(pending["evaluation"]["correct"])
            self.assertEqual(pending["current_mapping_status"], "CANDIDATE")
            self.assertEqual(len(pending["input_evidence_ids"]), 6)

    def test_expected_future_risk_and_objective_use_distribution(self):
        context = TestClient(app).get("/api/research/examples").json()["responses"]
        a = responses(context, {"T1021.002": .9, "T1041": .1})
        b = responses(context, {"T1021.002": .1, "T1041": .9})
        risks = {c["action"]: c["expected_future_risk"] for c in b["candidates"]}
        self.assertTrue(any(abs(c["expected_future_risk"]-risks[c["action"]]) > 1e-8 for c in a["candidates"]))
        for c in a["candidates"]:
            self.assertAlmostEqual(c["expected_future_risk"], sum(t["probability"]*t["residual_risk"] for t in c["future_risk"]["terms"]))
            self.assertAlmostEqual(c["objective_score"], c["base_objective_score"] + a["future_prediction_weight"]*c["expected_future_risk"])
        fallback = responses(context, {"T1685": 1.})["candidates"][0]
        self.assertEqual(fallback["future_risk"]["unsupported_probability_mass"], 1.)
        self.assertEqual(fallback["expected_future_risk"], fallback["residual_attack_risk"])


if __name__ == "__main__": unittest.main()
