"""Actual Windows APIs in a new disposable HKCU namespace, never real associations.

All production namespace/mutex constants are redirected before any operation.
An independent boundary interceptor rejects any open/create/delete outside the
unique test namespace. Cleanup refuses unknown values/children, never sweeps HKCU.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
import json
from pathlib import Path
import uuid
import winreg
from unittest.mock import patch
import unittest

from test_native_workspace import NativeTests, windows, native, bridge


class RegistryApiTests(NativeTests):
    def setUp(self):
        super().setUp()
        for guard in self.registry_guards:
            guard.stop()
        token = uuid.uuid4().hex
        self.prefix = 'Software\\ClaudeSharedWorkspaceFixture-' + token
        self.original = {name: getattr(winreg, name) for name in ('OpenKey', 'CreateKeyEx', 'DeleteKey', 'SetValueEx')}
        try:
            existing = self.original['OpenKey'](winreg.HKEY_CURRENT_USER, self.prefix)
        except FileNotFoundError:
            pass
        else:
            existing.Close()
            raise AssertionError('REGISTRY_FIXTURE_COLLISION')
        with self.original['CreateKeyEx'](winreg.HKEY_CURRENT_USER, self.prefix, 0, winreg.KEY_WRITE) as key:
            self.original['SetValueEx'](key, 'FixtureOwner', 0, winreg.REG_SZ, token)
        self.token = token
        self.addCleanup(self.cleanup_registry)
        for name, value in (('ROUTER', self.prefix + '\\Router'),
                            ('CAPABILITIES', self.prefix + '\\CapabilitiesRoot'),
                            ('REGISTERED', self.prefix + '\\RegisteredApplications'),
                            ('VALUE', 'FixtureRouter'), ('MUTEX_NAME', 'Local\\ClaudeFixtureMutex-' + token)):
            guard = patch.object(windows, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        for name in ('OpenKey', 'CreateKeyEx', 'DeleteKey'):
            def bounded(root, path, *args, _name=name, **kw):
                if root != winreg.HKEY_CURRENT_USER or not path.startswith(self.prefix + '\\'):
                    raise AssertionError('REAL_REGISTRY_NAMESPACE_FORBIDDEN')
                return self.original[_name](root, path, *args, **kw)
            guard = patch.object(winreg, name, bounded)
            guard.start()
            self.addCleanup(guard.stop)

    def cleanup_registry(self):
        # All interceptors/constants have already been restored by LIFO cleanup.
        with self.original['OpenKey'](winreg.HKEY_CURRENT_USER, self.prefix) as key:
            value, kind = winreg.QueryValueEx(key, 'FixtureOwner')
            if value != self.token or kind != winreg.REG_SZ:
                raise AssertionError('REGISTRY_FIXTURE_OWNERSHIP_CHANGED')
            children, values, _ = winreg.QueryInfoKey(key)
            if children or values != 1:
                raise AssertionError('REGISTRY_FIXTURE_UNKNOWN_ADDITIONS_RETAINED')
        self.original['DeleteKey'](winreg.HKEY_CURRENT_USER, self.prefix)

    def delete_registered_fixture(self, expected):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, windows.REGISTERED) as key:
            children, values, _ = winreg.QueryInfoKey(key)
            actual = dict((name, (value, kind)) for name, value, kind in
                          (winreg.EnumValue(key, i) for i in range(values)))
            self.assertEqual(children, 0)
            self.assertEqual(actual, expected, 'UNKNOWN_FIXTURE_VALUES_RETAINED')
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, windows.REGISTERED)

    def test_actual_registry_install_readback_restore_shared_value(self):
        before = windows.registry_snapshot()
        self.assertTrue(windows.empty_registry(before))
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, windows.REGISTERED, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, 'OtherFixture', 0, winreg.REG_SZ, 'UNCHANGED')
        desired = windows.desired_registry(self.install)
        try:
            windows.install_registry(before, desired)
            self.assertEqual(windows.registry_snapshot(), desired)
            windows.restore_registry(before, desired)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, windows.REGISTERED) as key:
                self.assertEqual(winreg.QueryValueEx(key, 'OtherFixture')[0], 'UNCHANGED')
            self.assertTrue(windows.empty_registry(windows.registry_snapshot()))
        finally:
            current = windows.registry_snapshot()
            if not windows.empty_registry(current):
                windows.restore_registry(before, desired, allow_partial=True)
            self.delete_registered_fixture({'OtherFixture': ('UNCHANGED', winreg.REG_SZ)})

    def test_actual_registry_partial_write_restores_owned_subset(self):
        before = windows.registry_snapshot()
        desired = windows.desired_registry(self.install)
        count = [0]
        def interrupt(*args, **kw):
            count[0] += 1
            if count[0] == 4:
                raise OSError('INJECTED_REGISTRY_WRITE_FAILURE')
            return self.original['SetValueEx'](*args, **kw)
        try:
            with patch.object(winreg, 'SetValueEx', side_effect=interrupt):
                with self.assertRaises(OSError):
                    windows.install_registry(before, desired)
            self.assertTrue(windows.partial_owned(windows.registry_snapshot(), desired))
            windows.restore_registry(before, desired, allow_partial=True)
            self.assertTrue(windows.empty_registry(windows.registry_snapshot()))
        finally:
            if not windows.empty_registry(windows.registry_snapshot()):
                windows.restore_registry(before, desired, allow_partial=True)

    def test_actual_registry_foreign_value_blocks_restore(self):
        before = windows.registry_snapshot()
        desired = windows.desired_registry(self.install)
        try:
            windows.install_registry(before, desired)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, windows.ROUTER, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, 'ExternalFixture', 0, winreg.REG_SZ, 'RETAIN_ME')
            with self.assertRaisesRegex(bridge.BridgeError, 'ROUTER_REGISTRY_RESTORE_CONFLICT'):
                windows.restore_registry(before, desired)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, windows.ROUTER, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                self.assertEqual(winreg.QueryValueEx(key, 'ExternalFixture')[0], 'RETAIN_ME')
                winreg.DeleteValue(key, 'ExternalFixture')  # Only this test-created value, after refusal proof.
        finally:
            if not windows.empty_registry(windows.registry_snapshot()):
                windows.restore_registry(before, desired, allow_partial=True)
            self.delete_registered_fixture({})

    def test_actual_mutex_other_thread_refuses_and_releases(self):
        def contender():
            with self.assertRaisesRegex(bridge.BridgeError, 'ROUTER_MUTEX_BUSY'):
                with windows.registry_guard():
                    self.fail('CONTENDER_ENTERED')
        with windows.registry_guard():
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(contender).result(timeout=5)
        with windows.registry_guard():
            pass

    def test_actual_metadata_repair_preserves_command_and_refuses_foreign_change(self):
        before = windows.registry_snapshot()
        desired = windows.desired_registry(self.install)
        old = copy.deepcopy(desired)
        old['router']['children'].pop('Application')
        old['router']['children'].pop('DefaultIcon')
        caps = old['capabilities']['children']['Capabilities']['values']
        caps.pop('ApplicationIcon')
        caps['ApplicationName'] = 'Claude Login Router'
        try:
            windows.install_registry(before, old)
            windows.repair_registration_metadata(old, desired)
            self.assertEqual(windows.registry_snapshot(), desired)
            self.assertEqual(old['router']['children']['shell'], desired['router']['children']['shell'])
            self.assertEqual(desired['capabilities']['children']['Capabilities']['values']['ApplicationName'], windows.VALUE)
            with self.assertRaises(bridge.BridgeError):
                windows.repair_registration_metadata(old, desired)
        finally:
            current = windows.registry_snapshot()
            if not windows.empty_registry(current):
                windows.restore_registry(before, current)
            self.delete_registered_fixture({})

    def test_actual_host_upgrade_refuses_stale_snapshot_and_restores(self):
        before = windows.registry_snapshot()
        desired = windows.desired_registry(self.install)
        legacy = windows.legacy_host_registry(desired, self.install)
        try:
            windows.install_registry(before, legacy)
            windows.upgrade_host_registration(legacy, desired, self.install)
            self.assertEqual(windows.registry_snapshot(), desired)
            with self.assertRaisesRegex(bridge.BridgeError, 'ROUTER_HOST_UPGRADE_CONFLICT'):
                windows.upgrade_host_registration(legacy, desired, self.install)
        finally:
            current = windows.registry_snapshot()
            if not windows.empty_registry(current):
                windows.restore_registry(before, current)
            self.delete_registered_fixture({})

    def test_repair_maintenance_keeps_owned_receipt_valid_and_profiles_intact(self):
        spec = importlib.util.spec_from_file_location('registration_repair',
            Path(__file__).resolve().parents[1] / 'scripts/Repair-Registration.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        self.do_install()  # TEMP profiles, no real URI registration.
        record = native.load(self.install)
        before = windows.registry_snapshot()
        legacy = copy.deepcopy(windows.desired_registry(self.install))
        legacy['router']['children'].pop('Application')
        legacy['router']['children'].pop('DefaultIcon')
        values = legacy['capabilities']['children']['Capabilities']['values']
        values.pop('ApplicationIcon')
        values['ApplicationName'] = 'Claude Login Router'
        windows.install_registry(before, legacy)
        record.update(registry_before=before, registry_after=legacy, registry_phase='applied')
        native.persist(native.record_path(self.install), record)
        calls = [0]
        def validated_version_boundary(install):
            calls[0] += 1
            return copy.deepcopy(record) if calls[0] == 1 else native.load(install)
        try:
            # Old-version validation is a boundary stub here; actual old installed
            # interpreter validation is retained in the local host repair receipt.
            with patch.object(helper, 'installed_record', side_effect=validated_version_boundary):
                self.assertEqual(helper.repair(self.install)['status'], 'REGISTRATION_METADATA_REPAIRED')
            checked = native.load(self.install)
            self.assertEqual(checked['registry_after'], windows.registry_snapshot())
            self.assertEqual(len(list(self.install.glob('registration-repair-*.source-backup'))), 1)
            journal = next(self.install.glob('registration-repair-*.json'))
            self.assertEqual(json.loads(journal.read_bytes())['phase'], 'completed')
            self.assert_a_preserved()
        finally:
            windows.restore_registry(before, windows.registry_snapshot())
            self.delete_registered_fixture({})


if __name__ == '__main__':
    suite = unittest.TestSuite(RegistryApiTests(name) for name in sorted(RegistryApiTests.__dict__) if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
