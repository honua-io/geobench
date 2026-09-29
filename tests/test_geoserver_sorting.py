import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from feature_contract import oracle, request_url
from feature_geoserver import SORTING_CONFORMANCE, enable_sorting_settings, sorting_receipt


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
