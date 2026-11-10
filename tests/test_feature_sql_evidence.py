import sys
import json
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from feature_sql_evidence import validate_source_trace
from feature_evidence import report


def execution(sql, phase='execute <unnamed>'):
    return f'2026-09-28 12:00:00.000 UTC [42] LOG:  duration: 1.0 ms  {phase}: {sql}\n'


COUNT = execution('SELECT count(*) FROM "public"."bench_points"')
FEATURES = execution('SELECT ST_AsBinary(geom) FROM (SELECT geom FROM "public"."bench_points" LIMIT 100) page')


class SourceEvidenceTests(unittest.TestCase):
    def test_source_count_cannot_hide_materialized_feature_reads(self):
        for table in ('honua.features', '"honua"."features"', 'public.cached_points', '"other"."bench_points"'):
            with self.subTest(table=table), self.assertRaises(ValueError):
                validate_source_trace(COUNT + execution(f'SELECT ST_AsBinary(geometry) FROM {table}'))

    def test_requires_executed_count_and_feature_reads(self):
        for trace in (COUNT, FEATURES, execution('SELECT ST_AsBinary(geom) FROM public.bench_points', 'parse <unnamed>') + COUNT):
            with self.assertRaises(ValueError):
                validate_source_trace(trace)

    def test_literal_comments_and_detail_text_do_not_prove_source_reads(self):
        for sql in ("SELECT ST_AsBinary(geom), 'FROM public.bench_points' FROM other.points",
                    'SELECT ST_AsBinary(geom) FROM other.points /* FROM public.bench_points */',
                    'SELECT ST_AsBinary(geom), $$FROM public.bench_points$$ FROM other.points'):
            with self.assertRaises(ValueError):
                validate_source_trace(COUNT + execution(sql))

    def test_records_source_relations_for_nested_and_geoserver_projections(self):
        geo = execution('SELECT id,encode(ST_AsEWKB(geom), \'base64\') AS geom\n\tFROM "public"."bench_points" LIMIT 100', 'execute <unnamed>/C_23')
        result = validate_source_trace(COUNT + FEATURES + geo)
        self.assertEqual(2, result['feature_queries'])
        self.assertEqual(1, result['source_count_queries'])
        self.assertEqual(['public.bench_points'], result['feature_relations'])

    def test_rejects_materialized_joins_and_unqualified_source(self):
        for sql in ('SELECT ST_AsBinary(p.geom) FROM public.bench_points p JOIN honua.features f ON f.id=p.id',
                    'SELECT ST_AsBinary(p.geom) FROM public.bench_points p, honua.features f',
                    'SELECT ST_AsBinary(p.geom) FROM public.bench_points p, other.cached_points f',
                    'SELECT ST_AsBinary(geom) FROM bench_points'):
            with self.assertRaises(ValueError):
                validate_source_trace(COUNT + execution(sql))

    def test_quoted_columns_and_literals_are_not_from_clauses(self):
        sql = '''SELECT "FROM", ST_AsBinary(geom), 'FROM honua.features', $tag$JOIN other.points$tag$
\tFROM "public"."bench_points" WHERE label = 'quote'' FROM honua.features' '''
        self.assertEqual(1, validate_source_trace(COUNT + execution(sql))['feature_queries'])

    def test_report_revalidates_raw_sql_instead_of_trusting_a_passed_attempt(self):
        manifest = {'mode':'diagnostic','profile':'source','repetitions':1,
                    'servers':['honua'],'scenarios':[],'binding':'test'}
        attempt = {'id':'pair1-honua','server':'honua','repetition':1,'status':'passed','rows':{}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / attempt['id']
            path.mkdir()
            (path / 'source-query.json').write_text(json.dumps(validate_source_trace(COUNT + FEATURES, 'baseline')))
            (path / 'source-query.log').write_text(COUNT + execution('SELECT ST_AsBinary(geometry) FROM honua.features'))
            result = report(temp, manifest, [attempt])
            self.assertTrue(any('invalid executed source-query evidence' in value for value in result['failures']))
            (path / 'source-query.log').write_text(COUNT + FEATURES + FEATURES)
            result = report(temp, manifest, [attempt])
            self.assertTrue(any('source-query evidence mismatch' in value for value in result['failures']))


if __name__ == '__main__':
    unittest.main()
