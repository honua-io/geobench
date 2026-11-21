import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import candidate_schedule

SHA = 'de512e8123bdfbfbe20f692b236e37853b4f8294'
DIGEST = 'sha256:' + '1e' * 32
MANIFEST = f'''components:
  honua-server:
    # comment mentioning sha: {'0' * 40}
    repository: "https://github.com/honua-io/honua-server"
    publicationHistory:
      sha256: "sha256:{'ab' * 32}"

    sha: {SHA}
    image: ghcr.io/honua-io/honua-server:nightly-aot-de512e8
    digest: "{DIGEST}"
  honua-console:
    sha: {'c' * 40}
    digest: "sha256:{'cd' * 32}"
'''


class CandidateScheduleTests(unittest.TestCase):
    def test_reads_only_the_server_component_pin(self):
        self.assertEqual((SHA, DIGEST), candidate_schedule.pinned_candidate(MANIFEST))

    def test_rejects_missing_or_malformed_pins(self):
        for manifest in ('components:\n  honua-console:\n    sha: x\n',
                         MANIFEST.replace(SHA, 'pending'),
                         MANIFEST.replace(DIGEST, 'sha256:short')):
            with self.subTest(manifest=manifest[:40]), self.assertRaises(ValueError):
                candidate_schedule.pinned_candidate(manifest)

    def test_dedupes_on_completed_or_running_runs_but_retries_cancelled_ones(self):
        tag = candidate_schedule.release_tag(SHA)
        self.assertEqual('candidate-de512e8', tag)
        title = 'Benchmark candidate-de512e8'
        self.assertTrue(candidate_schedule.already_benchmarked([{'display_title': title, 'conclusion': 'failure'}], tag))
        self.assertTrue(candidate_schedule.already_benchmarked([{'display_title': title, 'conclusion': None}], tag))
        self.assertFalse(candidate_schedule.already_benchmarked([{'display_title': title, 'conclusion': 'cancelled'}], tag))
        self.assertFalse(candidate_schedule.already_benchmarked([{'display_title': 'Benchmark candidate-0000000'}], tag))


if __name__ == '__main__':
    unittest.main()
