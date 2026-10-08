"""Receipt reconciliation on owned TEMP installs: B's roots recreated outside the receipt's view.

The drift is produced as it happened for real: B's folder is deleted and recreated, so its path is unchanged
and its physical file identity is not. Only B's own roots may be re-recorded; everything else stays fatal.
"""
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from test_native_workspace import NativeTests, windows, native, bridge, tx


class ReconcileTests(NativeTests):
    def setUp(self):
        super().setUp()
        self.running = patch.object(windows, 'claude_profile_running', return_value=False)
        self.running.start()
        self.addCleanup(self.running.stop)
        self.do_install()
        self.b_data = Path(self.profiles['B']['dataDir'])
        self.b_config = Path(self.profiles['B']['configDir'])

    def recreate(self, path):
        """Same path, new physical identity (what the MSIX redirection left behind)."""
        # Holding the old folder's file id forces the new one to differ even when the OS reuses an index.
        holder = path.with_name(path.name + '-holder')
        path.rename(holder)
        path.mkdir()
        (path / 'real-data.txt').write_bytes(b'B_REAL_DATA')
        shutil.rmtree(holder)

    def receipt_bytes(self):
        return native.record_path(self.install).read_bytes()

    def test_drift_is_what_refuses_the_receipt_before_reconciliation(self):
        self.recreate(self.b_data)
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_OWNED_DIRECTORY_CHANGED'):
            native.load(self.install)
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_OWNED_DIRECTORY_CHANGED'):
            self.remove()

    def test_preview_reports_the_drift_and_writes_nothing(self):
        self.recreate(self.b_data)
        before = (self.receipt_bytes(), sorted(p.name for p in self.install.iterdir()))
        result = native.reconcile(self.install, approved=False, writers_closed=False)
        self.assertEqual((result['status'], result['would_validate'], result['writes_nothing']),
                         ('NATIVE_RECONCILE_PREVIEW', True, True))
        self.assertEqual([d['path'] for d in result['drifted']], [str(self.b_data)])
        self.assertNotEqual(result['drifted'][0]['recorded_file_id'], result['drifted'][0]['current_file_id'])
        self.assertEqual((self.receipt_bytes(), sorted(p.name for p in self.install.iterdir())), before)

    def test_apply_re_records_only_the_b_root_and_unblocks_the_native_operations(self):
        self.recreate(self.b_data)
        before = json.loads(self.receipt_bytes())['record']
        result = native.reconcile(self.install, approved=True, writers_closed=True)
        self.assertEqual((result['status'], result['profiles_modified'], result['registry_modified']),
                         ('NATIVE_RECEIPT_RECONCILED', False, False))
        after = native.load(self.install)
        # Exactly one field of one entry changed.
        changed = [(b['path'], a['identity']['file_id']) for b, a in zip(before['directories'], after['directories'])
                   if b['identity'] != a['identity']]
        self.assertEqual([c[0] for c in changed], [str(self.b_data)])
        for key in ('phase', 'files', 'protected', 'protected_identities', 'registry_after', 'registry_phase', 'b_roots'):
            self.assertEqual(before[key], after[key], key)
        # A journal keeps the previous receipt and the change.
        journals = list(self.install.glob('reconcile-*.json'))
        self.assertEqual(len(journals), 1)
        journal = json.loads(journals[0].read_bytes())
        self.assertEqual((journal['phase'], journal['receipt_before']['record']['phase']), ('completed', 'installed'))
        # The data that was really there is untouched and the transitions that were refused now work.
        self.assertEqual((self.b_data / 'real-data.txt').read_bytes(), b'B_REAL_DATA')
        self.assertEqual(native.reconcile(self.install, approved=True, writers_closed=True)['status'],
                         'NATIVE_RECEIPT_ALREADY_CURRENT')
        self.assertTrue(self.remove()['b_data_retained'])
        self.assertEqual((self.b_data / 'real-data.txt').read_bytes(), b'B_REAL_DATA')
        self.assert_a_preserved()

    def test_rollback_works_after_reconciliation(self):
        self.recreate(self.b_data)
        self.recreate(self.b_config)
        native.reconcile(self.install, approved=True, writers_closed=True)
        self.assertEqual(self.recover()['status'], 'NATIVE_ROLLED_BACK')
        self.assertTrue(self.b_data.exists() and self.b_config.exists())     # B data is retained by rollback
        self.assert_a_preserved()

    def test_nothing_to_do_when_the_receipt_is_current(self):
        self.assertEqual(native.reconcile(self.install, approved=True, writers_closed=True)['status'],
                         'NATIVE_RECEIPT_ALREADY_CURRENT')
        self.assertEqual(list(self.install.glob('reconcile-*.json')), [])

    def test_one_approval_flag_alone_is_refused(self):
        self.recreate(self.b_data)
        for flags in ((True, False), (False, True)):
            with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_APPROVAL_AND_CLOSED_WRITERS_REQUIRED'):
                native.reconcile(self.install, approved=flags[0], writers_closed=flags[1])
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_OWNED_DIRECTORY_CHANGED'):
            native.load(self.install)

    def test_running_b_is_refused_and_the_receipt_is_untouched(self):
        self.recreate(self.b_data)
        before = self.receipt_bytes()
        with patch.object(windows, 'claude_profile_running', return_value=True):
            with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_B_RUNNING_CLOSE_IT_FIRST'):
                native.reconcile(self.install, approved=True, writers_closed=True)
        self.assertEqual(self.receipt_bytes(), before)
        self.assertEqual(list(self.install.glob('reconcile-*.json')), [])

    def test_a_non_b_owned_directory_drift_stays_fatal(self):
        shutil.rmtree(self.install / 'bin')           # the receipt-owned launcher folder is not B's root
        (self.install / 'bin').mkdir()
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_OWNED_DIRECTORY_CHANGED'):
            native.reconcile(self.install, approved=True, writers_closed=True)

    def test_a_changed_owned_file_is_not_hidden_by_reconciliation(self):
        self.recreate(self.b_data)
        shortcut = self.desktop / 'Claude (B added).lnk'
        shortcut.write_bytes(b'TAMPERED')
        before = self.receipt_bytes()
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_OWNED_FILE_CHANGED'):
            native.reconcile(self.install, approved=True, writers_closed=True)
        self.assertEqual(self.receipt_bytes(), before)

    def test_a_replaced_b_root_that_is_a_link_is_refused(self):
        shutil.rmtree(self.b_data)
        target = self.root / 'elsewhere'
        target.mkdir()
        import _winapi
        _winapi.CreateJunction(str(target), str(self.b_data))
        before = self.receipt_bytes()
        with self.assertRaises(bridge.BridgeError):
            native.reconcile(self.install, approved=True, writers_closed=True)
        self.assertEqual(self.receipt_bytes(), before)

    def test_a_record_taken_from_a_private_redirected_store_is_reconciled(self):
        # What really happened: the recorded location was Codex's private store, not the declared path.
        record = native.load(self.install)
        private = 'c:\\users\\x\\appdata\\local\\packages\\openai.codex_x\\localcache\\roaming\\claude-b'
        for entry in record['directories']:
            if entry['path'] == str(self.b_data):
                entry['identity'] = {**entry['identity'], 'canonical': private, 'file_id': [1, 2, 3]}
        native.persist(native.record_path(self.install), record)
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_OWNED_DIRECTORY_CHANGED'):
            native.load(self.install)
        preview = native.reconcile(self.install, approved=False, writers_closed=False)
        self.assertEqual(preview['drifted'][0]['recorded_location'], private)
        self.assertTrue(preview['drifted'][0]['current_location'].endswith(self.b_data.name.casefold()))
        self.assertEqual(native.reconcile(self.install, approved=True, writers_closed=True)['status'],
                         'NATIVE_RECEIPT_RECONCILED')
        native.load(self.install)

    def test_a_directory_that_is_not_really_at_its_declared_path_is_refused(self):
        self.recreate(self.b_data)
        real = bridge.identity

        def redirected(path):
            found = real(path)
            if str(path) == str(self.b_data):
                found = {**found, 'canonical': 'c:\\somewhere\\else'}
            return found
        before = self.receipt_bytes()
        with patch.object(bridge, 'identity', side_effect=redirected):
            with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_B_ROOT_NOT_AT_ITS_DECLARED_PATH'):
                native.reconcile(self.install, approved=True, writers_closed=True)
        self.assertEqual(self.receipt_bytes(), before)

    def test_a_failed_final_validation_restores_the_previous_receipt(self):
        self.recreate(self.b_data)
        before = self.receipt_bytes()
        real_load = native.load
        calls = []

        def flaky(install, drifted=None):
            calls.append(drifted is None)
            if drifted is None:                      # the validation after the write
                raise bridge.BridgeError('NATIVE_OWNED_FILE_CHANGED')
            return real_load(install, drifted)
        with patch.object(native, 'load', side_effect=flaky):
            with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_OWNED_FILE_CHANGED'):
                native.reconcile(self.install, approved=True, writers_closed=True)
        self.assertEqual(self.receipt_bytes(), before)
        self.assertEqual(json.loads(next(self.install.glob('reconcile-*.json')).read_bytes())['phase'], 'restored')

    def test_a_consumed_routing_marker_is_quiet_but_an_armed_or_unreadable_one_blocks(self):
        marker = self.install / 'bin' / 'target.txt'
        self.recreate(self.b_data)
        for text in (b'{"version":2,"status":"armed"}', b'SYNTHETIC_INTENT', b'{"version":1,"status":"consumed"}'):
            marker.write_bytes(text)
            before = self.receipt_bytes()
            with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_ROUTING_INTENT_REQUIRES_DISARM'):
                native.reconcile(self.install, approved=True, writers_closed=True)
            self.assertEqual((self.receipt_bytes(), marker.read_bytes()), (before, text))
        for text in (b'{"version":2,"status":"consumed"}', b'{"version":2,"status":"disarmed"}'):
            marker.write_bytes(text)
            self.assertFalse(windows.route_intent_pending(marker))
        marker.write_bytes(b'{"version":2,"status":"consumed"}')
        self.assertEqual(native.reconcile(self.install, approved=True, writers_closed=True)['status'],
                         'NATIVE_RECEIPT_RECONCILED')
        self.assertEqual(marker.read_bytes(), b'{"version":2,"status":"consumed"}')

    def test_a_non_installed_phase_is_refused(self):
        self.remove()                                # a healthy receipt moves to b_removed first
        self.assertEqual(json.loads(self.receipt_bytes())['record']['phase'], 'b_removed')
        self.recreate(self.b_data)
        before = self.receipt_bytes()
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_RECONCILE_REQUIRES_INSTALLED_PHASE'):
            native.reconcile(self.install, approved=True, writers_closed=True)
        self.assertEqual(self.receipt_bytes(), before)

    def test_cli_previews_and_applies_through_the_guarded_entry(self):
        self.recreate(self.b_data)
        code, output = self.run_entry(['native-reconcile', '--install-dir', str(self.install)])
        self.assertEqual((code, json.loads(output)['status']), (0, 'NATIVE_RECONCILE_PREVIEW'))
        code, output = self.run_entry(['native-reconcile', '--install-dir', str(self.install), '--approved'])
        self.assertEqual((code, json.loads(output)['reason']), (2, 'NATIVE_APPROVAL_AND_CLOSED_WRITERS_REQUIRED'))
        code, output = self.run_entry(['native-reconcile', '--install-dir', str(self.install), '--approved', '--writers-closed'])
        self.assertEqual((code, json.loads(output)['status']), (0, 'NATIVE_RECEIPT_RECONCILED'))
        code, output = self.run_entry(['native-reconcile', '--spec', str(self.spec), '--install-dir', str(self.install)])
        self.assertEqual((code, json.loads(output)['reason']), (2, 'NATIVE_RECOVERY_ARGUMENTS'))
        with patch.object(windows, 'ancestor_package_rcs', return_value=[(1, 'Claude.exe', 122)]):
            code, output = self.run_entry(['native-reconcile', '--install-dir', str(self.install)])
        self.assertEqual((code, json.loads(output)['reason']), (2, 'PACKAGED_PROCESS_REFUSED'))

    def test_real_running_check_matches_the_exact_data_dir_and_ignores_child_processes(self):
        self.running.stop()
        try:
            lines = ('"C:\\App\\Claude.exe" --user-data-dir="C:\\Data\\Claude-B"\n'
                     '"C:\\App\\Claude.exe" --type=gpu-process --user-data-dir="C:\\Data\\Claude-C"\n'
                     '"C:\\App\\Claude.exe"\n')
            class Done:
                returncode, stdout = 0, lines
            with patch.object(windows.subprocess, 'run', return_value=Done()):
                self.assertTrue(windows.claude_profile_running('C:\\Data\\Claude-B'))
                self.assertTrue(windows.claude_profile_running('c:\\data\\claude-b\\'))
                self.assertFalse(windows.claude_profile_running('C:\\Data\\Claude-C'))    # only a child process
                self.assertFalse(windows.claude_profile_running('C:\\Data\\Claude-B2'))   # prefix is not a match
            class Failed:
                returncode, stdout = 1, ''
            with patch.object(windows.subprocess, 'run', return_value=Failed()):
                with self.assertRaisesRegex(bridge.BridgeError, 'PROFILE_RUNNING_CHECK_FAILED'):
                    windows.claude_profile_running('C:\\Data\\Claude-B')
        finally:
            self.running.start()


if __name__ == '__main__':
    unittest.main()
