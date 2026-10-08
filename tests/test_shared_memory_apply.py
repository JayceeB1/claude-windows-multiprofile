"""Selected-key mutation tests operate exclusively on owned TEMP fixtures."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_shared_memory_plan import PlanTests
import SharedMemoryApply as tx
import SharedMemoryPlan as bridge


class ApplyTests(PlanTests):
    # Inherited planner tests also run against the apply module's dependencies.
    def setUp(self):
        super().setUp()
        self.state = self.root / 'Bridge State'

    def apply(self):
        return tx.apply_plan(self.plan(), self.state, writers_closed=True)

    def restore(self):
        return tx.restore(self.project, self.state, writers_closed=True)

    def test_apply_restore_new_file_preserves_memory_profiles(self):
        before = self.bytes_snapshot()
        self.assertEqual(self.apply()['status'], 'APPLIED')
        self.assertEqual(json.loads(self.settings.read_bytes())[bridge.KEY], str(self.memory))
        self.assertEqual(self.restore()['status'], 'RESTORED')
        self.assertFalse(self.settings.exists())
        for name, raw in before.items():
            self.assertEqual(Path(name).read_bytes(), raw)
        self.assertFalse(Path(self.profiles['B']['configDir']).exists())

    def test_selected_backup_never_contains_settings_secrets(self):
        self.write_settings({'env': {'TOKEN': 'SYNTHETIC_SECRET'}, 'hooks': {'x': 'SYNTHETIC_SECRET'}})
        self.apply()
        for path in self.state.iterdir():
            self.assertNotIn(b'SYNTHETIC_SECRET', path.read_bytes())
        self.restore()
        self.assertEqual(json.loads(self.settings.read_bytes()),
                         {'env': {'TOKEN': 'SYNTHETIC_SECRET'}, 'hooks': {'x': 'SYNTHETIC_SECRET'}})

    def test_no_ack_no_write(self):
        with self.assertRaises(bridge.BridgeError):
            tx.apply_plan(self.plan(), self.state, writers_closed=False)
        with self.assertRaises(bridge.BridgeError):
            tx.restore(self.project, self.state, writers_closed=False)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.settings.exists())

    def test_idempotence_no_rewrite(self):
        self.apply()
        before = self.bytes_snapshot()
        self.assertEqual(self.apply()['status'], 'ALREADY_CONFIGURED')
        self.assertEqual(before, self.bytes_snapshot())
        self.restore()
        self.assertEqual(self.restore()['status'], 'NO_TRANSACTION')

    def test_matching_setting_no_state(self):
        self.write_settings({bridge.KEY: str(self.memory)})
        self.apply()
        self.assertFalse(self.state.exists())

    def test_change_after_plan_refused_before_state(self):
        plan = self.plan()
        self.write_settings({'language': 'French'})
        with self.assertRaises(bridge.BridgeError):
            tx.apply_plan(plan, self.state, writers_closed=True)
        self.assertFalse(self.state.exists())

    def test_unrelated_edit_preserved_on_restore(self):
        self.apply()
        obj = json.loads(self.settings.read_bytes())
        obj['language'] = 'French'
        self.write_settings(obj)
        self.restore()
        self.assertEqual(json.loads(self.settings.read_bytes()), {'language': 'French'})

    def test_selected_edit_refuses_restore(self):
        self.apply()
        self.write_settings({bridge.KEY: str(self.root / 'Different Memory')})
        before = self.settings.read_bytes()
        with self.assertRaises(bridge.BridgeError):
            self.restore()
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertTrue(list(self.state.glob('[0-9a-f]*.json')))

    def test_missing_target_after_apply_refuses(self):
        self.apply()
        self.settings.unlink()
        with self.assertRaises(bridge.BridgeError):
            self.restore()
        self.assertFalse(self.settings.exists())

    def test_replaced_target_same_bytes_refused(self):
        self.apply()
        raw = self.settings.read_bytes()
        self.settings.rename(self.settings.with_suffix('.old'))
        self.settings.write_bytes(raw)
        with self.assertRaises(bridge.BridgeError):
            self.restore()
        self.assertEqual(self.settings.read_bytes(), raw)

    def test_same_byte_settings_replacement_invalidates_plan(self):
        self.write_settings({})
        plan = self.plan()
        raw = self.settings.read_bytes()
        self.settings.rename(self.settings.with_suffix('.old'))
        self.settings.write_bytes(raw)
        with self.assertRaises(bridge.BridgeError):
            tx.apply_plan(plan, self.state, writers_closed=True)
        self.assertFalse(self.state.exists())

    def test_partial_replace_failure_recovers_original(self):
        self.write_settings({'language': 'French'})
        before = self.settings.read_bytes()
        with patch.object(tx.os, 'replace', side_effect=PermissionError('fixture')):
            with self.assertRaises(PermissionError):
                self.apply()
        self.assertEqual(self.settings.read_bytes(), before)
        self.restore()
        self.assertEqual(self.settings.read_bytes(), before)

    def test_state_cannot_nest_protected_roots(self):
        for root in (self.project, self.memory, self.config, self.data,
                     Path(self.profiles['B']['configDir'])):
            with self.assertRaises(bridge.BridgeError):
                tx.apply_plan(self.plan(), root / 'state', writers_closed=True)
        self.assertFalse(self.settings.exists())

    def test_existing_state_unowned_refused(self):
        self.state.mkdir()
        (self.state / 'unrelated').write_text('preserve')
        with self.assertRaises(bridge.BridgeError):
            self.apply()
        self.assertEqual((self.state / 'unrelated').read_text(), 'preserve')

    def test_journal_tamper_refused(self):
        self.apply()
        journal, _ = tx.state_paths(self.project, self.state, [])
        record = json.loads(journal.read_bytes())
        record['record']['before_present'] = True
        journal.write_text(json.dumps(record))
        with self.assertRaises(bridge.BridgeError):
            self.restore()
        self.assertIn(bridge.KEY, json.loads(self.settings.read_bytes()))

    def test_lock_second_writer_refused_no_target_write(self):
        tx.ensure_state(self.state)
        _, lock = tx.state_paths(self.project, self.state, [])
        with tx.locked(lock):
            with self.assertRaises(bridge.BridgeError):
                self.apply()
            self.assertTrue(lock.exists())
        self.assertFalse(self.settings.exists())

    def test_replace_no_overwrite_admission(self):
        target = self.root / 'target.json'
        target.write_bytes(b'{}')
        with self.assertRaises(bridge.BridgeError):
            tx.replace_checked(target, b'{"x":1}', None)
        self.assertEqual(target.read_bytes(), b'{}')

    def test_new_target_admission_failure_retains_journal(self):
        with patch.object(tx.os, 'link', side_effect=PermissionError('fixture')):
            with self.assertRaises(PermissionError):
                self.apply()
        self.assertFalse(self.settings.exists())
        self.assertTrue(list(self.state.glob('[0-9a-f]*.json')))
        self.restore()
        self.assertFalse(self.settings.exists())


if __name__ == '__main__':
    # Avoid discovery of the imported base class as a second standalone suite.
    unittest.main(defaultTest='ApplyTests')
