"""Native Windows fixtures; no Claude runtime or real project mutation."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import SharedMemoryPlan as bridge


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shared-plan-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'Project with spaces'
        self.config = self.root / 'Config A'
        self.data = self.root / 'Data A'
        self.memory = self.config / 'projects' / 'one' / 'memory'
        for path in (self.project, self.memory, self.data):
            path.mkdir(parents=True)
        (self.memory / 'MEMORY.md').write_text('SYNTHETIC_MEMORY_SECRET', encoding='utf-8')
        (self.config / '.credentials.json').write_text('SYNTHETIC_CREDENTIAL', encoding='utf-8')
        self.profiles = {'A': {'dataDir': str(self.data), 'configDir': str(self.config)},
                         'B': {'dataDir': str(self.root / 'New Data B'),
                               'configDir': str(self.root / 'New Config B')}}
        self.settings = self.project / '.claude' / 'settings.local.json'
        self.evidence = bridge.Evidence(True, True, True, True, 'fixture-v1', 'synthetic_fixture')

    def plan(self):
        return bridge.make_plan(self.project, self.memory, self.profiles, self.evidence)

    def write_settings(self, obj, path=None):
        path = path or self.settings
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj), encoding='utf-8')

    def bytes_snapshot(self):
        return {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_preview_no_write_or_creation(self):
        before = self.bytes_snapshot()
        paths = list(self.root.rglob('*'))
        plan = self.plan()
        self.assertTrue(plan.changed)
        self.assertEqual(paths, list(self.root.rglob('*')))
        self.assertEqual(before, self.bytes_snapshot())
        self.assertFalse(plan.summary()['apply_allowed'])

    def test_only_one_key_added_preserving_unrelated(self):
        self.write_settings({'env': {'TOKEN': 'SYNTHETIC_SECRET'}, 'language': 'French'})
        plan = self.plan()
        self.assertEqual(json.loads(plan.after), {**json.loads(plan.before), bridge.KEY: str(self.memory)})
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(plan.private_preview()))
        self.assertNotIn('SYNTHETIC_SECRET', repr(plan))

    def test_existing_matching_setting_preserves_bytes(self):
        self.write_settings({bridge.KEY: str(self.memory)})
        plan = self.plan()
        self.assertFalse(plan.changed)
        self.assertEqual(plan.after, self.settings.read_bytes())

    def test_public_summary_has_no_paths(self):
        result = json.dumps(self.plan().summary())
        self.assertNotIn(str(self.root), result)
        self.assertNotIn('SYNTHETIC', result)
        self.assertIn('NOT_TESTED', result)

    def test_no_credentials_or_memory_content_read(self):
        original = Path.open
        def restricted(path, *args, **kw):
            self.assertEqual(path.name, 'settings.json' if path.parent == self.config else 'settings.local.json')
            self.assertEqual(args, ('rb',))
            return original(path, *args, **kw)
        self.write_settings({'autoMemoryEnabled': True}, self.config / 'settings.json')
        with patch.object(Path, 'open', restricted):
            self.plan()

    def test_evidence_unknowns_refused(self):
        for number in range(4):
            values = [True] * 4
            values[number] = False
            self.evidence = bridge.Evidence(*values, 'v1', 'synthetic_fixture')
            with self.assertRaises(bridge.BridgeError):
                self.plan()

    def test_version_surface_required(self):
        for version, surface in (('', 'synthetic_fixture'), ('v1', 'guessed')):
            self.evidence = bridge.Evidence(True, True, True, True, version, surface)
            with self.assertRaises(bridge.BridgeError):
                self.plan()

    def test_empty_config_never_defaults_home(self):
        self.profiles['A']['configDir'] = ''
        with self.assertRaises(bridge.BridgeError):
            self.plan()

    def test_existing_b_never_adopted(self):
        Path(self.profiles['B']['configDir']).mkdir()
        with self.assertRaises(bridge.BridgeError):
            self.plan()

    def test_profile_alias_and_nesting_refused(self):
        for value in (str(self.config), str(self.config / 'new b')):
            self.profiles['B']['configDir'] = value
            with self.assertRaises(bridge.BridgeError):
                self.plan()

    def test_project_profile_collision(self):
        with self.assertRaises(bridge.BridgeError):
            bridge.make_plan(self.config, self.memory, self.profiles, self.evidence)

    def test_memory_under_project_settings_refused(self):
        memory = self.project / '.claude' / 'memory'
        memory.mkdir(parents=True)
        with self.assertRaises(bridge.BridgeError):
            bridge.make_plan(self.project, memory, self.profiles, self.evidence)

    def test_memory_never_b_root(self):
        self.profiles['B']['configDir'] = str(self.memory / 'New B')
        with self.assertRaises(bridge.BridgeError):
            self.plan()

    def test_memory_never_desktop_data(self):
        with self.assertRaises(bridge.BridgeError):
            bridge.make_plan(self.project, self.data, self.profiles, self.evidence)

    def test_invalid_json_unchanged(self):
        self.settings.parent.mkdir()
        for raw in (b'{bad', b'[]', b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff'):
            self.settings.write_bytes(raw)
            with self.assertRaises(bridge.BridgeError):
                self.plan()
            self.assertEqual(self.settings.read_bytes(), raw)

    def test_large_json_refused(self):
        self.settings.parent.mkdir()
        self.settings.write_bytes(b' ' * (bridge.MAX_JSON + 1))
        with self.assertRaises(bridge.BridgeError):
            self.plan()

    def test_disabled_all_scopes_refused(self):
        for path in (self.config / 'settings.json', self.project / '.claude' / 'settings.json', self.settings):
            self.write_settings({'autoMemoryEnabled': False}, path)
            with self.assertRaises(bridge.BridgeError):
                self.plan()
            path.unlink()

    def test_environment_override_and_policy_refused(self):
        for obj in ({'env': {'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '0'}},
                    {'permissions': {'blockReadsOutsideWorkingDirectories': True}}):
            self.write_settings(obj)
            with self.assertRaises(bridge.BridgeError):
                self.plan()

    def test_directory_override_all_scopes_conflict(self):
        self.write_settings({bridge.KEY: str(self.root / 'different')}, self.config / 'settings.json')
        with self.assertRaises(bridge.BridgeError):
            self.plan()

    def test_nonmemory_entry_refused(self):
        (self.memory / 'settings.json').write_text('{}')
        with self.assertRaises(bridge.BridgeError):
            self.plan()

    def test_nonempty_requires_index_empty_accepted(self):
        (self.memory / 'MEMORY.md').rename(self.memory / 'topic.md')
        with self.assertRaises(bridge.BridgeError):
            self.plan()
        (self.memory / 'topic.md').unlink()
        self.assertTrue(self.plan().changed)

    def test_hardlink_memory_and_settings_refused(self):
        os.link(self.config / '.credentials.json', self.memory / 'note.md')
        with self.assertRaises(bridge.BridgeError):
            self.plan()
        (self.memory / 'note.md').unlink()
        self.write_settings({})
        os.link(self.settings, self.root / 'settings-alias.json')
        with self.assertRaises(bridge.BridgeError):
            self.plan()

    def test_symlink_refused(self):
        link = self.root / 'memory-link'
        link.symlink_to(self.memory, target_is_directory=True)
        with self.assertRaises(bridge.BridgeError):
            bridge.make_plan(self.project, link, self.profiles, self.evidence)

    def test_relative_traversal_ads_and_device_refused(self):
        for path in (Path('relative'), self.project / '..' / 'other',
                     Path(str(self.memory) + ':ads'), Path(r'\\?\C:\example')):
            with self.assertRaises(bridge.BridgeError):
                bridge.safe_path(path)

    def test_two_projects_cannot_share_one_memory(self):
        second = self.root / 'Other Project'
        second.mkdir()
        with self.assertRaises(bridge.BridgeError):
            bridge.make_plans([(self.project, self.memory, self.profiles, self.evidence),
                               (second, self.memory, self.profiles, self.evidence)])

    def test_distinct_project_mapping(self):
        second = self.root / 'Other Project'
        memory = self.config / 'projects' / 'two' / 'memory'
        second.mkdir()
        memory.mkdir(parents=True)
        plans = bridge.make_plans([(self.project, self.memory, self.profiles, self.evidence),
                                   (second, memory, self.profiles, self.evidence)])
        self.assertEqual(len(plans), 2)
        self.assertNotEqual(plans[0].memory, plans[1].memory)

    def test_revalidate_changed_settings(self):
        plan = self.plan()
        self.write_settings({'language': 'French'})
        with self.assertRaises(bridge.BridgeError):
            bridge.revalidate(plan)

    def test_revalidate_changed_memory(self):
        plan = self.plan()
        (self.memory / 'new.md').write_text('fixture')
        with self.assertRaises(bridge.BridgeError):
            bridge.revalidate(plan)

    def test_revalidate_changed_project_identity(self):
        plan = self.plan()
        self.project.rename(self.root / 'moved')
        self.project.mkdir()
        with self.assertRaises(bridge.BridgeError):
            bridge.revalidate(plan)

    def test_memory_entry_limit(self):
        with patch.object(bridge, 'MAX_ENTRIES', 0), self.assertRaises(bridge.BridgeError):
            self.plan()

    def test_invalid_namespace_refused_before_filesystem_probe(self):
        with patch.object(Path, 'lstat', side_effect=AssertionError('UNEXPECTED_PROBE')):
            for value in (r'\\remote\share\file', r'\\?\C:\device', 'relative',
                          str(self.memory) + ':stream', str(self.project / '..' / 'elsewhere')):
                with self.assertRaises(bridge.BridgeError):
                    bridge.safe_path(value)


if __name__ == '__main__':
    unittest.main()
