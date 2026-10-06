"""Owned TEMP native transactions; actual COM/locks, registry always simulated."""
from contextlib import nullcontext
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_workspace_entry import EntryTests
import NativeWorkspace as native
import NativeWindowsIO as windows
import SharedMemoryApply as tx
import SharedMemoryPlan as bridge
import SharedWorkspace as entry


class NativeTests(EntryTests):
    def setUp(self):
        super().setUp()
        self.capsule_path = self.root / 'approval.native.local.json'
        # Test default uses an explicit shortcut double; actual COM has separate cases.
        self.shortcut = patch.object(windows, 'shortcut_bytes', return_value=b'SYNTHETIC_LNK_DOUBLE')
        self.shortcut.start()
        self.addCleanup(self.shortcut.stop)
        # Every test refuses any accidental real-registry call.
        self.registry_guards = []
        for name in ('registry_snapshot', 'install_registry', 'restore_registry'):
            guard = patch.object(windows, name, side_effect=AssertionError('REAL_REGISTRY_FORBIDDEN'))
            guard.start()
            self.registry_guards.append(guard)
            self.addCleanup(guard.stop)

    def prepare(self):
        plan = entry.spec_plan(self.spec)
        capsule = native.prepare(plan, self.spec)
        native.save_preview(self.capsule_path, capsule, plan, self.spec)
        return plan, native.approval(self.capsule_path)

    def do_install(self):
        plan, capsule = self.prepare()
        result = native.install(plan, capsule, self.spec, approved=True, writers_closed=True)
        self.assertEqual(result['status'], 'NATIVE_INSTALLED')
        return capsule

    def remove(self, **kw):
        return native.remove_b(self.install, approved=True, writers_closed=True, **kw)

    def recover(self, **kw):
        return native.rollback(self.install, approved=True, writers_closed=True, **kw)

    def assert_a_preserved(self):
        self.assertEqual((self.config / '.credentials.json').read_bytes(), b'SYNTHETIC_CREDENTIAL')
        self.assertEqual((self.memory / 'MEMORY.md').read_bytes(), b'SYNTHETIC_MEMORY_SECRET')
        self.assertEqual((self.desktop / 'Original Claude.lnk').read_bytes(), b'ORIGINAL_A_SHORTCUT')

    def test_native_preview_exclusive_no_profile_writes_or_secret_bytes(self):
        before = self.bytes_snapshot()
        self.prepare()
        after = self.bytes_snapshot()
        self.assertEqual({k: v for k, v in after.items() if k != str(self.capsule_path)}, before)
        self.assertNotIn(b'SYNTHETIC_CREDENTIAL', self.capsule_path.read_bytes())
        self.assertNotIn(b'SYNTHETIC_MEMORY_SECRET', self.capsule_path.read_bytes())
        self.assertFalse(self.install.exists())
        with self.assertRaises(bridge.BridgeError):
            plan = entry.spec_plan(self.spec)
            native.save_preview(self.capsule_path, native.prepare(plan, self.spec), plan, self.spec)

    def test_native_approval_required_before_writes(self):
        plan, capsule = self.prepare()
        for flags in ((False, True), (True, False)):
            with self.assertRaises(bridge.BridgeError):
                native.install(plan, capsule, self.spec, approved=flags[0], writers_closed=flags[1])
        self.assertFalse(self.install.exists())

    def test_native_stale_spec_refuses_before_install(self):
        plan, capsule = self.prepare()
        self.spec.write_bytes(self.spec.read_bytes() + b' ')
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_PREVIEW_STALE'):
            native.install(plan, capsule, self.spec, approved=True, writers_closed=True)
        self.assertFalse(self.install.exists())

    def test_native_stale_settings_refuse_before_install(self):
        plan, capsule = self.prepare()
        self.write_settings({'language': 'changed'})
        with self.assertRaises(bridge.BridgeError):
            native.install(plan, capsule, self.spec, approved=True, writers_closed=True)
        self.assertFalse(self.install.exists())

    def test_native_install_idempotence_and_owned_receipt(self):
        capsule = self.do_install()
        record = native.load(self.install)
        self.assertEqual(record['phase'], 'installed')
        self.assertEqual(len(record['files']), len(entry.workspace.ASSETS) + 3)
        before = self.bytes_snapshot()
        self.assertEqual(native.installed_again(self.install, capsule, self.spec,
            approved=True, writers_closed=True)['status'], 'NATIVE_ALREADY_INSTALLED')
        self.assertEqual(self.bytes_snapshot(), before)
        self.assert_a_preserved()

    def test_native_reinstall_changed_memory_setting_refuses(self):
        capsule = self.do_install()
        self.write_settings({'language': 'new'})
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_INSTALLED_MEMORY_SETTING_CHANGED'):
            native.installed_again(self.install, capsule, self.spec, approved=True, writers_closed=True)

    def test_native_remove_b_retains_a_memory_and_b_data(self):
        self.do_install()
        b = Path(self.profiles['B']['dataDir'])
        (b / 'keep.txt').write_bytes(b'B_DATA')
        self.assertTrue(self.remove()['b_data_retained'])
        self.assertEqual(set(json.loads((self.install / 'bin/profiles.json').read_bytes())['profiles']), {'A'})
        self.assertTrue((self.desktop / 'Claude (A existing).lnk').exists())
        self.assertFalse((self.desktop / 'Claude (B added).lnk').exists())
        self.assertEqual((b / 'keep.txt').read_bytes(), b'B_DATA')
        self.assertEqual(self.remove()['status'], 'NATIVE_B_ALREADY_REMOVED')
        self.assert_a_preserved()

    def test_native_explicit_b_deletion_exact_roots(self):
        self.do_install()
        for value in self.profiles['B'].values():
            (Path(value) / 'session-fixture.txt').write_bytes(b'B_DATA')
        self.assertFalse(self.remove(delete_b_data=True)['b_data_retained'])
        for value in self.profiles['B'].values():
            self.assertFalse(Path(value).exists())
        self.assert_a_preserved()
        self.assertEqual(native.load(self.install)['phase'], 'b_removed')

    def test_native_b_hardlink_refuses_before_manifest_change(self):
        self.do_install()
        os.link(self.memory / 'MEMORY.md', Path(self.profiles['B']['dataDir']) / 'alias.md')
        before = (self.install / 'bin/profiles.json').read_bytes()
        with self.assertRaises(bridge.BridgeError):
            self.remove(delete_b_data=True)
        self.assertEqual((self.install / 'bin/profiles.json').read_bytes(), before)
        self.assert_a_preserved()

    def test_native_unreadable_b_tree_refuses_before_manifest_change(self):
        self.do_install()
        before = (self.install / 'bin/profiles.json').read_bytes()
        def unreadable(root, **kw):
            kw['onerror'](PermissionError('INJECTED_UNREADABLE_DIRECTORY'))
            return []
        with patch.object(native.os, 'walk', side_effect=unreadable):
            with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_B_DELETE_UNREADABLE'):
                self.remove(delete_b_data=True)
        self.assertEqual((self.install / 'bin/profiles.json').read_bytes(), before)
        self.assertTrue((self.desktop / 'Claude (B added).lnk').exists())

    def test_native_modified_shortcut_refuses_before_manifest_change(self):
        self.do_install()
        (self.desktop / 'Claude (B added).lnk').write_bytes(b'OTHER_OWNER')
        before = (self.install / 'bin/profiles.json').read_bytes()
        with self.assertRaises(bridge.BridgeError):
            self.remove()
        self.assertEqual((self.install / 'bin/profiles.json').read_bytes(), before)

    def test_native_replaced_asset_refuses_recovery(self):
        self.do_install()
        target = self.install / 'bin/Launch-Claude.ps1'
        raw = target.read_bytes()
        target.unlink()
        target.write_bytes(raw)
        with self.assertRaises(bridge.BridgeError):
            self.recover()

    def test_native_rollback_preserves_unrelated_settings_and_additions(self):
        self.do_install()
        self.write_settings({bridge.KEY: str(self.memory), 'language': 'later', 'env': {'TOKEN': 'SYNTHETIC_NEW'}})
        (self.install / 'unowned.txt').write_bytes(b'UNOWNED')
        self.assertEqual(self.recover()['status'], 'NATIVE_ROLLED_BACK')
        self.assertEqual(json.loads(self.settings.read_bytes()), {'language': 'later', 'env': {'TOKEN': 'SYNTHETIC_NEW'}})
        self.assertEqual((self.install / 'unowned.txt').read_bytes(), b'UNOWNED')
        self.assertTrue((self.install / 'bin/route.lock').exists())
        self.assertEqual(self.recover()['status'], 'NATIVE_ALREADY_ROLLED_BACK')
        self.assert_a_preserved()

    def test_native_changed_selected_key_preserved_and_refused(self):
        self.do_install()
        self.write_settings({bridge.KEY: 'C:\\DifferentMemory'})
        with self.assertRaises(bridge.BridgeError):
            self.recover()
        self.assertEqual(json.loads(self.settings.read_bytes())[bridge.KEY], 'C:\\DifferentMemory')

    def test_native_partial_install_shortcut_failure_recovers(self):
        plan, capsule = self.prepare()
        with patch.object(windows, 'shortcut_bytes', side_effect=bridge.BridgeError('INJECTED_COM_FAILURE')):
            with self.assertRaises(bridge.BridgeError):
                native.install(plan, capsule, self.spec, approved=True, writers_closed=True)
        self.assertEqual(native.load(self.install)['phase'], 'installing')
        with self.assertRaises(bridge.BridgeError):
            self.remove()
        self.assertEqual(self.recover()['status'], 'NATIVE_ROLLED_BACK')
        self.assert_a_preserved()

    def test_native_pending_intent_requires_explicit_disarm(self):
        self.do_install()
        target = self.install / 'bin/target.txt'
        target.write_bytes(b'SYNTHETIC_INTENT')
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_ROUTING_INTENT_REQUIRES_DISARM'):
            self.remove()
        self.assertEqual(target.read_bytes(), b'SYNTHETIC_INTENT')

    def test_native_real_share_none_contention_retains_lock(self):
        self.do_install()
        lock = self.install / 'bin/route.lock'
        with windows.routing_guard(lock):
            with self.assertRaisesRegex(bridge.BridgeError, 'ROUTER_BUSY_OR_LOCK_UNAVAILABLE'):
                self.remove()
        self.assertTrue(lock.exists())
        self.assertEqual(self.remove()['status'], 'NATIVE_B_REMOVED')

    def test_native_operation_lock_contention(self):
        self.do_install()
        with tx.locked(self.install / 'operation.lock'):
            with self.assertRaisesRegex(bridge.BridgeError, 'TRANSACTION_BUSY'):
                self.remove()

    def test_native_corrupt_receipt_refuses(self):
        self.do_install()
        receipt = native.record_path(self.install)
        obj = json.loads(receipt.read_bytes())
        obj['record']['phase'] = 'b_removed'
        receipt.write_bytes(tx.encode(obj))
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_RECEIPT_INTEGRITY'):
            self.remove()

    def test_native_cli_requires_approval_without_reading_secret(self):
        with patch.object(bridge, 'read_optional', side_effect=AssertionError('SECRET_READ')):
            for action in ('native-install', 'native-remove-b', 'native-rollback'):
                code, output = self.run_entry([action, '--spec', str(self.config / '.credentials.json')])
                self.assertEqual(code, 2)
                self.assertNotIn('SYNTHETIC', output)

    def test_native_cli_conflicting_preview_flags_refuse(self):
        code, output = self.run_entry(['native-preview', '--spec', str(self.spec),
            '--output', str(self.capsule_path), '--approve-protocol'])
        self.assertEqual(code, 2)
        self.assertFalse(self.capsule_path.exists())

    def test_native_real_com_unicode_shortcuts_roundtrip(self):
        self.shortcut.stop()
        staging = self.root / 'Éléments natifs 日本'
        staging.mkdir()
        raw = windows.shortcut_bytes({'script': str(staging / 'launch.vbs'), 'dataDir': str(self.data),
            'configDir': str(self.config), 'role': 'A'}, staging)
        self.assertTrue(raw.startswith(b'\x4c\x00\x00\x00'))  # Shell Link header, not a JSON double.
        self.assertEqual(list(staging.iterdir()), [])

    def test_native_com_failure_does_not_publish_shortcut(self):
        self.shortcut.stop()
        with patch.object(windows.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'', b'SECRET')):
            with self.assertRaisesRegex(bridge.BridgeError, '^SHORTCUT_COM_OR_READBACK_FAILED$'):
                windows.shortcut_bytes({'script': str(self.root / 'launch.vbs'), 'dataDir': str(self.data),
                    'configDir': str(self.config), 'role': 'A'}, self.root)
        self.assertFalse(any(self.root.glob('.shortcut-*')))
        with patch.object(windows.subprocess, 'run', side_effect=subprocess.TimeoutExpired('SYNTHETIC_SECRET', 30)):
            with self.assertRaisesRegex(bridge.BridgeError, '^SHORTCUT_COM_TIMEOUT$'):
                windows.shortcut_bytes({'script': str(self.root / 'launch.vbs'), 'dataDir': str(self.data),
                    'configDir': str(self.config), 'role': 'A'}, self.root)
        self.assertFalse(any(self.root.glob('.shortcut-*')))

    def test_native_full_com_install_remove_rollback(self):
        self.shortcut.stop()
        self.do_install()
        self.assertTrue((self.desktop / 'Claude (B added).lnk').read_bytes().startswith(b'\x4c\0\0\0'))
        self.remove()
        self.recover()
        self.assert_a_preserved()

    def test_native_interrupted_manifest_write_requires_review(self):
        self.do_install()
        original = tx.replace_checked
        def interrupt(path, payload, expected):
            original(path, payload, expected)
            if path.name == 'profiles.json':
                raise OSError('INJECTED_AFTER_MANIFEST_REPLACE')
        with patch.object(tx, 'replace_checked', side_effect=interrupt):
            with self.assertRaises(OSError):
                self.remove()
        with self.assertRaises(bridge.BridgeError):
            self.recover()
        self.assertTrue((self.desktop / 'Claude (B added).lnk').exists())
        self.assert_a_preserved()

    def test_native_reordered_profile_keys_are_valid(self):
        obj = json.loads(self.spec.read_bytes())
        for role in ('A', 'B'):
            obj['profiles'][role] = dict(reversed(list(obj['profiles'][role].items())))
        self.spec.write_bytes(tx.encode(obj))
        self.do_install()
        self.assertEqual(native.load(self.install)['phase'], 'installed')
        self.recover()

    def test_native_ps_wrappers_both_shells_owned_fixture(self):
        scripts = Path(__file__).resolve().parents[1] / 'scripts'
        for shell in ('powershell', 'pwsh'):
            with self.subTest(shell=shell):
                fixture = EntryTests('test_help_offline')
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                capsule = fixture.root / 'wrapper.native.local.json'
                def command(script, arguments):
                    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-File', str(scripts / script),
                        *arguments, '-PythonExecutable', sys.executable], capture_output=True, timeout=45,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    return json.loads(result.stdout)
                preview = command('Setup.ps1', ['-NativeSpec', str(fixture.spec), '-NativePreview', str(capsule)])
                self.assertEqual(preview['status'], 'NATIVE_PREVIEW_SAVED')
                args = ['-NativeSpec', str(fixture.spec), '-NativeApproval', str(capsule), '-Approved', '-WritersClosed']
                self.assertEqual(command('Setup.ps1', args)['status'], 'NATIVE_INSTALLED')
                self.assertEqual(command('Setup.ps1', args)['status'], 'NATIVE_ALREADY_INSTALLED')
                args = ['-Native', '-InstallDir', str(fixture.install), '-Approved', '-WritersClosed']
                self.assertEqual(command('Uninstall.ps1', args)['status'], 'NATIVE_B_REMOVED')
                self.assertEqual(command('Uninstall.ps1', args + ['-Rollback'])['status'], 'NATIVE_ROLLED_BACK')
                self.assertTrue((fixture.desktop / 'Original Claude.lnk').exists())
                self.assertTrue(fixture.memory.exists())

    def test_native_packaged_entry_import_and_install_temp_only(self):
        import zipfile
        archive = self.root / 'native-fixture.zip'
        entry.package(archive)
        destination = self.root / 'Extracted Native Fixture'
        with zipfile.ZipFile(archive) as z:
            allowed = {'scripts/' + name for name in entry.PACKAGE_FILES} | set(entry.PACKAGE_DOCS) | {'PACKAGE.json'}
            self.assertEqual(set(z.namelist()), allowed)
            for name in z.namelist():
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(z.read(name))
        def run(args):
            r = subprocess.run([sys.executable, '-B', str(destination / 'scripts/SharedWorkspace.py'), *args],
                capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(r.returncode, 0, r.stderr.decode(errors='replace'))
            return json.loads(r.stdout)
        run(['native-preview', '--spec', str(self.spec), '--output', str(self.capsule_path)])
        result = run(['native-install', '--spec', str(self.spec), '--approval', str(self.capsule_path),
            '--approved', '--writers-closed'])
        self.assertEqual(result['status'], 'NATIVE_INSTALLED')
        self.assertEqual(run(['native-rollback', '--install-dir', str(self.install),
            '--approved', '--writers-closed'])['status'], 'NATIVE_ROLLED_BACK')
        self.assert_a_preserved()

    def test_dedicated_host_refuses_invalid_input_and_forwards_one_quoted_argument(self):
        host = Path(__file__).resolve().parents[1] / 'scripts/ClaudeLoginRouter.exe'
        if not host.exists():
            windows.materialize_router_host(host.with_suffix('.cs'))
        fixture = self.root / 'Host roundtrip'
        fixture.mkdir()
        target = fixture / host.name
        target.write_bytes(host.read_bytes())
        captured = fixture / 'argument.txt'
        (fixture / 'ClaudeOpenShim.ps1').write_text("param([string]$Url)\n[IO.File]::WriteAllText($env:FIXTURE_ROUTER_CAPTURE,$Url,[Text.UTF8Encoding]::new($false))\nexit 7\n")
        env = dict(os.environ, FIXTURE_ROUTER_CAPTURE=str(captured))
        for args in ([], ['https://example.invalid'], ['claude://bad\nnewline'], ['claude://x', 'extra']):
            r = subprocess.run([str(target), *args], env=env, capture_output=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(r.returncode, 2)
            self.assertFalse(captured.exists())
        url = 'claude://callback?code=SYNTHETIC&state=quote"slash\\\\'
        r = subprocess.run([str(target), url], env=env, capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(r.returncode, 7)
        self.assertEqual(captured.read_text(encoding='utf-8'), url)
        self.assertFalse(r.stdout or r.stderr)


if __name__ == '__main__':
    # Avoid recounting inherited fixture contracts.
    suite = unittest.TestSuite(NativeTests(name) for name in sorted(NativeTests.__dict__) if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
