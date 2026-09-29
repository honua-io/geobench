import json
import io
import importlib.util
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree as ET
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from feature_contract import oracle, request_url
from feature_geoserver import SORTING_CONFORMANCE, enable_sorting_settings, geoserver_sorting, sorting_receipt


def runner_module():
    spec = importlib.util.spec_from_file_location('sorting_campaign_runner', ROOT / 'scripts/run-feature-campaign.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GeoServerSortingTests(unittest.TestCase):
    def test_enable_preserves_existing_service_and_conformance_settings(self):
        original = b'''<wfs><title>Existing</title><metadata>
          <entry key="other">preserved</entry>
          <entry key="ogcapiFeatures"><ogcapiFeatures>
            <featuresFilter>true</featuresFilter><sortBy>false</sortBy>
          </ogcapiFeatures></entry></metadata></wfs>'''
        updated = enable_sorting_settings(original)
        root = ET.fromstring(updated)
        self.assertEqual('Existing', root.findtext('title'))
        self.assertEqual('preserved', root.findtext("metadata/entry[@key='other']"))
        self.assertEqual('true', root.findtext("metadata/entry[@key='ogcapiFeatures']/ogcapiFeatures/featuresFilter"))
        self.assertEqual('true', root.findtext("metadata/entry[@key='ogcapiFeatures']/ogcapiFeatures/sortBy"))
        self.assertEqual(updated, enable_sorting_settings(updated))

    def test_enable_adds_typed_metadata_for_default_configuration(self):
        updated = enable_sorting_settings(b'<wfs><enabled>true</enabled></wfs>')
        receipt = sorting_receipt(updated, {'conformsTo': [SORTING_CONFORMANCE]})
        self.assertTrue(receipt['sort_by'])
        self.assertEqual(SORTING_CONFORMANCE, receipt['sorting_conformance'])

    def test_missing_or_disabled_sorting_fails_closed(self):
        for xml in [b'<wfs/>', b'<wfs><metadata><entry key="ogcapiFeatures"><ogcapiFeatures><sortBy>false</sortBy></ogcapiFeatures></entry></metadata></wfs>']:
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                sorting_receipt(xml, {'conformsTo': [SORTING_CONFORMANCE]})

    def test_advertisement_is_required_in_addition_to_saved_configuration(self):
        xml = enable_sorting_settings(b'<wfs/>')
        for payload in [{}, {'conformsTo': []}, {'conformsTo': SORTING_CONFORMANCE}, None]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                sorting_receipt(xml, payload)

    def test_malformed_or_ambiguous_settings_fail_closed(self):
        for xml in [b'not XML', b'<html/>', b'<wfs><metadata><entry key="ogcapiFeatures"/><entry key="ogcapiFeatures"/></metadata></wfs>']:
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                enable_sorting_settings(xml)

    def test_reverse_order_oracle_orders_page_and_aggregate(self):
        corpus = json.loads((ROOT / 'config/feature-corpus-v1.json').read_text())
        corpus['requests'] = [{'id': 'ordering-desc', 'order': 'desc'}]
        statements = []
        def sql(statement):
            statements.append(statement)
            return {'features': [], 'matched': 100000}
        oracle(corpus, sql)
        self.assertEqual(2, statements[0].count('ORDER BY id DESC'))
        self.assertIn('LIMIT 100 OFFSET 0', statements[0])

    def test_reverse_order_urls_request_actual_descending_sort(self):
        for server in ['honua', 'geoserver']:
            for protocol, parameter, expected in [('ogc', 'sortby', '-id'), ('gsr', 'orderByFields', 'id DESC')]:
                url = request_url(server, protocol, {'order': 'desc'}, 'http://test')
                self.assertEqual([expected], parse_qs(urlsplit(url).query)[parameter])

    def test_unknown_order_cannot_be_interpolated_into_oracle_sql(self):
        corpus = {'requests': [{'id': 'bad', 'order': 'DESC; SELECT 1'}], 'fields': [], 'limit': 100}
        with self.assertRaises(ValueError):
            oracle(corpus, lambda statement: self.fail('Invalid order reached the database'))
        with self.assertRaises(ValueError):
            request_url('honua', 'ogc', corpus['requests'][0], 'http://test')

    def test_fresh_configuration_is_read_back_and_anonymously_advertised(self):
        enabled = enable_sorting_settings(b'<wfs/>')
        bodies = [b'<wfs/>', b'', enabled, json.dumps({'conformsTo': [SORTING_CONFORMANCE]}).encode()]
        with patch('feature_geoserver.urlopen', side_effect=[io.BytesIO(body) for body in bodies]) as transport:
            receipt = geoserver_sorting('http://owned', 'test-credential', configure=True)
        requests = [call.args[0] for call in transport.call_args_list]
        self.assertEqual(['GET', 'PUT', 'GET', 'GET'], [r.get_method() for r in requests])
        self.assertTrue(receipt['sort_by'])
        self.assertEqual(enabled, requests[1].data)
        self.assertFalse(requests[-1].has_header('Authorization'))

    def test_reused_fixture_with_disabled_sorting_is_rejected_without_mutation(self):
        bodies = [b'<wfs/>', json.dumps({'conformsTo': [SORTING_CONFORMANCE]}).encode()]
        with patch('feature_geoserver.urlopen', side_effect=[io.BytesIO(body) for body in bodies]) as transport:
            with self.assertRaises(ValueError):
                geoserver_sorting('http://owned', 'test-credential')
        self.assertTrue(all(call.args[0].get_method() == 'GET' for call in transport.call_args_list))

    def test_hidden_primary_key_is_rejected_by_effective_store_check(self):
        runner = runner_module()
        for exposed in [None, 'false', 'true']:
            values = {'max connections': '6', 'min connections': '3'}
            if exposed is not None:
                values['Expose primary keys'] = exposed
            body = {'dataStore': {'connectionParameters': {'entry': [{'@key': k, '$': v} for k, v in values.items()]}}}
            with self.subTest(exposed=exposed), patch.object(runner, 'urlopen', return_value=io.BytesIO(json.dumps(body).encode())):
                if exposed == 'true':
                    self.assertEqual(values, runner.geoserver_store('http://owned', 'test-credential'))
                else:
                    with self.assertRaises(ValueError):
                        runner.geoserver_store('http://owned', 'test-credential')

    def test_missing_or_duplicated_probe_receipt_cannot_pass(self):
        runner = runner_module()
        config = {'requests': [{'id': 'normal'}], 'preflight_requests': [{'id': 'ordering-desc'}],
                  'duration': 1, 'protocol': 'ogc'}
        for names in [['normal'], ['normal', 'normal'], ['normal', 'wrong'], ['normal', 'ordering-desc']]:
            checks = [{'id': name, 'failure': None} for name in names]
            def fake_run(*args, **kwargs):
                kwargs['stdout'].write(json.dumps({'msg': 'PREFLIGHT ' + json.dumps(checks)}) + '\n')
                kwargs['stdout'].flush()
                return SimpleNamespace(returncode=0)
            with self.subTest(names=names), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = root / 'results/campaign/attempt'
                directory.mkdir(parents=True)
                with patch.object(runner, 'ROOT', root), patch.object(runner.subprocess, 'run', side_effect=fake_run):
                    if names == ['normal', 'ordering-desc']:
                        self.assertEqual(checks, runner.run_k6({'k6': 'owned'}, directory, config, 'preflight')[1])
                    else:
                        with self.assertRaises(ValueError):
                            runner.run_k6({'k6': 'owned'}, directory, config, 'preflight')

    def test_ignored_reverse_order_fails_preflight_and_probe_is_not_measured(self):
        subprocess.run(['node', '--input-type=module', '-e', r'''
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const validator = fs.readFileSync('src/tests/feature-validation.js');
const {validateFeatureResponse} = await import('data:text/javascript;base64,' + validator.toString('base64'));
let source = fs.readFileSync('src/tests/feature-campaign.js','utf8')
 .replace(/^import .*;$/gm,'').replace('export default function ()','function iterate()')
 .replaceAll('export function ','function ').replaceAll('export const ','const ');
const geometry = {type:'Point',coordinates:[1,2]};
const rows = [{id:1,geometry},{id:2,geometry}];
const config = {requests:[{id:'normal',url:'http://normal',expected:{features:rows,matched:2}}],
 preflight_requests:[{id:'ordering-desc',url:'http://reverse',expected:{features:[...rows].reverse(),matched:2}}],
 fields:[],protocol:'ogc',scenario:'normal',duration:1,phase:'measurement',vus:1};
const called = []; let ignoreSort = true;
class Metric {add() {}}
const context = {__ENV:{CAMPAIGN_INPUT:'input'},open:()=>JSON.stringify(config),Counter:Metric,Trend:Metric,
 exec:{scenario:{progress:0.5,iterationInTest:0}},console:{log:()=>{},error:()=>{}},validateFeatureResponse,
 http:{get:url=>{called.push(url);const selected=url==='http://reverse'&&!ignoreSort?[...rows].reverse():rows;
 return {status:200,headers:{},json:()=>({type:'FeatureCollection',numberMatched:2,
 features:selected.map(r=>({type:'Feature',id:r.id,properties:{},geometry:r.geometry}))})};}}};
vm.runInNewContext(source+';this.iterate=iterate;',context);
assert.throws(()=>context.setup(),/Corpus validation failed/);
ignoreSort=false;called.length=0;context.setup();
assert.deepEqual(called,['http://normal','http://reverse']);
called.length=0;context.iterate();assert.deepEqual(called,['http://normal']);
'''], cwd=ROOT, check=True)
