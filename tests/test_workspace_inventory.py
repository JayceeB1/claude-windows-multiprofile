"""Owned Windows fixtures; no real account/package/shortcut inspection."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'Inspect-SharedWorkspace.py'
spec = importlib.util.spec_from_file_location('inventory', MODULE)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


@unittest.skipUnless(os.name == 'nt', 'Native Windows identity proof required')
class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='WorkspaceInventory-')
        self.root = Path(self.temp.name).resolve()
        self.data = self.root / 'Existing A Data'
        self.config = self.root / 'Existing A Config'
        self.install = self.root / 'Install'
        for path in (self.data, self.config, self.install / 'bin'):
            path.mkdir(parents=True)
        self.links = []
        self.specs = {'a_data': {'path': str(self.data), 'role': 'protected'},
                      'a_config': {'path': str(self.config), 'role': 'protected'},
                      'install': {'path': str(self.install), 'role': 'protected'}}

    def tearDown(self):
        for link in self.links:
            if link.is_junction():
                os.rmdir(link)  # remove the owned junction itself, never its target
        self.temp.cleanup()

    def junction(self, target):
        link = self.root / ('Alias ' + str(len(self.links)))
        env = dict(os.environ, INV_FIXTURE_LINK=str(link), INV_FIXTURE_TARGET=str(target))
        script = "New-Item -ItemType Junction -Path $env:INV_FIXTURE_LINK -Target $env:INV_FIXTURE_TARGET -ErrorAction Stop | Out-Null"
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                       env=env, capture_output=True, check=True, timeout=15,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        self.links.append(link)
        return link

    def test_preserve_does_not_establish_effective_config(self):
        result = inventory.inventory_roots(self.specs)
        self.assertFalse(result['apply_allowed'])
        self.assertEqual(result['effective_a'], 'unconfirmed')
        self.assertTrue(all(r['state'] == 'preserve' for r in result['roots'].values()))
        self.assertEqual(result['conflicts'], [])

    def test_existing_same_name_never_owned(self):
        candidate = self.root / 'Claude-B'
        candidate.mkdir()
        self.specs['b'] = {'path': str(candidate), 'role': 'addition', 'ownership': 'claimed'}
        result = inventory.inventory_roots(self.specs)
        self.assertEqual(result['roots']['b']['state'], 'existing_unowned')
        self.assertEqual(result['roots']['b']['ownership'], 'unproven')

    def test_future_root_projected_from_actual_parent(self):
        result = inventory.physical_path(str(self.root / 'New B' / 'Config'))
        self.assertTrue(result['projected'])
        self.assertFalse(result['exists'])
        self.assertIsNone(result['file_id'])

    def test_case_alias(self):
        a = inventory.physical_path(str(self.data))
        b = inventory.physical_path(str(self.data).upper())
        self.assertEqual(inventory.relationship(a, b), 'alias')

    def test_junction_alias(self):
        link = self.junction(self.data)
        self.assertEqual(inventory.relationship(inventory.physical_path(str(link)),
                                               inventory.physical_path(str(self.data))), 'alias')

    def test_projected_junction_nesting(self):
        link = self.junction(self.data)
        a = inventory.physical_path(str(link / 'Future B'))
        b = inventory.physical_path(str(self.data))
        self.assertEqual(inventory.relationship(a, b), 'nested')

    def test_hardlink_file_identity(self):
        first = self.root / 'file-one'
        second = self.root / 'file-two'
        first.write_text('SYNTHETIC')
        os.link(first, second)
        self.assertEqual(inventory.relationship(inventory.physical_path(str(first)),
                                               inventory.physical_path(str(second))), 'alias')

    def test_short_name_identity_when_available(self):
        # 8.3 generation may be disabled: fallback paths preserve the identity,
        # while the projected-canonical case below covers equivalent spelling.
        import ctypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        api.GetShortPathNameW.restype = ctypes.c_uint32
        buffer = ctypes.create_unicode_buffer(32768)
        count = api.GetShortPathNameW(str(self.data), buffer, len(buffer))
        self.assertGreater(count, 0)
        if buffer.value.casefold() == str(self.data).casefold():
            self.skipTest('8.3 alias not available on this volume')
        self.assertEqual(inventory.relationship(inventory.physical_path(buffer.value),
                                               inventory.physical_path(str(self.data))), 'alias')

    def test_short_name_equivalence_model(self):
        a = {'canonical': r'c:\long-directory', 'file_id': [1, 2, 3]}
        b = {'canonical': r'c:\long-d~1', 'file_id': [1, 2, 3]}
        self.assertEqual(inventory.relationship(a, b), 'alias')

    def test_nested_root_is_conflict(self):
        self.specs['b'] = {'path': str(self.config / 'Nested'), 'role': 'addition'}
        result = inventory.inventory_roots(self.specs)
        self.assertIn({'roots': ['a_config', 'b'], 'kind': 'nested'}, result['conflicts'])

    def test_sibling_prefix_is_independent(self):
        a = inventory.physical_path(str(self.data))
        b = inventory.physical_path(str(self.root / 'Existing A Data B'))
        self.assertEqual(inventory.relationship(a, b), 'independent')

    def test_refuse_ambiguous_spellings(self):
        for path in ('relative', r'\\server\share', str(self.data) + ':stream',
                     str(self.data) + '.', str(self.data) + ' ',
                     str(self.data / '..' / 'B'), str(self.root / 'CON.txt')):
            with self.subTest(path=path), self.assertRaises(inventory.Unknown):
                inventory.physical_path(path)

    def test_root_file_refused(self):
        file = self.root / 'file'
        file.write_text('SYNTHETIC')
        result = inventory.inventory_roots({'a': {'path': str(file), 'role': 'protected'}})
        self.assertEqual(result['roots']['a']['state'], 'unknown')

    def test_unavailable_identity_refused(self):
        with patch.object(inventory, 'native_identity', side_effect=inventory.Unknown('PRIVATE')):
            result = inventory.inventory_roots(self.specs)
        self.assertTrue(all(r['state'] == 'unknown' for r in result['roots'].values()))
        self.assertFalse(result['apply_allowed'])

    def test_unknown_role_refused(self):
        result = inventory.inventory_roots({'x': {'path': str(self.data), 'role': 'guess'}})
        self.assertEqual(result['roots']['x']['state'], 'unknown')

    def test_manifest_whitelist(self):
        file = self.install / 'bin' / 'profiles.json'
        file.write_text(json.dumps({'secret': 'SYNTHETIC_SECRET', 'profiles': {
            'B': {'dataDir': str(self.data), 'configDir': str(self.config), 'env': 'SYNTHETIC_SECRET'}}}))
        result = inventory.read_manifest(str(self.install))
        self.assertEqual(result['state'], 'readable')
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(result))
        self.assertEqual(set(result['profiles']['B']), {'dataDir', 'configDir'})

    def test_missing_invalid_and_large_manifest(self):
        self.assertEqual(inventory.read_manifest(str(self.install))['state'], 'missing')
        file = self.install / 'bin' / 'profiles.json'
        for text in ('{}', '{', 'x' * 65537):
            file.write_text(text)
            self.assertIn(inventory.read_manifest(str(self.install))['state'], ('invalid', 'unknown'))

    def test_route_state_and_assets_do_not_prove_ownership(self):
        target = self.install / 'bin' / 'target.txt'
        self.assertEqual(inventory.read_route_state(str(self.install))['state'], 'missing')
        target.write_text('{"version":2,"status":"armed","url":"SYNTHETIC_SECRET"}')
        result = inventory.read_route_state(str(self.install))
        self.assertEqual(result['state'], 'armed')
        self.assertEqual(result['consistency'], 'not_qualified')
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(result))
        asset = self.install / 'bin' / 'ClaudeOpenShim.ps1'
        asset.write_text('SYNTHETIC DO NOT EXECUTE')
        result = inventory.installed_assets(str(self.install))
        self.assertTrue(result['ClaudeOpenShim.ps1']['present'])
        self.assertEqual(result['ClaudeOpenShim.ps1']['ownership'], 'unproven')

    def test_private_output_outside_roots_and_create_once(self):
        report = inventory.inventory_roots(self.specs)
        file = self.root / 'receipt.local.md'
        inventory.save_private(str(file), report, report['roots'])
        previous = file.read_bytes()
        with self.assertRaises(inventory.Unknown):
            inventory.save_private(str(file), report, report['roots'])
        self.assertEqual(previous, file.read_bytes())
        for candidate in (self.config / 'secret.local.md', self.root / 'public.json'):
            with self.assertRaises(inventory.Unknown):
                inventory.save_private(str(candidate), report, report['roots'])
            self.assertFalse(candidate.exists())

    def test_private_output_alias_into_protected_root_refused(self):
        link = self.junction(self.data)
        report = inventory.inventory_roots(self.specs)
        with self.assertRaises(inventory.Unknown):
            inventory.save_private(str(link / 'receipt.local.md'), report, report['roots'])
        self.assertFalse((self.data / 'receipt.local.md').exists())

    def test_private_output_unknown_protection_refused(self):
        with self.assertRaises(inventory.Unknown):
            inventory.save_private(str(self.root / 'receipt.local.md'), {}, {'a': {'state': 'unknown'}})

    def test_entry_point_identity_only(self):
        entry = self.root / 'Claude.lnk'
        entry.write_text('SYNTHETIC NO COM EXECUTION')
        self.assertEqual(inventory.inspect_entry(str(entry))['state'], 'observed')
        self.assertEqual(inventory.inspect_entry(None)['state'], 'unknown')

    def test_main_no_secret_reads_no_writes_and_no_private_stdout(self):
        credential = self.config / '.credentials.json'
        credential.write_text('SYNTHETIC_SECRET')
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        args = ['inventory', '--install-dir', str(self.install), '--a-data', str(self.data),
                '--a-config', str(self.config)]
        original = Path.open
        def allowed_open(path, *a, **kw):
            self.assertIn(path, (self.install / 'bin' / 'profiles.json',
                                self.install / 'bin' / 'target.txt'))
            return original(path, *a, **kw)
        output = io.StringIO()
        with patch.object(sys, 'argv', args), patch.object(inventory, 'installed_package',
             return_value={'state': 'unknown', 'packages': []}), \
             patch.object(Path, 'open', allowed_open), contextlib.redirect_stdout(output):
            self.assertEqual(inventory.main(), 0)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertNotIn('SYNTHETIC_SECRET', output.getvalue())
        self.assertFalse(json.loads(output.getvalue())['apply_allowed'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
