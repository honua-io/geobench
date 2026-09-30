import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from feature_contract import HONUA_PROFILES
from feature_evidence import report
from feature_sql_evidence import validate_honua_planner_profile, validate_source_trace


def execution(sql, pid=42, phase='execute <unnamed>'):
    return f'2026-09-29 12:00:00.000 UTC [{pid}] LOG: duration: 1.0 ms {phase}: {sql}\n'


COUNT_SETTING = "SELECT pg_catalog.set_config('jit', 'off', true)"
READ_SETTING = "SELECT set_config('max_parallel_workers_per_gather', '0', true)"
WHERE = ' FROM "public"."bench_points" WHERE ST_Intersects(geom, ST_MakeEnvelope($1,$2,$3,$4,4326))'
COUNT = 'SELECT ALL COUNT(*)' + WHERE
READ = 'SELECT ALL ST_AsBinary(geom)' + WHERE + ' ORDER BY id LIMIT 100'
COUNT_BATCH = execution(COUNT_SETTING) + execution(COUNT)
READ_BATCH = execution(READ_SETTING) + execution(READ)
SERIAL_COUNT = COUNT.replace('SELECT ALL', 'SELECT ALL /* honua:serial-source-count */')
SERIAL_COUNT_BATCH = execution(READ_SETTING) + execution(SERIAL_COUNT)
COMBINED_SETTING = COUNT_SETTING + ", pg_catalog.set_config('max_parallel_workers_per_gather', '0', true)"
COMBINED_COUNT = COUNT.replace('SELECT ALL', 'SELECT ALL /* honua:serial-jit-off-source-count */')
COMBINED_COUNT_BATCH = execution(COMBINED_SETTING) + execution(COMBINED_COUNT)


