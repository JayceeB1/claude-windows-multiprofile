"""Additive previews on owned fixtures, no shortcut/registry OS writes."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_shared_memory_plan import PlanTests
import SharedWorkspacePlan as workspace
import SharedMemoryPlan as bridge


class WorkspaceTests(PlanTests):
    def setUp(self):
        super().setUp()
        self.install = self.root / 'Owned Launcher'
        self.desktop = self.root / 'Fixture Desktop'
        self.desktop.mkdir()
        (self.desktop / 'Original Claude.lnk').write_bytes(b'ORIGINAL_A_SHORTCUT')

    def workspace(self, **kw):
        return workspace.make_workspace_plan((self.plan(),), self.install, self.desktop, **kw)

    def test_additive_no_write_and_original_entry_unchanged(self):
        before = self.bytes_snapshot()
        paths = list(self.root.rglob('*'))
        plan = self.workspace()
        self.assertEqual(before, self.bytes_snapshot())
        self.assertEqual(paths, list(self.root.rglob('*')))
        self.assertFalse(plan.protocol_change)
        self.assertFalse(plan.summary()['apply_allowed'])
        profiles = json.loads(plan.manifest)['profiles']
        self.assertEqual(profiles['A']['configDir'], str(self.config))
        self.assertFalse(self.install.exists())

    def test_protocol_separate_consent(self):
        with self.assertRaises(bridge.BridgeError):
            self.workspace(protocol_change=True)
        plan = self.workspace(protocol_change=True, protocol_consent=True, protocol_before='fixture-command')
        self.assertTrue(plan.protocol_change)
        self.assertNotIn('fixture-command', json.dumps(plan.summary()))

    def test_existing_install_never_adopted(self):
        self.install.mkdir()
        with self.assertRaises(bridge.BridgeError):
            self.workspace()

    def test_install_nested_protected_refused(self):
        for root in (self.project, self.memory, self.config, self.data, self.desktop):
            with self.assertRaises(bridge.BridgeError):
                workspace.make_workspace_plan((self.plan(),), root / 'new', self.desktop)

    def test_existing_shortcut_not_overwritten(self):
        (self.desktop / 'Claude (B added).lnk').write_bytes(b'OTHER_OWNER')
        with self.assertRaises(bridge.BridgeError):
            self.workspace()
        self.assertEqual((self.desktop / 'Claude (B added).lnk').read_bytes(), b'OTHER_OWNER')

    def test_public_plan_path_free(self):
        plan = self.workspace()
        self.assertNotIn(str(self.root), json.dumps(plan.summary()))
        self.assertEqual(set(plan.private_preview()['assets_sha256']), set(workspace.ASSETS))

    def test_source_change_invalidates_plan(self):
        source = self.root / 'Assets'
        source.mkdir()
        for name in workspace.ASSETS:
            (source / name).write_bytes(b'fixture-source')
        plan = self.workspace(source=source)
        (source / workspace.ASSETS[0]).write_bytes(b'changed')
        with self.assertRaises(bridge.BridgeError):
            workspace.revalidate_workspace(plan)

    def test_shortcut_created_after_plan_invalidates(self):
        plan = self.workspace()
        plan.shortcuts[0][0].write_bytes(b'NEW_OWNER')
        with self.assertRaises(bridge.BridgeError):
            workspace.revalidate_workspace(plan)

    def test_no_project_mapping_refused(self):
        with self.assertRaises(bridge.BridgeError):
            workspace.make_workspace_plan((), self.install, self.desktop)

    def test_duplicate_mapping_refused(self):
        plan = self.plan()
        with self.assertRaises(bridge.BridgeError):
            workspace.make_workspace_plan((plan, plan), self.install, self.desktop)


if __name__ == '__main__':
    unittest.main(defaultTest='WorkspaceTests')
