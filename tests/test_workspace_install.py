"""Fixture Windows adapter only; native shortcuts/registry/MSIX stay NOT_RUN."""
from pathlib import Path
import sys
import unittest
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_workspace_plan import WorkspaceTests
import SharedWorkspacePlan as workspace
import SharedMemoryPlan as bridge


class InstallTests(WorkspaceTests):
    def setUp(self):
        super().setUp()
        self.adapter = workspace.FixtureWindows(self.root)

    def install_fixture(self, plan=None):
        return workspace.execute_fixture(plan or self.workspace(), self.adapter, writers_closed=True)

    def test_install_preserves_a_projects_memory(self):
        before = self.bytes_snapshot()
        plan = self.workspace()
        result = self.install_fixture(plan)
        self.assertEqual(result['status'], 'INSTALLED_FIXTURE')
        self.assertEqual(result['native_install'], 'NOT_RUN')
        for path, raw in before.items():
            self.assertEqual(Path(path).read_bytes(), raw)
        self.assertTrue(Path(self.profiles['B']['configDir']).is_dir())
        self.assertIsNone(self.adapter.protocol)

    def test_same_plan_install_idempotent(self):
        plan = self.workspace()
        self.install_fixture(plan)
        before = self.bytes_snapshot()
        self.assertEqual(self.install_fixture(plan)['status'], 'ALREADY_INSTALLED_FIXTURE')
        self.assertEqual(before, self.bytes_snapshot())

    def test_closed_ack_required(self):
        with self.assertRaises(bridge.BridgeError):
            workspace.execute_fixture(self.workspace(), self.adapter, writers_closed=False)
        self.assertFalse(self.install.exists())

    def test_real_target_escape_refused(self):
        with self.assertRaises(bridge.BridgeError):
            self.adapter.check(Path(__file__).resolve())

    def test_protocol_changed_after_plan_refused(self):
        self.adapter.protocol = 'fixture-before'
        plan = self.workspace(protocol_change=True, protocol_consent=True, protocol_before='fixture-before')
        self.adapter.protocol = 'different-owner'
        with self.assertRaises(bridge.BridgeError):
            self.install_fixture(plan)
        self.assertFalse(self.install.exists())

    def test_protocol_rollback_conflict_preserved(self):
        plan = self.workspace(protocol_change=True, protocol_consent=True, protocol_before=None)
        self.install_fixture(plan)
        self.adapter.protocol = 'new-owner'
        with self.assertRaises(bridge.BridgeError):
            workspace.rollback_fixture(self.install, self.adapter, writers_closed=True)
        self.assertEqual(self.adapter.protocol, 'new-owner')
        self.assertTrue(self.install.exists())

    def test_partial_failure_receipt_and_recovery(self):
        before = self.bytes_snapshot()
        self.adapter.fail_after = 6
        with self.assertRaises(bridge.BridgeError):
            self.install_fixture()
        self.assertTrue((self.install / 'ownership.json').is_file())
        result = workspace.rollback_fixture(self.install, self.adapter, writers_closed=True)
        self.assertTrue(result['b_data_retained'])
        for path, raw in before.items():
            self.assertEqual(Path(path).read_bytes(), raw)

    def test_modified_asset_refuses_rollback(self):
        self.install_fixture()
        path = self.install / 'bin' / 'Launch-Claude.ps1'
        path.write_bytes(b'NEW_OWNER')
        with self.assertRaises(bridge.BridgeError):
            workspace.rollback_fixture(self.install, self.adapter, writers_closed=True)
        self.assertEqual(path.read_bytes(), b'NEW_OWNER')

    def test_runtime_lock_never_deleted(self):
        self.install_fixture()
        lock = self.install / 'bin' / 'route.lock'
        lock.write_bytes(b'0')
        with self.assertRaises(bridge.BridgeError):
            workspace.rollback_fixture(self.install, self.adapter, writers_closed=True)
        self.assertTrue(lock.exists())

    def test_complete_rollback_preserves_b_and_official_package(self):
        self.install_fixture()
        result = workspace.rollback_fixture(self.install, self.adapter, writers_closed=True)
        self.assertFalse(result['official_package_removal'])
        self.assertFalse(self.install.exists())
        self.assertTrue(Path(self.profiles['B']['dataDir']).exists())
        self.assertTrue((self.desktop / 'Original Claude.lnk').exists())

    def test_legacy_setup_refuses_before_any_install(self):
        setup = Path(__file__).resolve().parents[1] / 'scripts' / 'Setup.ps1'
        for shell in ('powershell.exe', 'pwsh.exe'):
            result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-File', str(setup),
                                     '-InstallDir', str(self.install)], capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'NATIVE_INSTALL_NOT_ADMITTED', result.stderr)
            self.assertFalse(self.install.exists())

    def test_unrecorded_install_file_preserved_before_rollback(self):
        self.install_fixture()
        extra = self.install / 'bin' / 'unrelated.txt'
        extra.write_bytes(b'NEW_OWNER')
        before = self.bytes_snapshot()
        with self.assertRaises(bridge.BridgeError):
            workspace.rollback_fixture(self.install, self.adapter, writers_closed=True)
        self.assertEqual(before, self.bytes_snapshot())


if __name__ == '__main__':
    unittest.main(defaultTest='InstallTests')
