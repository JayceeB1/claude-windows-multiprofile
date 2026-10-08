"""Code sessions list sync between two profiles on owned TEMP trees: real directories, real junction, no real profile.

The app refuses to save into a linked records folder; the records are copied instead. Nothing is deleted, an overwritten
record is kept in a backup, a session deleted in the app is never resurrected, and Projects (Spaces) stay per account.
"""
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'SessionRecordSync.py'
spec = importlib.util.spec_from_file_location('session_record_sync', SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def record(cli, activity, **extra):
    return json.dumps({'sessionId': 'local_' + cli, 'cliSessionId': cli, 'lastActivityAt': activity, 'title': cli, **extra})


class SessionRecordSyncTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='claude-sessync-test-'))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.install = self.root / 'ClaudeProfiles'
        self.src_desk, self.dst_desk = self.root / 'A' / 'Claude', self.root / 'B' / 'Claude-B'
        self.sess_a = self.src_desk / 'claude-code-sessions' / 'acct-a' / 'org-a'
        self.sess_b = self.dst_desk / 'claude-code-sessions' / 'acct-b' / 'org-b'
        for d in (self.install, self.sess_a, self.sess_b):
            d.mkdir(parents=True)
        self.patches = [patch.object(sync.links, 'require_unpackaged'),
                        patch.object(sync.links, 'profile_running', return_value=False)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def put(self, folder, name, text):
        (folder / name).write_text(text, encoding='utf-8')

    def run_main(self, *extra):
        argv = ['--install-dir', str(self.install), '--source-desktop', str(self.src_desk),
                '--target-desktop', str(self.dst_desk), *extra]
        out = io.StringIO()
        with redirect_stdout(out):
            code = sync.main(argv)
        return code, json.loads(out.getvalue())

    def names(self, folder):
        return sorted(p.name for p in folder.iterdir())

    def test_preview_writes_nothing(self):
        self.put(self.sess_a, 'local_a.json', record('a', 1))
        before = self.names(self.sess_b)
        code, result = self.run_main()
        self.assertEqual((code, result['status'], result['copy_to_B']), (0, 'PREVIEW', 1))
        self.assertEqual(self.names(self.sess_b), before)

    def test_apply_needs_approval(self):
        self.put(self.sess_a, 'local_a.json', record('a', 1))
        code, result = self.run_main('--apply')
        self.assertEqual((code, result['reason']), (2, 'APPROVAL_REQUIRED'))
        self.assertFalse((self.sess_b / 'local_a.json').exists())

    def test_records_flow_both_ways_and_a_second_run_is_quiet(self):
        self.put(self.sess_a, 'local_a.json', record('a', 1))
        self.put(self.sess_b, 'local_b.json', record('b', 2))
        self.put(self.sess_a, 'scheduled-tasks.json', '{"a":1}')
        code, result = self.run_main('--apply', '--approved')
        self.assertEqual((code, result['status'], result['written']), (0, 'APPLIED', 2))
        self.assertEqual(json.loads((self.sess_b / 'local_a.json').read_text(encoding='utf-8'))['cliSessionId'], 'a')
        self.assertEqual(json.loads((self.sess_a / 'local_b.json').read_text(encoding='utf-8'))['cliSessionId'], 'b')
        self.assertFalse((self.sess_b / 'scheduled-tasks.json').exists())          # only session records move
        self.assertEqual([n for n in self.names(self.sess_a) if n.startswith('.')], [])   # no temp file left behind
        self.assertEqual(self.run_main('--apply', '--approved')[1]['written'], 0)

    def test_the_later_activity_wins_and_the_other_version_is_backed_up(self):
        self.put(self.sess_a, 'local_x.json', record('x', 10, title='from-A'))
        self.put(self.sess_b, 'local_x.json', record('x', 20, title='from-B'))
        self.run_main('--apply', '--approved')
        self.assertEqual(json.loads((self.sess_a / 'local_x.json').read_text(encoding='utf-8'))['title'], 'from-B')
        kept = list((self.install / 'shared-config' / 'backups').rglob('local_x.json'))
        self.assertEqual(len(kept), 1)
        self.assertEqual(json.loads(kept[0].read_text(encoding='utf-8'))['title'], 'from-A')

    def test_a_session_deleted_in_the_app_is_not_resurrected(self):
        self.put(self.sess_a, 'local_gone.json', record('gone', 1))
        self.put(self.sess_b, 'deleted_gone', 'x')
        code, result = self.run_main('--apply', '--approved')
        self.assertEqual(result['written'], 0)
        self.assertFalse((self.sess_b / 'local_gone.json').exists())

    def test_a_legacy_junction_is_replaced_by_a_real_directory_and_a_is_untouched(self):
        shutil.rmtree(self.sess_b)
        sync.links.make_link('dir', self.sess_a, self.sess_b)
        self.put(self.sess_a, 'local_a.json', record('a', 1))
        a_before = self.names(self.sess_a)
        code, result = self.run_main()
        self.assertTrue(result['replace_legacy_link'])
        self.assertTrue(sync.links.is_link(self.sess_b))                            # preview changed nothing
        code, result = self.run_main('--apply', '--approved')
        self.assertEqual((code, result['status']), (0, 'APPLIED'))
        self.assertFalse(sync.links.is_link(self.sess_b))
        self.assertTrue(self.sess_b.is_dir())
        self.assertEqual(self.names(self.sess_b), ['local_a.json'])                 # copied back as a real file
        self.assertEqual(self.names(self.sess_a), a_before)
        self.put(self.sess_b, 'local_new.json', record('new', 5))                   # B can now register its own
        self.run_main('--apply', '--approved')
        self.assertTrue((self.sess_a / 'local_new.json').exists())

    def test_replacing_a_legacy_junction_refuses_while_b_is_open(self):
        shutil.rmtree(self.sess_b)
        sync.links.make_link('dir', self.sess_a, self.sess_b)
        with patch.object(sync.links, 'profile_running', return_value=True):
            code, result = self.run_main('--apply', '--approved')
        self.assertEqual((code, result['reason']), (2, 'TARGET_PROFILE_RUNNING_CLOSE_IT_FIRST'))
        self.assertTrue(sync.links.is_link(self.sess_b))

    def test_a_project_the_other_profile_lacks_becomes_a_plain_folder_session(self):
        space = self.src_desk / 'local-agent-mode-sessions' / 'acct-a' / 'org-a'
        space.mkdir(parents=True)
        (space / 'spaces.json').write_text(json.dumps({'spaces': [{'id': 'space-1', 'name': 'P'}]}), encoding='utf-8')
        self.put(self.sess_a, 'local_p.json', record('p', 1, spaceId='space-1', spaceIdSetBy='user', cwd='F:\\proj'))
        self.run_main('--apply', '--approved')
        arrived = json.loads((self.sess_b / 'local_p.json').read_text(encoding='utf-8'))
        self.assertNotIn('spaceId', arrived)
        self.assertNotIn('spaceIdSetBy', arrived)
        self.assertEqual(arrived['cwd'], 'F:\\proj')
        self.assertIn('spaceId', json.loads((self.sess_a / 'local_p.json').read_text(encoding='utf-8')))   # A keeps its Project
        self.assertEqual(self.run_main('--apply', '--approved')[1]['written'], 0)    # and the difference never loops

    def test_missing_or_ambiguous_stores_are_refused(self):
        (self.dst_desk / 'claude-code-sessions' / 'acct-b' / 'org-b2').mkdir()
        code, result = self.run_main()
        self.assertEqual((code, result['reason']), (2, 'SEVERAL_ACCOUNTS_OR_ORGANISATIONS'))
        shutil.rmtree(self.dst_desk / 'claude-code-sessions')
        code, result = self.run_main()
        self.assertEqual((code, result['reason']), (2, 'NO_SESSION_STORE'))


if __name__ == '__main__':
    unittest.main()
