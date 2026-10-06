"""B removal fixtures retain A routing/package and selected memory."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_workspace_install import InstallTests
import SharedWorkspacePlan as workspace
import SharedMemoryPlan as bridge
import SharedMemoryApply as tx


class RemoveTests(InstallTests):
    def remove(self, **kw):
        return workspace.remove_b_fixture(self.install, self.adapter, writers_closed=True, **kw)

    def test_default_b_removal_preserves_all_data_a_memory_routing(self):
        before = self.bytes_snapshot()
        self.install_fixture()
        b_file = Path(self.profiles['B']['dataDir']) / 'fixture-session'
        b_file.write_bytes(b'B_DATA_RETAINED')
        result = self.remove()
        self.assertTrue(result['b_data_retained'])
        self.assertFalse(result['official_package_removal'])
        for path, raw in before.items():
            self.assertEqual(Path(path).read_bytes(), raw)
        self.assertTrue(b_file.exists())
        self.assertTrue((self.install / 'bin' / 'ClaudeOpenShim.ps1').exists())
        self.assertTrue((self.desktop / 'Claude (A existing).lnk').exists())
        self.assertFalse((self.desktop / 'Claude (B added).lnk').exists())
        self.assertEqual(set(json.loads((self.install / 'bin' / 'profiles.json').read_bytes())['profiles']), {'A'})
        self.assertEqual(self.remove()['status'], 'B_ALREADY_REMOVED_FIXTURE')

    def test_explicit_b_data_deletion_keeps_memory_a(self):
        self.install_fixture()
        (Path(self.profiles['B']['configDir']) / 'fixture-data').write_bytes(b'OWNED_B')
        result = self.remove(delete_b_data=True)
        self.assertFalse(result['b_data_retained'])
        self.assertFalse(Path(self.profiles['B']['configDir']).exists())
        self.assertTrue((self.memory / 'MEMORY.md').exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.data.exists())

    def test_b_root_replaced_by_alias_refused_before_change(self):
        self.install_fixture()
        b_root = Path(self.profiles['B']['configDir'])
        b_root.rmdir()
        b_root.symlink_to(self.config, target_is_directory=True)
        before = (self.install / 'bin' / 'profiles.json').read_bytes()
        with self.assertRaises(bridge.BridgeError):
            self.remove(delete_b_data=True)
        self.assertEqual((self.install / 'bin' / 'profiles.json').read_bytes(), before)
        self.assertTrue(self.config.exists())

    def test_held_runtime_lock_not_deleted(self):
        self.install_fixture()
        lock = self.install / 'bin' / 'route.lock'
        with tx.locked(lock):
            with self.assertRaises(bridge.BridgeError):
                self.remove()
            self.assertTrue(lock.exists())
        self.assertTrue((self.desktop / 'Claude (B added).lnk').exists())

    def test_released_unowned_lock_requires_review(self):
        self.install_fixture()
        lock = self.install / 'bin' / 'route.lock'
        lock.write_bytes(b'0')
        with self.assertRaises(bridge.BridgeError):
            self.remove()
        self.assertTrue(lock.exists())

    def test_modified_shortcut_refuses_before_manifest_change(self):
        self.install_fixture()
        shortcut = self.desktop / 'Claude (B added).lnk'
        shortcut.write_bytes(b'UNRELATED_NEW_OWNER')
        before = (self.install / 'bin' / 'profiles.json').read_bytes()
        with self.assertRaises(bridge.BridgeError):
            self.remove()
        self.assertEqual((self.install / 'bin' / 'profiles.json').read_bytes(), before)
        self.assertEqual(shortcut.read_bytes(), b'UNRELATED_NEW_OWNER')

    def test_b_hardlink_refuses_explicit_deletion(self):
        import os
        self.install_fixture()
        os.link(self.config / '.credentials.json', Path(self.profiles['B']['configDir']) / 'alias')
        with self.assertRaises(bridge.BridgeError):
            self.remove(delete_b_data=True)
        self.assertTrue((self.config / '.credentials.json').exists())

    def test_partial_install_refuses_b_removal(self):
        self.adapter.fail_after = 2
        with self.assertRaises(bridge.BridgeError):
            self.install_fixture()
        with self.assertRaises(bridge.BridgeError):
            self.remove()

    def test_router_change_preserved(self):
        self.install_fixture(self.workspace(protocol_change=True, protocol_consent=True))
        self.adapter.protocol = 'UNRELATED_ROUTER'
        with self.assertRaises(bridge.BridgeError):
            self.remove()
        self.assertEqual(self.adapter.protocol, 'UNRELATED_ROUTER')


if __name__ == '__main__':
    unittest.main(defaultTest='RemoveTests')
