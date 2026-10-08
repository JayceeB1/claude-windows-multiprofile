"""Offline help/preview/package tests; native mutation actions are refused."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_workspace_plan import WorkspaceTests
import SharedWorkspace as entry
import SharedMemoryPlan as bridge


class EntryTests(WorkspaceTests):
    def setUp(self):
        super().setUp()
        self.spec = self.root / 'fixture.workspace.local.json'
        self.spec.write_text(json.dumps({'schema': 1, 'profiles': self.profiles,
            'projects': [{'project': str(self.project), 'memory': str(self.memory),
                          'evidence': vars(self.evidence)}],
            'install_dir': str(self.install), 'desktop_dir': str(self.desktop),
            'protocol': {'change': False, 'consent': False, 'expected_before': None}}))

    def run_entry(self, args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = entry.main(args)
        return code, output.getvalue()

    def test_preview_offline_no_write_path_free(self):
        before = self.bytes_snapshot()
        code, output = self.run_entry(['preview', '--spec', str(self.spec)])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), output)
        self.assertFalse(json.loads(output)['apply_allowed'])
        self.assertEqual(before, self.bytes_snapshot())

    def test_private_output_exclusive(self):
        report = self.root / 'preview.local.md'
        code, _ = self.run_entry(['preview', '--spec', str(self.spec), '--output', str(report)])
        self.assertEqual(code, 0)
        before = report.read_bytes()
        code, _ = self.run_entry(['preview', '--spec', str(self.spec), '--output', str(report)])
        self.assertEqual(code, 2)
        self.assertEqual(report.read_bytes(), before)
        self.assertNotIn(b'SYNTHETIC_CREDENTIAL', before)

    def test_output_under_project_refused(self):
        report = self.project / 'preview.local.md'
        code, _ = self.run_entry(['preview', '--spec', str(self.spec), '--output', str(report)])
        self.assertEqual(code, 2)
        self.assertFalse(report.exists())

    def test_native_actions_refused_before_spec_read(self):
        for action in ('apply', 'install', 'remove', 'restore'):
            code, output = self.run_entry([action, '--spec', str(self.root / 'SYNTHETIC_SECRET')])
            self.assertEqual(code, 2)
            self.assertNotIn('SYNTHETIC_SECRET', output)
            self.assertEqual(json.loads(output)['reason'], 'NATIVE_ACTION_NOT_ADMITTED')

    def test_help_offline(self):
        code, output = self.run_entry(['help'])
        self.assertEqual(code, 0)
        self.assertIn('Preview', output)

    def test_missing_and_unknown_schema_refused(self):
        for payload in (None, {'schema': 1, 'secret': 'SYNTHETIC_SECRET'}):
            if payload is None:
                self.spec.unlink()
            else:
                self.spec.write_text(json.dumps(payload))
            code, output = self.run_entry(['preview', '--spec', str(self.spec)])
            self.assertEqual(code, 2)
            self.assertNotIn('SYNTHETIC_SECRET', output)

    def test_package_allowlist_hashes_and_no_overwrite(self):
        target = self.root / 'offline.zip'
        code, output = self.run_entry(['package', '--output', str(target)])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), output)
        with zipfile.ZipFile(target) as archive:
            receipt = json.loads(archive.read('PACKAGE.json'))
            self.assertEqual(set(archive.namelist()), set(receipt['sha256']) | {'PACKAGE.json'})
            for name, digest in receipt['sha256'].items():
                self.assertEqual(bridge.digest(archive.read(name)), digest)
                self.assertNotIn('..', name)
            self.assertNotIn('private-spec.json', archive.namelist())
        before = target.read_bytes()
        code, _ = self.run_entry(['package', '--output', str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(target.read_bytes(), before)

    def test_unknown_policy_prevents_plan(self):
        obj = json.loads(self.spec.read_bytes())
        obj['projects'][0]['evidence']['external_policy_reviewed'] = False
        self.spec.write_text(json.dumps(obj))
        code, output = self.run_entry(['preview', '--spec', str(self.spec)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['reason'], 'PROVENANCE_TRUST_OR_POLICY_UNRESOLVED')

    def test_packaged_entry_relative_imports_offline(self):
        target = self.root / 'portable.zip'
        self.assertEqual(self.run_entry(['package', '--output', str(target)])[0], 0)
        destination = self.root / 'Extracted Package'
        with zipfile.ZipFile(target) as archive:
            # Generated allowlist package; validate every name before extraction.
            allowed = {'scripts/' + name for name in entry.PACKAGE_FILES} | set(entry.PACKAGE_DOCS) | {'PACKAGE.json'}
            self.assertEqual(set(archive.namelist()), allowed)
            for name in archive.namelist():
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))
        result = subprocess.run([sys.executable, '-B', str(destination / 'scripts' / 'SharedWorkspace.py'), 'help'],
                                cwd=self.root, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'Preview', result.stdout)

    def test_credential_named_input_refused_before_read(self):
        from unittest.mock import patch
        with patch.object(bridge, 'read_optional', side_effect=AssertionError('SECRET_READ')):
            code, output = self.run_entry(['preview', '--spec', str(self.config / '.credentials.json')])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['reason'], 'PRIVATE_SPEC_NAME_REQUIRED')


if __name__ == '__main__':
    unittest.main(defaultTest='EntryTests')
