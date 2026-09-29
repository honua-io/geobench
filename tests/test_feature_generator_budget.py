import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from feature_contract import BUDGET, fingerprint
from feature_evidence import report
from feature_runtime import Observer


def runner_module():
    spec = importlib.util.spec_from_file_location('generator_runner', ROOT / 'scripts/run-feature-campaign.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compose_input():
    return json.dumps({'services': {name: {'environment': {}, 'volumes': []}
                                   for name in ('honua', 'geoserver', 'postgis-honua', 'postgis-geoserver', 'k6')}})


class GeneratorBudgetTests(unittest.TestCase):
    def test_report_discloses_generator_budget_even_when_evidence_fails(self):
        manifest = {'mode': 'diagnostic', 'profile': 'bounded-generator-8cpu', 'repetitions': 3,
                    'servers': ['honua', 'geoserver'], 'scenarios': ['equality'], 'binding': 'x',
                    'budget': BUDGET, 'generator_budget': {'cpus': 8, 'memory_bytes': 4 * 1024**3}}
        with tempfile.TemporaryDirectory() as temp:
            result = report(temp, manifest, [])
            self.assertFalse(result['valid'])
            self.assertFalse(result['publishable'])
            self.assertEqual(manifest['generator_budget'], result['generator_budget'])
            self.assertEqual(BUDGET, result['server_database_budget'])
            self.assertIn('Generator budget (same for both products): {"cpus": 8', (Path(temp) / 'report.md').read_text())

    def test_only_generator_cpu_changes_and_both_products_get_same_budget(self):
        runner = runner_module()
        with patch.object(runner, 'command', return_value=compose_input()):
            for server in ('honua', 'geoserver'):
                baseline = runner.make_compose('owned', server, {})
                enlarged = runner.make_compose('owned', server, {}, generator_cpus=8)
                self.assertNotEqual(fingerprint(baseline), fingerprint(enlarged))
                limits = enlarged['services']['k6']['deploy']['resources']['limits']
                self.assertEqual({'cpus': '8', 'memory': str(4 * 1024**3)}, limits)
                limits['cpus'] = '4'
                self.assertEqual(baseline, enlarged)
                self.assertEqual(6, BUDGET['source_connections'])

    def test_invalid_cpu_budget_fails_before_docker(self):
        runner = runner_module()
        with patch.object(runner, 'command') as command:
            for cpus in (0, -1, 0.5, 4.5, True, '8', float('nan'), float('inf')):
                with self.subTest(cpus=cpus), self.assertRaises(ValueError):
                    runner.make_compose('owned', 'honua', {}, generator_cpus=cpus)
                with self.subTest(runtime_cpus=cpus), self.assertRaises(ValueError):
                    runner.runtime_receipt({}, {}, generator_cpus=cpus)
            command.assert_not_called()

    def test_effective_generator_server_and_database_drift_fail_closed(self):
        runner = runner_module()
        roles = ('geoserver', 'postgis-geoserver', 'k6')
        images = {role: {'id': role} for role in ('geoserver', 'postgis', 'k6')}
        infos = {role: {'Image': 'postgis' if role.startswith('postgis-') else role,
                        'HostConfig': {'NanoCpus': (8 if role == 'k6' else 4) * 10**9,
                                       'Memory': 4 * 1024**3}, 'Config': {'Env': []}}
                 for role in roles}
        with patch.object(runner, 'inspect', side_effect=lambda identity: infos[identity]), \
                patch.object(runner, 'docker_engine_identity', return_value={}):
            receipt = runner.runtime_receipt(dict(zip(roles, roles)), images, generator_cpus=8)
            self.assertEqual(8, receipt['k6']['cpus'])
            for role in roles:
                for key, value in (('NanoCpus', 6 * 10**9), ('Memory', 8 * 1024**3)):
                    original = infos[role]['HostConfig'][key]
                    infos[role]['HostConfig'][key] = value
                    with self.subTest(role=role, key=key), self.assertRaisesRegex(ValueError, 'resource drift'):
                        runner.runtime_receipt(dict(zip(roles, roles)), images, generator_cpus=8)
                    infos[role]['HostConfig'][key] = original

    def test_prepared_manifest_records_budget_and_rejects_changed_resume(self):
        runner = runner_module()
        cwd = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                for folder in ('src/tests', 'adapters', 'scripts', 'config', 'data/small'):
                    (root / folder).mkdir(parents=True)
                (root / 'config/feature-corpus-v1.json').write_bytes((ROOT / 'config/feature-corpus-v1.json').read_bytes())
                (root / 'data/small/init.sql').write_text('-- fixture')
                (root / 'docker-compose.yml').write_text('{}')
                output = root / 'results/prepared'
                argv = ['campaign', '--prepare-only', '--generator-cpus', '8', '--output', str(output)]
                with patch.object(runner, 'ROOT', root), patch.object(runner, 'resolve_images', return_value={}), \
                        patch.object(runner, 'host_identity', return_value={}), \
                        patch.object(runner, 'source_fingerprint', return_value='source'), \
                        patch.object(runner, 'command', side_effect=lambda *a, **kw: compose_input() if a[0] == 'docker' else 'commit'), \
                        patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()):
                    self.assertEqual(0, runner.main())
                    original = (output / 'campaign.json').read_bytes()
                    manifest = json.loads(original)
                    self.assertEqual({'cpus': 8, 'memory_bytes': 4 * 1024**3}, manifest['generator_budget'])
                    self.assertEqual(BUDGET, manifest['budget'])
                    self.assertIn('generator-8cpu', manifest['profile'])
                    for server in ('honua', 'geoserver'):
                        self.assertEqual('8', manifest['effective_compose'][server]['services']['k6']['deploy']['resources']['limits']['cpus'])
                    argv.append('--resume')
                    self.assertEqual(0, runner.main())
                    argv[argv.index('8')] = '4'
                    with self.assertRaisesRegex(ValueError, 'Resume refused'):
                        runner.main()
                    self.assertEqual(original, (output / 'campaign.json').read_bytes())
        finally:
            os.chdir(cwd)

    def test_cli_rejects_invalid_values_before_image_inspection(self):
        runner = runner_module()
        with patch.object(runner, 'resolve_images') as images, redirect_stderr(io.StringIO()):
            for value in ('0', '-1', '4.5', 'nan', 'inf'):
                with patch.object(sys, 'argv', ['campaign', '--generator-cpus', value]), self.assertRaises(SystemExit):
                    runner.main()
            images.assert_not_called()

    def test_observer_uses_each_containers_actual_cpu_limit(self):
        infos = {role: {'Name': '/' + role, 'HostConfig': {'NanoCpus': cpus * 10**9}}
                 for role, cpus in (('server', 4), ('db', 4), ('k6', 8))}
        with tempfile.TemporaryDirectory() as temp, patch('feature_runtime.inspect', side_effect=lambda identity: infos[identity]):
            observer = Observer(temp, list(infos), 'db')
            observer.container_peaks = {role: {'cpu_percent': 400, 'memory_percent': 1} for role in infos}
            summary = observer.summary()
            self.assertEqual({'server': 4, 'db': 4, 'k6': 8}, summary['container_cpu_limits'])
            self.assertEqual(2, len(summary['signals']))
            self.assertFalse(any(s.startswith('k6:') for s in summary['signals']))
            observer.container_peaks['k6']['cpu_percent'] = 720
            self.assertTrue(any(s.startswith('k6:') for s in observer.summary()['signals']))
            invalid = copy.deepcopy(infos)
            invalid['k6']['HostConfig']['NanoCpus'] = 0
            with patch('feature_runtime.inspect', side_effect=lambda identity: invalid[identity]), self.assertRaises(ValueError):
                Observer(temp, list(infos), 'db')
