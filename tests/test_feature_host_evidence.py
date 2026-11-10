import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import feature_runtime
from feature_contract import fingerprint


def runner():
    spec = importlib.util.spec_from_file_location('campaign_host_test', ROOT / 'scripts/run-feature-campaign.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HostEvidenceTests(unittest.TestCase):
    def test_engine_identity_is_fingerprinted_without_proxy_credentials(self):
        module = runner()
        engine = {'ID':'engine-one', 'Name':'docker-desktop', 'OperatingSystem':'Docker Desktop',
                  'OSType':'linux', 'Architecture':'x86_64', 'KernelVersion':'engine-kernel',
                  'NCPU':22, 'MemTotal':25000000000, 'ServerVersion':'29.8.0',
                  'CgroupDriver':'cgroupfs', 'CgroupVersion':'2',
                  'HttpProxy':'https://user:secret@proxy.invalid'}
        with patch.object(module, 'command', return_value=json.dumps(engine)):
            first = module.host_identity()
        self.assertEqual('engine-one', first['docker_engine']['ID'])
        self.assertNotIn('secret', json.dumps(first))
        engine['ID'] = 'engine-two'
        with patch.object(module, 'command', return_value=json.dumps(engine)):
            second = module.host_identity()
        self.assertNotEqual(fingerprint(first), fingerprint(second))
        for key, value in [('ID', ''), ('NCPU', 0), ('MemTotal', -1)]:
            with patch.object(module, 'command', return_value=json.dumps({**engine, key:value})):
                with self.assertRaises(ValueError):
                    module.host_identity()

    def test_container_host_sample_comes_from_engine_kernel_and_rejects_missing_evidence(self):
        boot = '71835f64-dcb0-4b84-96c5-45ddcda109ed'
        raw = f'1.0 2.0 3.0 1/20 99\ncpu 1 2 3 4\ncpu0 1 2 3 4\nbtime 123\nMemTotal: 25000000 kB\nMemFree: 100000 kB\n{boot}\n'
        with patch.object(feature_runtime, 'command', return_value=raw) as command:
            sample = feature_runtime.engine_host_sample('exact-owned-database')
        self.assertEqual('docker-engine-kernel', sample['scope'])
        self.assertEqual(boot, sample['boot_id'])
        self.assertEqual([1.0, 2.0, 3.0], sample['load'])
        self.assertEqual('cpu 1 2 3 4', sample['cpu'])
        self.assertEqual('MemTotal: 25000000 kB\nMemFree: 100000 kB\n', sample['memory'])
        self.assertEqual(('docker', 'exec', 'exact-owned-database', 'cat'), command.call_args.args[:4])
        for invalid in ('', raw.replace(boot, 'missing'), raw.replace('MemTotal:', 'Unknown:'), raw.replace('1.0 2.0 3.0', 'nan 2.0 3.0')):
            with patch.object(feature_runtime, 'command', return_value=invalid):
                with self.assertRaises(ValueError):
                    feature_runtime.engine_host_sample('exact-owned-database')

    def test_observer_keeps_controller_separate_from_container_host(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(feature_runtime, 'inspect',
                side_effect=lambda identity: {'Name': '/' + identity, 'HostConfig': {'NanoCpus': 4 * 10**9}}):
            observer = feature_runtime.Observer(temp, ['server','db','k6'], 'db')
            def host_sample(container):
                self.assertEqual('db', container)
                observer.stop_event.set()
                return {'scope':'docker-engine-kernel','boot_id':'remote-boot','load':[9,8,7]}
            with patch.object(feature_runtime, 'engine_host_sample', side_effect=host_sample), \
                 patch.object(feature_runtime, 'sql', return_value={'source_sessions':1,'source_active':1,'parallel_workers':0}), \
                 patch.object(feature_runtime, 'command', return_value='{"Name":"server","CPUPerc":"10%","MemPerc":"5%"}'):
                observer.run()
            row = json.loads((Path(temp) / 'telemetry.jsonl').read_text())
            self.assertEqual('remote-boot', row['host']['boot_id'])
            self.assertEqual('controller-kernel', row['controller']['scope'])
            self.assertEqual(1, observer.summary()['samples'])
            self.assertEqual([], observer.summary()['failures'])


if __name__ == '__main__':
    unittest.main()
