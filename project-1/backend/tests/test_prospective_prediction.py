import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from app import prospective_prediction as p
from app.services import research_service as research


class ProspectiveTests(unittest.TestCase):
    def test_smoothed_history_and_unseen_suffix(self):
        rows=[{f"technique_suffix_{i}":"A" for i in range(1,6)} for _ in range(4)]
        model=p.SmoothedHistory(5,5).fit(rows,["X","X","X","Y"])
        values=model.predict_proba(rows[:1])[0]
        np.testing.assert_allclose(values,[.75,.25])
        self.assertTrue(all(0<v<1 for v in values))
        np.testing.assert_allclose(model.predict_proba([{f"technique_suffix_{i}":"UNSEEN" for i in range(1,6)}])[0],values)

    def test_development_excludes_old_test_and_roles_disjoint(self):
        rows, roles, registry=p.development()
        self.assertEqual({k:len(v) for k,v in roles.items()},dict(train=700,validation=100,probability_calibration=25,conformal_calibration=25))
        ids=[sid for part in roles.values() for sid in part]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertFalse(set(ids)&set(registry['scenario_ids'][850:]))
        boundaries=[(min(p.stamp(r['cutoff_timestamp']) for r in part),max(p.stamp(r['target_timestamp']) for r in part)) for part in rows.values()]
        for left,right in zip(boundaries,boundaries[1:]):self.assertLess(left[1],right[0])

    def test_generator_determinism_and_disjointness(self):
        spec={'templates':{'T1003.001':[{'source':'fixture','action':'test'}], 'T1059.001':[{'source':'fixture','action':'test'}]},
              'adjacency':{'T1003.001':{'T1059.001':1},'T1059.001':{'T1003.001':1}},'scenario_count':10,
              'registry':{'paths':[],'last_timestamp':'2029-01-01T00:00:00Z'}}
        first=p.generate_test(spec,42)
        self.assertEqual(first,p.generate_test(spec,42))
        paths=[p.digest([e['technique_id'] for e in s['events']]) for s in first['scenarios']]
        self.assertEqual(len(set(paths)),10)
        for scenario in first['scenarios']:
            row=p.sample(scenario,2)
            original=row['features']
            scenario['events'][-1]['technique_id']='FUTURE SECRET'
            self.assertEqual(original,p.sample(scenario,2)['features'])
            self.assertLess(p.stamp(row['cutoff_timestamp']),p.stamp(row['target_timestamp']))

    def test_finite_sample_conformal_and_set_metrics(self):
        labels=['A','B']
        values=np.array([[.8,.2]]*25)
        threshold=p.conformal_threshold(values,['A']*25,labels)
        self.assertAlmostEqual(threshold,.2)
        measured=p.set_metrics(values,['A']*25,labels,threshold)
        self.assertEqual(measured['conformal_coverage'],1)
        self.assertEqual(measured['average_prediction_set_size'],1)
        self.assertEqual(p.conformal_threshold([[.8,.2]],['A'],labels),1.)

    def test_single_evaluation_lock_and_frozen_hash_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            p.write_exclusive(root/'evaluation_started.json',{'already':'evaluated'})
            with patch.object(p,'load_frozen',return_value={}), patch.object(p,'sha256',return_value='fixture'):
                with self.assertRaises(FileExistsError):p.evaluate_once(root)
            p.write_exclusive(root/'frozen.json',{'model_hash':'bad'})
            (root/'model.joblib').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Frozen artifact changed'):p.load_frozen(root)

    def test_advisory_score_is_explicitly_unnormalized(self):
        from app.api.research import examples
        context=examples()['responses']
        result=research.responses(context,{'T1003.001':1.})
        self.assertFalse(result['objective_normalized'])
        self.assertAlmostEqual(result['objective_weight_sum'],1.2)
        for candidate in result['candidates']:
            self.assertAlmostEqual(candidate['objective_score'],candidate['base_objective_score']+candidate['future_prediction_contribution'])
        self.assertEqual(result['execution'],'recommendation_only')
