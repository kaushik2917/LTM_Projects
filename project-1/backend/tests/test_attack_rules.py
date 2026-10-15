"""Candidate-rule regressions using inert telemetry strings and the pinned catalog."""
import unittest

from app.services.attack_service import catalog, map_event


class AttackRuleTests(unittest.TestCase):
    def test_lsass_minidump_is_an_uncalibrated_candidate(self):
        for image, command in (
            (r"C:\Windows\System32\rundll32.exe", r"rundll32.exe C:\Windows\System32\comsvcs.dll,MiniDump"),
            (r"C:\Windows\System32\RUNDLL32.EXE", "COMSVCS.DLL,MINIDUMP"),
            ("", "RUNDLL32.EXE COMSVCS.DLL,MINIDUMP"),
        ):
            with self.subTest(image=image, command=command):
                matches = map_event({"properties": {"image_path": image, "command_line": command}})
                self.assertEqual(len(matches), 1)
                candidate = matches[0]
                self.assertEqual(candidate["technique_id"], "T1003.001")
                for key, value in catalog()["techniques"]["T1003.001"].items():
                    self.assertEqual(candidate[key], value)
                self.assertEqual(candidate["name"], "LSASS Memory")
                self.assertEqual(candidate["mapping_status"], "CANDIDATE")
                self.assertEqual(candidate["label_source"], "behavior_rule")
                self.assertIsNone(candidate["confidence"])
                self.assertEqual(candidate["basis"], "LSASS-memory-related MiniDump pattern observed")
                self.assertEqual(candidate["mapping_reason"], candidate["basis"])
                self.assertIn("no calibrated confidence", candidate["confidence_reason"])

    def test_lsass_rule_requires_all_three_indicators(self):
        for command in ("rundll32.exe comsvcs.dll", "rundll32.exe MiniDump", "comsvcs.dll MiniDump", "lsass.exe"):
            with self.subTest(command=command):
                self.assertNotIn("T1003.001", [c["technique_id"] for c in map_event({"properties": {"command_line": command}})])
