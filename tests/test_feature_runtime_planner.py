import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def runner_module():
    spec = importlib.util.spec_from_file_location('planner_runtime_runner', ROOT / 'scripts/run-feature-campaign.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimePlannerEvidenceTests(unittest.TestCase):
    def receipt(self, runner, environment, profile=None):
        info = {'Image': 'sha256:pinned', 'HostConfig': {'NanoCpus': 4_000_000_000, 'Memory': 4 * 1024**3},
                'Config': {'Env': environment}}
        images = {'honua': {'id': 'sha256:pinned', 'labels': {'honua.runtime.compilation': 'native-aot'}}}
        with patch.object(runner, 'inspect', return_value=info), \
                patch.object(runner, 'docker_engine_identity', return_value={}), \
                patch.object(runner, 'command', side_effect=['native mappings', '/app/Honua.Server\x00']):
            if profile is None:
                return runner.runtime_receipt({'honua': 'owned-container'}, images)
            return runner.runtime_receipt({'honua': 'owned-container'}, images, honua_profile=profile)

    def test_receipt_records_exact_shared_profile_keys_without_database_secrets(self):
        runner = runner_module()
        # Future profiles must not need a second hard-coded receipt allowlist.
        profiles = {**runner.HONUA_PROFILES, 'future-count-profile': {'Database__PreferSerialSourceSpatialCounts': 'true'}}
        keys = set().union(*(set(options) for options in profiles.values()))
        expected = [key + '=true' for key in sorted(keys)]
        excluded = ['Database__Password=secret', 'Database__ConnectionString=secret',
                    'ConnectionStrings__DefaultConnection=secret',
                    'Database__DisableJitForSourceSpatialCountsPassword=secret']
        with patch.object(runner, 'HONUA_PROFILES', profiles):
            result = self.receipt(runner, expected + excluded + ['OgcFeatures__NumberMatchedPolicy=Exact'])
        self.assertEqual(expected + ['OgcFeatures__NumberMatchedPolicy=Exact'], result['honua']['environment'])

    def test_runtime_rejects_missing_wrong_and_unrequested_planner_options(self):
        runner = runner_module()
        for profile, options in runner.HONUA_PROFILES.items():
            actual = [key + '=' + value for key, value in options.items()]
            with self.subTest(profile=profile, variant='matching'):
                result = self.receipt(runner, actual, profile)
                self.assertEqual(actual, result['honua']['environment'])
            for key in options:
                for variant in ('missing', 'wrong', 'duplicate'):
                    changed = [entry for entry in actual if not entry.startswith(key + '=')]
                    if variant == 'wrong':
                        changed.append(key + '=false')
                    if variant == 'duplicate':
                        changed.extend([key + '=true', key + '=false'])
                    with self.subTest(profile=profile, key=key, variant=variant), self.assertRaisesRegex(ValueError, 'planner.*drift'):
                        self.receipt(runner, changed, profile)
            extras = set().union(*(set(value) for value in runner.HONUA_PROFILES.values())) - options.keys()
            for key in extras:
                with self.subTest(profile=profile, extra=key), self.assertRaisesRegex(ValueError, 'planner.*drift'):
                    self.receipt(runner, actual + [key + '=true'], profile)

    def test_unknown_profile_fails_before_docker_inspection(self):
        runner = runner_module()
        with patch.object(runner, 'inspect') as inspect, patch.object(runner, 'docker_engine_identity') as engine:
            with self.assertRaisesRegex(ValueError, 'Unknown Honua profile'):
                runner.runtime_receipt({}, {}, honua_profile='unknown')
            inspect.assert_not_called()
            engine.assert_not_called()
