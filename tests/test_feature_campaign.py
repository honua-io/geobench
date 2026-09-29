import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from feature_contract import fingerprint, immutable_image, oracle, request_url, validate_plugin_jars
from feature_evidence import calibration_failures, calibration_sample_failures, distribution, report, summarize
from feature_runtime import LABEL, cleanup, owned_ids


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FeatureCampaignTests(unittest.TestCase):
    def test_validator_uses_full_oracle_including_empty_wrong_order_and_types(self):
        subprocess.run(['node', '--input-type=module', '-e', '''
import fs from 'node:fs';
import assert from 'node:assert/strict';
const source = fs.readFileSync('src/tests/feature-validation.js');
const {validateFeatureResponse: validate} = await import('data:text/javascript;base64,' + source.toString('base64'));
const geometry = {type:'Point',coordinates:[1,2]};
const expected = {features:[{id:1, category:'park', priority:1, geometry}, {id:2, category:'park', priority:2, geometry}], matched:2};
const payload = {type:'FeatureCollection',features:expected.features.map(r => ({type:'Feature',id:r.id,properties:{category:r.category,priority:r.priority},geometry})),numberMatched:2,numberReturned:2};
const check = p => validate(p, expected, 'ogc', ['category','priority']);
assert.equal(check(payload), null);
assert.ok(check({...payload, numberMatched:undefined}));
for (const p of [null, 'malformed JSON', {}, [], {features:[]}, {type:'FeatureCollection',features:[]}, {...payload,features:payload.features.slice(0,1)}]) assert.ok(check(p));
for (const change of [p => p.features.reverse(), p => p.features[1] = p.features[0], p => p.features[0].properties.category='road', p => p.features[0].properties.priority='1', p => p.features[0].geometry.coordinates=[2,1], p => p.numberMatched=1]) {
 const p=structuredClone(payload); change(p); assert.ok(check(p));
}
assert.equal(validate({type:'FeatureCollection',features:[],numberMatched:0}, {features:[],matched:0}, 'ogc', []), null);
assert.ok(validate({features:[]}, {features:[],matched:0}, 'ogc', []));
assert.ok(validate({error:{message:'unsupported'},features:[]}, {features:[],matched:0}, 'gsr', []));
'''], cwd=ROOT, check=True)

    def test_k6_completion_boundary_uses_executor_progress_not_wall_clock(self):
        subprocess.run(['node', '--input-type=module', '-e', r'''
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
let source = fs.readFileSync('src/tests/feature-campaign.js', 'utf8')
 .replace(/^import .*;$/gm, '').replace('export default function ()', 'function iterate()')
 .replaceAll('export function ', 'function ').replaceAll('export const ', 'const ');
const records = [];
const config = {scenario:'equality', requests:[{id:'equality',url:'http://test',expected:{features:[],matched:0}}],fields:[], protocol:'ogc', duration:1, phase:'measurement',vus:1};
const exec = {scenario:{progress:0.4,iterationInTest:0}};
let finish=0.5;
class Metric { constructor(name) {this.name=name;} add(value,tags) {records.push({name:this.name,value,tags});} }
const context = {exec, __ENV:{CAMPAIGN_INPUT:'input'}, open:()=>JSON.stringify(config),Counter:Metric,Trend:Metric,
 validateFeatureResponse:()=>null, console, Date:{now:()=>{throw Error('wall clock used');}},
 http:{get:()=>{exec.scenario.progress=finish;return {status:200,headers:{},json:()=>({type:'FeatureCollection',features:[]})};}}};
vm.runInNewContext(source+';this.iterate=iterate;', context);
context.iterate();
assert.ok(Math.abs(records.find(r=>r.name==='feature_latency').value-100)<1e-8);
assert.equal(records.find(r=>r.name==='feature_completed').tags.phase,'measurement');
records.length=0;exec.scenario.progress=0.9;finish=1;context.iterate();
assert.equal(records.find(r=>r.name==='feature_completed').tags.phase,'drain');
assert.equal(records.filter(r=>r.name==='feature_latency').length,0);
'''], cwd=ROOT, check=True)

    def test_oracle_orders_limits_counts_and_boundary(self):
        corpus = json.loads((ROOT / 'config/feature-corpus-v1.json').read_text())
        statements = []
        def sql(statement):
            statements.append(statement)
            return [1, 2] if statement.startswith('SELECT json_build_array') else {'features':[], 'matched':0}
        result = oracle(corpus, sql)
        self.assertEqual(len(corpus['requests']), len(result['requests']))
        self.assertIn('ORDER BY id', statements[0])
        self.assertIn('LIMIT 100 OFFSET 0', statements[0])
        self.assertIn('count(*)', statements[0])
        self.assertIn('ST_Intersects', statements[-1])
        self.assertEqual([1, 2, 1.000001, 2.000001], result['requests'][-1]['bbox'])

    def test_urls_do_not_substitute_protocols(self):
        for protocol, marker in [('ogc', '/ogc/'), ('gsr', '/FeatureServer/')]:
            url = request_url('geoserver', protocol, {'filter':"category='park'", 'offset':1000}, 'http://test')
            self.assertIn(marker, url)
            self.assertIn('1000', url)
        with self.assertRaises(ValueError):
            request_url('geoserver', 'wfs', {}, 'http://test')

    def test_measured_samples_exclude_warmup_late_invalid_and_overlapping_tags(self):
        records = []
        def sample(metric, value, phase='measurement', valid='true'):
            records.append({'type':'Point','metric':metric,'data':{'value':value,'tags':{
                'phase':phase,'valid':valid,'request':'equality','query_type':'equality','concurrency':'10'}}})
        for phase, value in [('warmup',900),('measurement',1),('measurement',10),('drain',1000)]:
            sample('feature_started', 1, phase)
            sample('feature_completed', 1, phase)
            sample('feature_latency', value, phase)
            sample('feature_invalid', 0, phase)
        # Marginal HTTP metrics are not counted a second time.
        sample('http_req_duration', 999)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'points.jsonl'
            path.write_text('\n'.join(map(json.dumps, records)))
            result = summarize(path, 2)
        self.assertEqual(1, result['throughput'])
        self.assertEqual(10, result['latency_ms']['p95'])
        self.assertEqual(1, result['counts']['drain'])
        self.assertEqual([], result['failures'])

    def test_cancellations_and_missing_points_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'points.jsonl'
            path.write_text(json.dumps({'type':'Point','metric':'feature_started','data':{'value':1,'tags':{}}}))
            result = summarize(path, 30)
            self.assertEqual(1, result['counts']['cancelled'])
            self.assertTrue(result['failures'])

    def test_never_average_overall_percentiles_or_sum_overlapping_tags(self):
        old = load('generate-report')
        self.assertIsNone(old.measured_overall_from_summary({
            'http_reqs{concurrency:10}':{'count':100,'rate':10},
            'http_reqs{concurrency:10,workload:equality}':{'count':100,'rate':10},
            'http_req_duration{concurrency:10}':{'med':2,'p(95)':10,'p(99)':50}}))
        self.assertEqual(100, distribution([1]*94 + [100]*6)['p95'])

    def test_fingerprints_detect_every_drift_dimension(self):
        original = {'workload':'a','image':'b','dataset':'c','configuration':{'pool':6},'harness':'d'}
        for key in original:
            changed = copy.deepcopy(original)
            changed[key] = 'changed'
            self.assertNotEqual(fingerprint(original), fingerprint(changed))
        self.assertEqual(fingerprint(original), fingerprint(dict(reversed(list(original.items())))))

    def test_resume_snapshot_detects_removed_or_changed_harness(self):
        runner = load('run-feature-campaign')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'harness').mkdir()
            file = root / 'harness/workload.js'
            file.write_text('original')
            manifest = {'snapshot_sha256': runner.tree_hashes(root / 'harness')}
            runner.verify_snapshot(root, manifest)
            file.write_text('drift')
            with self.assertRaises(ValueError):
                runner.verify_snapshot(root, manifest)
            file.unlink()
            with self.assertRaises(ValueError):
                runner.verify_snapshot(root, manifest)

    def test_count_tuning_is_scoped_to_honua_and_changes_configuration_fingerprint(self):
        runner = load('run-feature-campaign')
        original = {'services': {name: {'environment': {'keep': 'value'}} for name in
                    ('honua', 'geoserver', 'postgis-honua', 'postgis-geoserver', 'k6')}}
        with patch.object(runner, 'command', return_value=json.dumps(original)):
            baseline = runner.make_compose('owned', 'honua', {})
            tuned = runner.make_compose('owned', 'honua', {}, 'count-jit-off')
            geo = runner.make_compose('owned', 'geoserver', {})
            geo_tuned = runner.make_compose('owned', 'geoserver', {}, 'count-jit-off')
        key = 'Database__DisableJitForSourceSpatialCounts'
        self.assertNotIn(key, baseline['services']['honua']['environment'])
        self.assertEqual('true', tuned['services']['honua']['environment'][key])
        self.assertNotEqual(fingerprint(baseline), fingerprint(tuned))
        del tuned['services']['honua']['environment'][key]
        self.assertEqual(baseline, tuned)
        self.assertEqual(geo, geo_tuned)
        with patch.object(runner, 'command') as command:
            with self.assertRaises(ValueError):
                runner.make_compose('owned', 'honua', {}, 'unknown')
            command.assert_not_called()

    def test_cleanup_discovers_stopped_owned_containers(self):
        with patch('feature_runtime.command', return_value='owned') as mocked:
            self.assertEqual(['owned'], owned_ids('mine'))
            self.assertIn('-a', mocked.call_args.args)
            self.assertIn(f'label={LABEL}=mine', mocked.call_args.args)

    def test_images_and_incompatible_plugins(self):
        self.assertTrue(immutable_image('repo@sha256:' + 'a'*64))
        self.assertTrue(immutable_image('sha256:' + 'a'*64))
        self.assertFalse(immutable_image('repo:latest'))
        jars = ['a /lib/gs-main-3.0.1.jar','b /lib/gs-ogcapi-features-3.0.1.jar']
        self.assertTrue(validate_plugin_jars(jars))
        for invalid in [jars[:1], jars+['c /lib/gs-gsr-3.0-SNAPSHOT.jar']]:
            with self.assertRaises(ValueError):
                validate_plugin_jars(invalid, gsr=True)

    def test_cleanup_owned_exact_ids_only(self):
        calls = []
        def docker(*args):
            calls.append(args)
            return json.dumps([{'Config':{'Labels':{LABEL:'mine'}}}]) if 'inspect' in args else ''
        with patch('feature_runtime.command', side_effect=docker):
            cleanup('mine', {'container':['exact-id']})
        self.assertEqual(('docker','container','rm','-f','exact-id'), calls[-1])
        with patch('feature_runtime.command', return_value=json.dumps([{'Config':{'Labels':{LABEL:'someone-else'}}}])) as mocked:
            with self.assertRaises(ValueError):
                cleanup('mine', {'container':['other-id']})
            self.assertEqual(1, mocked.call_count)

    def test_missing_scenarios_interrupted_attempts_and_reruns_remain_invalid(self):
        manifest = {'mode':'comparison','profile':'stable-ogc-source-bounded','repetitions':1,
                    'servers':['honua','geoserver'],'scenarios':['equality'],'binding':'x'}
        attempts = [{'id':'old','server':'honua','repetition':1,'status':'interrupted','rows':{}},
                    {'id':'retry','server':'honua','repetition':1,'status':'passed','rows':{}}]
        with tempfile.TemporaryDirectory() as temp:
            result = report(temp, manifest, attempts)
        self.assertFalse(result['valid'])
        self.assertFalse(result['publishable'])
        self.assertTrue(any('old' in failure for failure in result['failures']))
        self.assertTrue(any('missing scenarios' in failure for failure in result['failures']))

    def test_calibration_requires_both_observer_and_isolated_generator(self):
        self.assertTrue(calibration_failures(None, 'x'))
        evidence = {'binding':'x','local_generator_identity':'local','isolated_generator_identity':'remote'}
        for key in ('observer_off','observer_on','isolated_generator'):
            evidence[key] = [{'throughput':100,'p95':10,'sha256':key+str(i)} for i in range(3)]
        with patch('feature_evidence.calibration_sample_failures', return_value=[]):
            self.assertEqual([], calibration_failures(evidence, 'x'))
            evidence['observer_on'] = [{'throughput':95,'p95':10,'sha256':'observer_on'+str(i)} for i in range(3)]
            self.assertEqual([], calibration_failures(evidence, 'x'))
            evidence['observer_on'] = [{'throughput':94,'p95':10,'sha256':'observer_on'+str(i)} for i in range(3)]
            self.assertTrue(calibration_failures(evidence, 'x'))
        self.assertTrue(calibration_sample_failures({'throughput':100,'p95':10}))
        self.assertTrue(calibration_failures(evidence, 'drifted'))

    def test_calibration_rejects_reused_treatments_and_clock_anomalies(self):
        evidence = {'binding':'x','local_generator_identity':'local','isolated_generator_identity':'remote'}
        for key in ('observer_off','observer_on','isolated_generator'):
            evidence[key] = [{'throughput':100,'p95':10,'sha256':key+str(i)} for i in range(3)]
        evidence['isolated_generator'][0]['sha256'] = evidence['observer_on'][0]['sha256']
        with patch('feature_evidence.calibration_sample_failures', return_value=[]):
            self.assertIn('calibration treatments reuse the same raw artifacts', calibration_failures(evidence, 'x'))
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / 'raw.jsonl'
            raw.write_text('raw')
            import hashlib
            sample = {'raw_points':str(raw),'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
                      'measurement_seconds':120, 'throughput':100,'p95':10}
            with patch('feature_evidence.summarize', return_value={'counts':{'clock_anomalies':1}}):
                self.assertEqual(['clock anomalies in calibration raw samples'], calibration_sample_failures(sample))

    def test_observer_calibration_alternates_and_drains_without_sampling_off_runs(self):
        module = load('run-observer-calibration')
        first = module.observer_order(42, 1)
        self.assertEqual(first[::-1], module.observer_order(42, 2))
        self.assertEqual(first, module.observer_order(42, 3))
        events = []
        class FakeObserver:
            def __init__(self, *args):
                pass
            def __enter__(self):
                events.append('observer-start')
                return self
            def __exit__(self, *args):
                events.append('observer-drained')
            def summary(self):
                return {'samples':2,'failures':[], 'max_database_pressure':{
                    'source_sessions':6, 'source_active':3, 'parallel_workers':0}}
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / 'raw'
            raw.write_text('raw')
            def run(ids, path, config, name):
                events.append(name)
                return raw, []
            summary = {'failures':[], 'throughput':100, 'latency_ms':{'p95':10}, 'counts':{}, 'requests':{'equality':100}}
            attempt = {'id':'test','repetition':1}
            with patch.object(module, 'Observer', FakeObserver), patch.object(module, 'summarize', return_value=summary):
                result = module.collect_observer_samples(SimpleNamespace(run_k6=run),
                    {'seed':42,'warmup':30,'measurement':30}, ['equality'], Path(temp), {'k6':'k6'}, 'db', {}, attempt, Mock())
        self.assertEqual(['equality-observer_off-warmup', 'equality-observer_off-measurement',
                          'observer-start', 'equality-observer_on-warmup',
                          'equality-observer_on-measurement', 'observer-drained'], events)
        self.assertEqual(2, result['samples'])
        self.assertEqual({'observer_on','observer_off'}, set(attempt['calibration_rows']['equality']))

    def test_observer_report_retains_interruption_and_cannot_approve_publication(self):
        module = load('run-observer-calibration')
        manifest = {'servers':['honua'],'binding':'x','host_identity':{'node':'wsl'},
                    'mode':'diagnostic','warmup':30,'measurement':30}
        attempts = [{'id':'failed', 'server':'honua', 'repetition':1, 'status':'interrupted'}]
        with tempfile.TemporaryDirectory() as temp:
            result = module.local_report(Path(temp), manifest, attempts, ['equality'])
        self.assertFalse(result['valid'])
        self.assertFalse(result['publishable'])
        self.assertFalse(result['within_five_percent'])
        self.assertTrue(any('interrupted' in reason for reason in result['failures']))

    def test_interrupted_calibration_cleanup_preserves_failed_attempts_and_ownership(self):
        module = load('run-observer-calibration')
        runner = load('run-feature-campaign')
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            ledger = directory / 'observer-test-attempts.json'
            ledger.write_text(json.dumps([{'id':'observer-test-pair1-honua','owner':'mine-observer-test-pair1-honua',
                                          'status':'running'}]))
            with patch.object(runner, 'record_resources', return_value={'container':['stopped-owned-id']}) as discovery, \
                 patch.object(runner, 'cleanup') as cleanup_mock:
                module.recover_interrupted(runner, directory, {'owner':'mine'})
            discovery.assert_called_once_with('mine-observer-test-pair1-honua')
            cleanup_mock.assert_called_once_with('mine-observer-test-pair1-honua', {'container':['stopped-owned-id']})
            attempt = json.loads(ledger.read_text())[0]
            self.assertEqual('interrupted', attempt['status'])
            self.assertTrue(attempt['cleaned'])
            attempt.update({'owner':'someone-else', 'cleaned':False})
            ledger.write_text(json.dumps([attempt]))
            with patch.object(runner, 'cleanup') as cleanup_mock:
                with self.assertRaises(ValueError):
                    module.recover_interrupted(runner, directory, {'owner':'mine'})
            cleanup_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
