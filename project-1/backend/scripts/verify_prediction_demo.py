r"""Safe repeatable API demonstration: inert replay plus isolated research inference.

Run from backend: ..\.venv\Scripts\python.exe scripts/verify_prediction_demo.py
Appends two inert replay events via the existing verification script.
No subprocess commands, malware, containment or model activation.
"""
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
import json
from urllib.request import urlopen

from verify_defense_demo import main as verify_defense


def main():
    captured = StringIO()
    with redirect_stdout(captured):
        verify_defense()
    operational = json.loads(captured.getvalue())
    base = "http://127.0.0.1:8001/api/research/prediction-benchmark"
    with urlopen(base, timeout=60) as response:
        benchmark = json.load(response)
    scenario = benchmark["manifest"]["splits"]["test"]["scenario_ids"][0]
    with urlopen(base + "/examples/" + scenario, timeout=60) as response:
        example = json.load(response)
    prediction = example["prediction"]
    assert prediction["model_hash"] == benchmark["model_hash"]
    assert prediction["top_k"] and 0 <= prediction["uncertainty"] <= 1
    assert datetime.fromisoformat(prediction["cutoff_timestamp"]) < datetime.fromisoformat(example["hindsight_target"]["timestamp"])
    assert example["hindsight_target"]["validated_ground_truth"] is False
    assert prediction["execution_mode"] == "DRY_RUN"
    if prediction["status"] == "ABSTAINED":
        assert prediction["probability"] is None and prediction["predicted_technique_id"] is None
        assert prediction["abstain_reason"]
    print(json.dumps({"defense_replay": operational, "synthetic_research_example": example,
                      "evaluation": benchmark["results"], "target_achieved": benchmark["target_achieved"],
                      "notice": "Research model is not qualified for observed telemetry. Defense replay legitimately abstains. No real host action executed."}, indent=2))


if __name__ == "__main__":
    main()