class PlannerProfileTests(unittest.TestCase):
    def test_automatic_profile_requires_unset_flags_and_executed_serial_batches(self):
        self.assertEqual({}, HONUA_PROFILES['automatic-bounded'])
        result = validate_source_trace(READ_BATCH + SERIAL_COUNT_BATCH, 'automatic-bounded')['planner_profile']
        self.assertEqual((1, 1), (result['scoped_count_queries'], result['scoped_feature_queries']))
        for trace in (execution(READ) + execution(COUNT), READ_BATCH + execution(COUNT),
                      execution(READ) + SERIAL_COUNT_BATCH, READ_BATCH + COMBINED_COUNT_BATCH):
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                validate_honua_planner_profile(trace, 'automatic-bounded')

    def test_legacy_profiles_pin_independent_serial_options_against_default_drift(self):
        keys = {'Database__PreferSerialBoundedSpatialReads', 'Database__PreferSerialSourceSpatialCounts'}
        for profile, options in HONUA_PROFILES.items():
            if profile == 'automatic-bounded':
                continue
            with self.subTest(profile=profile):
                self.assertTrue(keys <= options.keys())
                self.assertTrue(all(options[key] in {'true', 'false'} for key in keys))
        self.assertEqual({key: 'false' for key in keys}, HONUA_PROFILES['baseline'])
        result = validate_source_trace(execution(READ) + execution(COUNT), 'baseline')['planner_profile']
        self.assertEqual((0, 0), (result['scoped_count_queries'], result['scoped_feature_queries']))
        with self.assertRaises(ValueError):
            validate_honua_planner_profile(READ_BATCH + SERIAL_COUNT_BATCH, 'baseline')

    def test_separate_and_combined_profiles_require_their_executed_batch_shapes(self):
        for profile, trace, counts in [
            ('baseline', execution(COUNT) + execution(READ), (0, 0)),
            ('count-jit-off', COUNT_BATCH + execution(READ), (1, 0)),
            ('serial-reads', execution(COUNT) + READ_BATCH, (0, 1)),
            ('count-jit-off-serial-reads', COUNT_BATCH + READ_BATCH, (1, 1)),
            ('serial-counts', SERIAL_COUNT_BATCH + execution(READ), (1, 0)),
            ('count-jit-off-serial-counts', COMBINED_COUNT_BATCH + execution(READ), (1, 0)),
            ('serial-reads-counts', SERIAL_COUNT_BATCH + READ_BATCH, (1, 1)),
            ('count-jit-off-serial-reads-counts', COMBINED_COUNT_BATCH + READ_BATCH, (1, 1)),
        ]:
            with self.subTest(profile=profile):
                result = validate_source_trace(trace, profile)['planner_profile']
                self.assertEqual(counts, (result['scoped_count_queries'], result['scoped_feature_queries']))

    def test_ignored_options_and_missing_half_of_combined_profile_fail(self):
        for profile, trace in [
            ('count-jit-off', execution(COUNT) + execution(READ)),
            ('serial-reads', execution(COUNT) + execution(READ)),
            ('count-jit-off-serial-reads', COUNT_BATCH + execution(READ)),
            ('count-jit-off-serial-reads', execution(COUNT) + READ_BATCH),
            ('serial-reads-counts', SERIAL_COUNT_BATCH + execution(READ)),
            ('serial-reads-counts', execution(COUNT) + READ_BATCH),
            ('count-jit-off-serial-reads-counts', COMBINED_COUNT_BATCH + execution(READ)),
            ('count-jit-off-serial-reads-counts', SERIAL_COUNT_BATCH + READ_BATCH),
            ('count-jit-off-serial-reads-counts', COUNT_BATCH + READ_BATCH),
            ('count-jit-off-serial-reads-counts', COUNT_BATCH + SERIAL_COUNT_BATCH + READ_BATCH),
            ('serial-reads-counts', COMBINED_COUNT_BATCH + READ_BATCH),
            ('baseline', COUNT_BATCH + READ_BATCH),
            ('unknown', COUNT_BATCH),
        ]:
            with self.subTest(profile=profile, trace=trace), self.assertRaises(ValueError):
                validate_honua_planner_profile(trace, profile)

    def test_nonlocal_settings_and_wrong_query_targets_fail(self):
        for trace in [
            execution(COUNT_SETTING.replace('true', 'false')) + execution(COUNT),
            execution('SET LOCAL jit=off') + execution(COUNT),
            execution(COUNT_SETTING) + execution(READ),
            execution(COUNT_SETTING) + execution(COUNT.replace('SELECT ALL', 'SELECT')),
            execution(COUNT_SETTING) + execution(COUNT.replace('"public"."bench_points"', 'honua.features')),
            execution(COUNT_SETTING) + execution('SELECT ALL COUNT(*) FROM public.bench_points'),
            execution(COUNT_SETTING),
        ]:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                validate_honua_planner_profile(trace, 'count-jit-off')
        with self.assertRaises(ValueError):
            validate_honua_planner_profile(execution(READ_SETTING) + execution(COUNT), 'serial-reads')

    def test_interleaved_backends_do_not_steal_scoped_query_evidence(self):
        trace = execution(COUNT_SETTING, 42) + execution(READ_SETTING, 99)
        trace += execution('SELECT 1', 100) + execution(COUNT, 42) + execution(READ, 99)
        result = validate_honua_planner_profile(trace, 'count-jit-off-serial-reads')
        self.assertEqual(1, result['scoped_count_queries'])
        self.assertEqual(1, result['scoped_feature_queries'])
        with self.assertRaises(ValueError):
            validate_honua_planner_profile(execution(COUNT_SETTING, 42) + execution(COUNT, 99), 'count-jit-off')
        with self.assertRaises(ValueError):
            validate_honua_planner_profile(execution(COUNT_SETTING) + execution('SELECT 1') + execution(COUNT), 'count-jit-off')

    def test_parse_bind_comments_and_literals_do_not_prove_tuning(self):
        for fake in [execution(COUNT_SETTING, phase='parse <unnamed>'),
                     execution(COUNT_SETTING, phase='bind <unnamed>'),
                     execution('SELECT 1 /* ' + COUNT_SETTING + ' */'),
                     execution('SELECT $$' + COUNT_SETTING + '$$')]:
            with self.subTest(fake=fake), self.assertRaises(ValueError):
                validate_honua_planner_profile(fake + execution(COUNT), 'count-jit-off')

    def test_combined_read_count_settings_stay_on_their_own_backends(self):
        trace = execution(COMBINED_SETTING, 42) + execution(READ_SETTING, 99)
        trace += execution(READ, 99) + execution(COMBINED_COUNT, 42)
        result = validate_honua_planner_profile(trace, 'count-jit-off-serial-reads-counts')
        self.assertEqual(1, result['scoped_count_queries'])
        self.assertEqual(1, result['scoped_feature_queries'])
        swapped = execution(COMBINED_SETTING, 42) + execution(READ_SETTING, 99)
        swapped += execution(COMBINED_COUNT, 99) + execution(READ, 42)
        with self.assertRaises(ValueError):
            validate_honua_planner_profile(swapped, 'count-jit-off-serial-reads-counts')

    def test_serial_count_setting_cannot_be_substituted_for_feature_setting(self):
        for profile, trace in [
            ('serial-counts', READ_BATCH),
            ('serial-reads', SERIAL_COUNT_BATCH),
            ('count-jit-off', SERIAL_COUNT_BATCH),
            ('count-jit-off-serial-counts', SERIAL_COUNT_BATCH),
            ('count-jit-off-serial-counts', COUNT_BATCH),
            ('count-jit-off-serial-counts', COUNT_BATCH + SERIAL_COUNT_BATCH),
            ('serial-counts', COMBINED_COUNT_BATCH),
            ('serial-counts', execution(READ_SETTING) + execution(COUNT)),
            ('count-jit-off-serial-counts', execution(COMBINED_SETTING) + execution(SERIAL_COUNT)),
            ('serial-counts', execution(READ_SETTING) + execution(COMBINED_COUNT)),
            ('baseline', SERIAL_COUNT_BATCH),
        ]:
            with self.subTest(profile=profile, trace=trace), self.assertRaises(ValueError):
                validate_honua_planner_profile(trace, profile)

    def test_combined_count_settings_must_belong_to_the_same_executed_batch(self):
        for trace in [
            execution(COMBINED_SETTING, 42) + execution(COMBINED_COUNT, 99),
            execution(COMBINED_SETTING) + execution('SELECT 1') + execution(COMBINED_COUNT),
            execution(COMBINED_SETTING.replace('true', 'false')) + execution(COMBINED_COUNT),
            execution(COMBINED_SETTING.replace("'0'", "'2'")) + execution(COMBINED_COUNT),
            execution(COMBINED_SETTING + ", pg_catalog.set_config('jit', 'off', true)") + execution(COMBINED_COUNT),
            execution(COMBINED_SETTING, phase='parse <unnamed>') + execution(COMBINED_COUNT),
            execution(COMBINED_SETTING, phase='bind <unnamed>') + execution(COMBINED_COUNT),
            execution(COMBINED_SETTING) + execution(COMBINED_COUNT.replace('"public"."bench_points"', 'honua.features')),
            execution(COMBINED_SETTING),
        ]:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                validate_honua_planner_profile(trace, 'count-jit-off-serial-counts')

    def test_report_rejects_profile_receipt_when_raw_trace_shows_ignored_option(self):
        manifest = {'mode': 'diagnostic', 'profile': 'source', 'honua_profile': 'serial-reads',
                    'repetitions': 1, 'servers': ['honua'], 'scenarios': [], 'binding': 'test'}
        attempt = {'id': 'pair1-honua', 'server': 'honua', 'repetition': 1, 'status': 'passed', 'rows': {}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / attempt['id']
            path.mkdir()
            claimed = validate_source_trace(execution(COUNT) + READ_BATCH, 'serial-reads')
            (path / 'source-query.json').write_text(json.dumps(claimed))
            (path / 'source-query.log').write_text(execution(COUNT) + execution(READ))
            result = report(temp, manifest, [attempt])
            self.assertTrue(any('invalid executed source-query evidence' in error for error in result['failures']))


if __name__ == '__main__':
    unittest.main()
