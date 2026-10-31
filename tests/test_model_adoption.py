import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('model_adoption_app',Path(__file__).parent.parent/'agent/venture_agent_integrated.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

OLD='qwen2.5:7b';NEW='qwen2.5-coder:7b';INSTALLED={OLD:'old-digest',NEW:'new-digest'}


class ModelAdoptionTests(unittest.TestCase):
    """A winning comparison must be adoptable and then really reversible (owner control)."""

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.old=(app.DB,app.OUT);app.DB=root/'agent.db';app.OUT=root/'out';app.OUT.mkdir();app.init()
        tasks=[t for t,_,_ in app.benchmark_tasks()]
        self.report=dict(policy=app.MODEL_BENCHMARK_POLICY,task_signature=app.benchmark_task_signature(),run_id='run-1',
            status='完了',baseline=OLD,candidate=NEW,general_model=OLD,installed=INSTALLED,
            results=[dict(model=m,task=t) for m in (OLD,NEW) for t in tasks])
        app.save_benchmark_state(self.report)
        for p in (patch.object(app,'benchmark_model_digests',return_value=INSTALLED),
                  patch.object(app,'benchmark_source_valid',return_value=True),
                  patch.object(app,'benchmark_result_valid',side_effect=lambda r:r['model']==NEW)):
            p.start();self.addCleanup(p.stop)

    def tearDown(self):
        app.DB,app.OUT=self.old;self.tmp.cleanup()

    def test_winning_candidate_can_be_adopted_and_restored(self):
        self.assertTrue(app.benchmark_candidate_wins(app.benchmark_state()))
        self.assertEqual(app.adopt_benchmark_candidate(app.config()),NEW)
        self.assertEqual(app.config()['code_model'],NEW);self.assertEqual(app.config()['model'],OLD)
        self.assertEqual(app.coding_config(app.config(),'repair')['model'],NEW)
        self.assertEqual(app.restore_previous_code_model(),OLD)
        for task in ('new','repair','other'):
            self.assertEqual(app.coding_config(app.config(),task)['model'],OLD)

    def test_new_comparison_routes_again_after_an_earlier_restore(self):
        app.adopt_benchmark_candidate(app.config());app.restore_previous_code_model()
        app.save_benchmark_state(dict(self.report,run_id='run-2'))
        self.assertEqual(app.coding_config(app.config(),'new')['model'],NEW)

    def test_changed_configuration_still_blocks_adoption(self):
        cfg=app.config();cfg['model']='another-general-model'
        app.execute('UPDATE autonomous_control SET config=? WHERE id=1',(app.json.dumps(cfg),))
        with self.assertRaises(ValueError):app.adopt_benchmark_candidate(app.config())


if __name__=='__main__':
    unittest.main()
