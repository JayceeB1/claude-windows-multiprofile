"""Production registry algorithms against an explicit model; zero Windows registry writes."""
import copy
from contextlib import nullcontext
from pathlib import Path
import unittest
from unittest.mock import patch
from test_native_workspace import NativeTests, windows, native, bridge, entry
from native_registry_fixture import Registry


class RegistryTests(NativeTests):
    def setUp(self):
        super().setUp()
        for guard in self.registry_guards:
            guard.stop()
        self.registry = Registry((windows.ROUTER, windows.CAPABILITIES, windows.REGISTERED))
        for target, replacement in (('winreg', self.registry), ('registry_guard', nullcontext)):
            guard = patch.object(windows, target, replacement)
            guard.start()
            self.addCleanup(guard.stop)
        obj = entry.memory.object_json(self.spec.read_bytes())
        obj['protocol'].update(change=True, consent=True)
        self.spec.write_bytes(native.tx.encode(obj))

    def do_install(self):
        plan, capsule = self.prepare()
        result = native.install(plan, capsule, self.spec, approved=True, writers_closed=True, approve_protocol=True)
        self.assertEqual(result['status'], 'NATIVE_INSTALLED')
        self.assertEqual(result['default_app_choice'], 'MANUAL')
        return capsule

    def test_model_protocol_requires_separate_consent(self):
        plan, capsule = self.prepare()
        with self.assertRaisesRegex(bridge.BridgeError, 'SEPARATE_NATIVE_PROTOCOL_APPROVAL_REQUIRED'):
            native.install(plan, capsule, self.spec, approved=True, writers_closed=True)
        self.assertFalse(self.install.exists())
        self.assertEqual(self.registry.writes, 0)

    def test_model_existing_namespace_not_adopted(self):
        self.registry.keys[windows.ROUTER] = {}
        with self.assertRaisesRegex(bridge.BridgeError, 'EXISTING_ROUTER_NOT_ADOPTED'):
            self.prepare()
        self.assertEqual(self.registry.writes, 0)

    def test_model_register_remove_b_then_restore_preserves_unrelated_value(self):
        self.registry.keys[windows.REGISTERED] = {'OtherApp': ('UNRELATED', windows.winreg.REG_SZ)}
        self.do_install()
        expected = windows.desired_registry(self.install)
        self.assertEqual(windows.registry_snapshot(), expected)
        self.remove()
        self.assertEqual(windows.registry_snapshot(), expected)
        self.recover(approve_protocol=True)
        self.assertTrue(windows.empty_registry(windows.registry_snapshot()))
        self.assertEqual(self.registry.keys[windows.REGISTERED], {'OtherApp': ('UNRELATED', windows.winreg.REG_SZ)})
        self.assert_a_preserved()

    def test_model_restore_consent_required_before_memory_rollback(self):
        self.do_install()
        before = self.settings.read_bytes()
        with self.assertRaisesRegex(bridge.BridgeError, 'NATIVE_REGISTRY_ROLLBACK_APPROVAL_OR_CONFLICT'):
            self.recover()
        self.assertEqual(self.settings.read_bytes(), before)

    def test_model_external_registry_change_refuses_before_removal(self):
        self.do_install()
        self.registry.keys[windows.ROUTER]['Unexpected'] = ('EXTERNAL', windows.winreg.REG_SZ)
        before = self.settings.read_bytes()
        with self.assertRaises(bridge.BridgeError):
            self.remove()
        with self.assertRaises(bridge.BridgeError):
            self.recover(approve_protocol=True)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(self.registry.keys[windows.ROUTER]['Unexpected'][0], 'EXTERNAL')

    def test_model_partial_registry_write_recovers(self):
        plan, capsule = self.prepare()
        self.registry.fail_after = 4
        with self.assertRaises(OSError):
            native.install(plan, capsule, self.spec, approved=True, writers_closed=True, approve_protocol=True)
        self.assertEqual(native.load(self.install)['registry_phase'], 'applying')
        self.registry.fail_after = None
        self.recover(approve_protocol=True)
        self.assertTrue(windows.empty_registry(windows.registry_snapshot()))
        self.assert_a_preserved()

    def test_model_partial_registry_external_child_refuses(self):
        plan, capsule = self.prepare()
        self.registry.fail_after = 4
        with self.assertRaises(OSError):
            native.install(plan, capsule, self.spec, approved=True, writers_closed=True, approve_protocol=True)
        self.registry.keys[windows.ROUTER + '\\ExternalChild'] = {}
        with self.assertRaises(bridge.BridgeError):
            self.recover(approve_protocol=True)
        self.assertIn(windows.ROUTER + '\\ExternalChild', self.registry.keys)

    def test_model_registry_snapshot_limits_and_types(self):
        self.registry.keys[windows.ROUTER] = {'bad': (3, 4)}
        with self.assertRaises(bridge.BridgeError):
            windows.registry_snapshot()
        self.registry.keys[windows.ROUTER] = {str(i): ('value', windows.winreg.REG_SZ) for i in range(65)}
        with self.assertRaisesRegex(bridge.BridgeError, 'ROUTER_REGISTRY_VALUE_REFUSED'):
            windows.registry_snapshot()

    def test_model_wrong_prestate_cannot_write(self):
        empty = windows.registry_snapshot()
        self.registry.keys[windows.CAPABILITIES] = {}
        with self.assertRaises(bridge.BridgeError):
            windows.install_registry(empty, windows.desired_registry(self.install))
        self.assertEqual(self.registry.writes, 0)


if __name__ == '__main__':
    suite = unittest.TestSuite(RegistryTests(name) for name in sorted(RegistryTests.__dict__) if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
