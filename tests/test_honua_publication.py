import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = (ROOT / 'adapters/honua/setup.sh').read_text().split('require_cmd curl\n', 1)[0]


class HonuaPublicationTests(unittest.TestCase):
    def run_adapter(self, command, responses=(), transport_failure=False):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for index, response in enumerate(responses):
                (directory / f'{index}.json').write_text(json.dumps(response))
            (directory / 'counter').write_text('0')
            script = FUNCTIONS + '\n' + f'fixture_dir={shlex.quote(temporary)}\n' + '''
api() {
    printf '%s\\n' "$2" >> "$fixture_dir/requests"
    local index
    index="$(cat "$fixture_dir/counter")"
    echo "$((index + 1))" > "$fixture_dir/counter"
    cat "$fixture_dir/$index.json"
}
sleep() { :; }
'''
            if transport_failure:
                script += 'api() { return 22; }\n'
            result = subprocess.run(['bash', '-c', script + command], capture_output=True, text=True, timeout=10)
            requests = directory / 'requests'
            return result, requests.read_text().splitlines() if requests.exists() else []

    def publish(self, response, **kwargs):
        return self.run_adapter(
            'resolve_published_layer_id ' + shlex.quote(json.dumps(response)) + ' connection-1', **kwargs)

    def test_immediate_publication_accepts_current_and_legacy_layer_ids(self):
        for field in ('storageLayerId', 'layerId'):
            with self.subTest(field=field):
                result, requests = self.publish({'data': {field: 42}})
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual('42', result.stdout.strip())
                self.assertEqual([], requests)

    def test_async_publication_waits_for_completed_layer_and_escapes_job_id(self):
        result, requests = self.publish(
            {'data': {'jobId': 'job/1', 'statusUrl': 'https://untrusted.invalid'}},
            responses=[{'data': {'status': 'Queued'}}, {'data': {'status': 'Processing'}},
                       {'data': {'status': 'Completed', 'storageLayerId': 43}}])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('43', result.stdout.strip())
        self.assertEqual(['/api/v1/admin/connections/connection-1/layers/jobs/job%2F1'] * 3, requests)

    def test_failed_cancelled_or_unknown_job_does_not_produce_a_layer(self):
        for status in ('Failed', 'Cancelled', 'Unexpected', ''):
            with self.subTest(status=status):
                result, _ = self.publish({'data': {'jobId': 'job-1'}}, responses=[{'data': {'status': status}}])
                self.assertNotEqual(0, result.returncode)
                self.assertEqual('', result.stdout)

    def test_completed_job_requires_a_storage_layer_id(self):
        result, _ = self.publish({'data': {'jobId': 'job-1'}}, responses=[{'data': {'status': 'Completed'}}])
        self.assertNotEqual(0, result.returncode)
        self.assertIn('no storage layer ID', result.stderr)

    def test_missing_job_and_layer_is_rejected_without_polling(self):
        result, requests = self.publish({'data': {}})
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], requests)

    def test_poll_transport_failure_is_preserved(self):
        result, _ = self.publish({'data': {'jobId': 'job-1'}}, transport_failure=True)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('', result.stdout)

    def test_inventory_accepts_paged_and_legacy_array_envelopes(self):
        for field in ('storageLayerId', 'layerId'):
            rows = [{'layerName': 'other', field: 1}, {'layerName': 'bench_points', field: 44}]
            for data in (rows, {'items': rows, 'totalCount': 2}):
                with self.subTest(field=field, data=data):
                    result, _ = self.run_adapter('find_layer_id connection-1', responses=[{'data': data}])
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual('44', result.stdout.strip())
