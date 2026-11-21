import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import feature_runtime


class ReadProcessFileTests(unittest.TestCase):
    def test_reads_with_exec_when_the_image_has_cat(self):
        with patch.object(feature_runtime, 'command', return_value='maps') as command:
            self.assertEqual(feature_runtime.read_process_file('c1', '/proc/1/maps', 'sha256:helper'), 'maps')
        self.assertEqual(command.call_args.args, ('docker', 'exec', 'c1', 'cat', '/proc/1/maps'))

    def test_shell_less_image_is_read_from_a_same_user_helper(self):
        missing = subprocess.CalledProcessError(127, 'cat')
        info = {'Config': {'User': '61001:1001'}}
        with patch.object(feature_runtime, 'command', side_effect=[missing, 'maps']) as command, \
                patch.object(feature_runtime, 'inspect', return_value=info):
            self.assertEqual(feature_runtime.read_process_file('c1', '/proc/1/maps', 'sha256:helper'), 'maps')
        self.assertEqual(command.call_args.args,
                         ('docker', 'run', '--rm', '--network', 'none', '--pid', 'container:c1',
                          '--user', '61001:1001', '--entrypoint', 'cat', 'sha256:helper', '/proc/1/maps'))

    def test_not_executable_and_unset_user_fall_back_to_a_root_helper(self):
        denied = subprocess.CalledProcessError(126, 'cat')
        with patch.object(feature_runtime, 'command', side_effect=[denied, 'cmd']) as command, \
                patch.object(feature_runtime, 'inspect', return_value={'Config': {'User': ''}}):
            self.assertEqual(feature_runtime.read_process_file('c1', '/proc/1/cmdline', 'sha256:helper'), 'cmd')
        self.assertEqual('0', command.call_args.args[command.call_args.args.index('--user') + 1])

    def test_other_exec_failures_and_missing_helper_are_not_hidden(self):
        for error, helper in ((subprocess.CalledProcessError(1, 'cat'), 'sha256:helper'),
                              (subprocess.CalledProcessError(127, 'cat'), None)):
            with patch.object(feature_runtime, 'command', side_effect=[error]), \
                    self.assertRaises(subprocess.CalledProcessError):
                feature_runtime.read_process_file('c1', '/proc/1/maps', helper)


if __name__ == '__main__':
    unittest.main()
