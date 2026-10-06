"""Shared-config links on owned TEMP trees: real junctions and symlinks, no real profile.

Identity and credentials are never linked or copied; removing a link never touches the source;
refusals leave everything as found.
"""
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'Link-SharedConfig.py'
spec = importlib.util.spec_from_file_location('link_shared_config', SCRIPT)
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


class SharedConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='claude-links-test-'))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        r = self.root
        self.src_cfg, self.dst_cfg = r / 'A' / '.claude', r / 'B' / '.claude-b'
        self.src_desk, self.dst_desk = r / 'A' / 'Roaming' / 'Claude', r / 'B' / 'Roaming' / 'Claude-B'
        self.install = r / 'ClaudeProfiles'
        for d in (self.src_cfg, self.dst_cfg, self.src_desk, self.dst_desk, self.install):
            d.mkdir(parents=True)
        # Source (A) content.
        (self.src_cfg / 'agents').mkdir()
        (self.src_cfg / 'agents' / 'reviewer.md').write_text('agent-A', encoding='utf-8')
        (self.src_cfg / 'projects' / 'proj' / 'memory').mkdir(parents=True)
        (self.src_cfg / 'projects' / 'proj' / 'memory' / 'MEMORY.md').write_text('mem-A', encoding='utf-8')
        real_skills = r / 'A' / 'codex-skills'
        real_skills.mkdir()
        (real_skills / 'skill.md').write_text('skill-A', encoding='utf-8')
        os.symlink(real_skills, self.src_cfg / 'skills', target_is_directory=True)   # chain: B -> A -> real
        (self.src_cfg / 'CLAUDE.md').write_text('rules-A', encoding='utf-8')
        (self.src_cfg / 'settings.json').write_text('{"model":"a"}', encoding='utf-8')
        (self.src_cfg / '.credentials.json').write_text('SECRET_A', encoding='utf-8')
        (self.src_cfg / '.claude.json').write_text(json.dumps(
            {'oauthAccount': {'email': 'a@example.invalid'}, 'mcpServers': {'srv1': {'command': 'x'}, 'srv2': {'url': 'u'}}}),
            encoding='utf-8')
        (self.src_desk / 'claude_desktop_config.json').write_text('{"mcpServers":{"d":{}}}', encoding='utf-8')
        (self.src_desk / 'config.json').write_text('TOKEN_A', encoding='utf-8')
        # Code sessions are stored per <account>/<organisation>; B has its own (empty) folder pair.
        self.sess_a = self.src_desk / 'claude-code-sessions' / 'acct-a' / 'org-a'
        self.sess_b = self.dst_desk / 'claude-code-sessions' / 'acct-b' / 'org-b'
        self.sess_a.mkdir(parents=True)
        self.sess_b.mkdir(parents=True)
        (self.sess_a / 'local_one.json').write_text('{"title":"session-A"}', encoding='utf-8')
        (self.sess_a / 'scheduled-tasks.json').write_text('{"scheduledTasks":[]}', encoding='utf-8')
        (self.sess_b / 'scheduled-tasks.json').write_text('{"scheduledTasks":[],"b":true}', encoding='utf-8')
        self.patches = [patch.object(links, 'require_unpackaged'), patch.object(links, 'profile_running', return_value=False)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def run_main(self, *extra):
        argv = ['--install-dir', str(self.install), '--source-config', str(self.src_cfg), '--target-config', str(self.dst_cfg),
                '--source-desktop', str(self.src_desk), '--target-desktop', str(self.dst_desk), *extra]
        out = io.StringIO()
        with redirect_stdout(out):
            code = links.main(argv)
        return code, json.loads(out.getvalue())

    def snapshot(self, root):
        return sorted((str(p.relative_to(root)), p.is_dir(), links.is_link(p)) for p in Path(root).rglob('*'))

    def test_preview_writes_nothing(self):
        before = (self.snapshot(self.root))
        code, result = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'PREVIEW')
        actions = {(e['role'], e['name']): e['action'] for e in result['plan']}
        self.assertEqual(actions[('config', 'agents')], 'link')
        self.assertEqual(actions[('config', 'keybindings.json')], 'skip')       # source missing
        self.assertEqual(self.snapshot(self.root), before)
        self.assertNotIn('SECRET_A', json.dumps(result))

    def test_apply_requires_approval(self):
        code, result = self.run_main('--apply')
        self.assertEqual((code, result['reason']), (2, 'APPROVAL_REQUIRED'))
        self.assertFalse(links.is_link(self.dst_cfg / 'agents'))

    def test_apply_shares_live_and_never_identity(self):
        code, result = self.run_main('--apply', '--approved', '--replace-files')
        self.assertEqual((code, result['status'], result['problems']), (0, 'APPLIED', []))
        for name in ('agents', 'projects', 'skills'):
            self.assertTrue(links.is_link(self.dst_cfg / name), name)
        self.assertEqual((self.dst_cfg / 'skills' / 'skill.md').read_text(encoding='utf-8'), 'skill-A')   # chain works
        self.assertEqual((self.dst_cfg / 'projects' / 'proj' / 'memory' / 'MEMORY.md').read_text(encoding='utf-8'), 'mem-A')
        # Both directions are live.
        (self.dst_cfg / 'agents' / 'from-b.md').write_text('B-wrote', encoding='utf-8')
        self.assertEqual((self.src_cfg / 'agents' / 'from-b.md').read_text(encoding='utf-8'), 'B-wrote')
        (self.src_cfg / 'projects' / 'proj' / 'memory' / 'MEMORY.md').write_text('mem-A2', encoding='utf-8')
        self.assertEqual((self.dst_cfg / 'projects' / 'proj' / 'memory' / 'MEMORY.md').read_text(encoding='utf-8'), 'mem-A2')
        # In-place edits through a file link propagate.
        self.assertTrue((self.dst_cfg / 'CLAUDE.md').is_symlink())
        (self.dst_cfg / 'CLAUDE.md').write_text('rules-edited', encoding='utf-8')
        self.assertEqual((self.src_cfg / 'CLAUDE.md').read_text(encoding='utf-8'), 'rules-edited')
        # Identity and credentials: never linked, never copied.
        self.assertFalse((self.dst_cfg / '.credentials.json').exists())
        self.assertFalse((self.dst_desk / 'config.json').exists() and links.is_link(self.dst_desk / 'config.json'))
        copied = json.loads((self.dst_cfg / '.claude.json').read_text(encoding='utf-8'))
        self.assertEqual(set(copied), {'mcpServers'})
        self.assertEqual(sorted(copied['mcpServers']), ['srv1', 'srv2'])
        self.assertNotIn('oauthAccount', copied)

    def test_rollback_restores_and_never_touches_source(self):
        (self.dst_cfg / 'mods').mkdir()                     # empty dir: replaced, then restored
        (self.src_cfg / 'mods').mkdir()
        (self.src_cfg / 'mods' / 'm.txt').write_text('mod-A', encoding='utf-8')
        sources_before = self.snapshot(self.src_cfg)
        self.run_main('--apply', '--approved', '--replace-files')
        self.assertTrue(links.is_link(self.dst_cfg / 'mods'))
        code, result = self.run_main('--rollback', '--approved')
        self.assertEqual((code, result['status']), (0, 'ROLLED_BACK'))
        self.assertFalse(links.is_link(self.dst_cfg / 'agents'))
        self.assertFalse((self.dst_cfg / 'agents').exists())
        self.assertTrue((self.dst_cfg / 'mods').is_dir() and not links.is_link(self.dst_cfg / 'mods'))   # empty dir back
        self.assertEqual((self.src_cfg / 'mods' / 'm.txt').read_text(encoding='utf-8'), 'mod-A')
        self.assertEqual((self.src_cfg / 'projects' / 'proj' / 'memory' / 'MEMORY.md').read_text(encoding='utf-8'), 'mem-A')
        self.assertEqual(self.snapshot(self.src_cfg), sources_before)
        self.assertFalse((self.dst_cfg / '.claude.json').exists())    # file we created is removed again

    def test_non_empty_target_directory_is_refused(self):
        (self.dst_cfg / 'agents').mkdir()
        (self.dst_cfg / 'agents' / 'mine.md').write_text('B-own', encoding='utf-8')
        code, result = self.run_main('--apply', '--approved')
        self.assertEqual((code, result['reason']), (2, 'TARGET_DIRECTORY_NOT_EMPTY'))
        self.assertEqual((self.dst_cfg / 'agents' / 'mine.md').read_text(encoding='utf-8'), 'B-own')
        self.assertFalse(links.is_link(self.dst_cfg / 'plugins'))        # nothing else was linked either

    def test_differing_file_needs_replace_files_then_backup_roundtrip(self):
        (self.dst_desk / 'claude_desktop_config.json').write_text('{"b":"own"}', encoding='utf-8')
        code, result = self.run_main('--apply', '--approved')
        self.assertEqual((code, result['reason']), (2, 'TARGET_FILE_EXISTS_USE_REPLACE_FILES'))
        self.assertEqual((self.dst_desk / 'claude_desktop_config.json').read_text(encoding='utf-8'), '{"b":"own"}')
        self.assertEqual(self.run_main('--apply', '--approved', '--replace-files')[0], 0)
        self.assertTrue((self.dst_desk / 'claude_desktop_config.json').is_symlink())
        self.assertEqual((self.dst_desk / 'claude_desktop_config.json').read_text(encoding='utf-8'), '{"mcpServers":{"d":{}}}')
        self.run_main('--rollback', '--approved')
        self.assertEqual((self.dst_desk / 'claude_desktop_config.json').read_text(encoding='utf-8'), '{"b":"own"}')
        self.assertFalse((self.dst_desk / 'claude_desktop_config.json').is_symlink())

    def test_mcp_copy_keeps_target_identity_and_rolls_back(self):
        (self.dst_cfg / '.claude.json').write_text(json.dumps({'oauthAccount': {'email': 'b@example.invalid'}, 'theme': 'x'}),
                                                   encoding='utf-8')
        self.run_main('--apply', '--approved', '--replace-files')
        merged = json.loads((self.dst_cfg / '.claude.json').read_text(encoding='utf-8'))
        self.assertEqual(merged['oauthAccount']['email'], 'b@example.invalid')       # B stays B
        self.assertEqual(sorted(merged['mcpServers']), ['srv1', 'srv2'])
        self.run_main('--rollback', '--approved')
        restored = json.loads((self.dst_cfg / '.claude.json').read_text(encoding='utf-8'))
        self.assertEqual(restored, {'oauthAccount': {'email': 'b@example.invalid'}, 'theme': 'x'})

    def test_code_sessions_of_a_become_visible_in_b_and_roll_back(self):
        code, result = self.run_main('--apply', '--approved', '--replace-files')
        self.assertEqual((code, result['problems']), (0, []))
        self.assertTrue(links.is_link(self.sess_b))
        self.assertEqual((self.sess_b / 'local_one.json').read_text(encoding='utf-8'), '{"title":"session-A"}')
        # A new session created through B lands in the shared store and is visible to A.
        (self.sess_b / 'local_two.json').write_text('{"title":"session-from-B"}', encoding='utf-8')
        self.assertTrue((self.sess_a / 'local_two.json').exists())
        # The account/organisation folders themselves are untouched siblings.
        self.assertTrue(self.sess_b.parent.is_dir() and not links.is_link(self.sess_b.parent))
        code, result = self.run_main('--rollback', '--approved')
        self.assertEqual(code, 0)
        self.assertFalse(links.is_link(self.sess_b))
        self.assertEqual((self.sess_b / 'scheduled-tasks.json').read_text(encoding='utf-8'), '{"scheduledTasks":[],"b":true}')
        self.assertFalse((self.sess_b / 'local_one.json').exists())
        self.assertTrue((self.sess_a / 'local_one.json').exists())            # A's records survive
        self.assertTrue((self.sess_a / 'local_two.json').exists())            # and so does what B added while linked

    def test_b_own_local_sessions_are_never_hidden(self):
        (self.sess_b / 'local_own.json').write_text('{"title":"B-own"}', encoding='utf-8')
        code, result = self.run_main('--apply', '--approved', '--replace-files')
        self.assertEqual((code, result['reason']), (2, 'TARGET_HAS_OWN_SESSIONS'))
        self.assertTrue((self.sess_b / 'local_own.json').exists())
        self.assertFalse(links.is_link(self.dst_cfg / 'agents'))              # nothing else was linked either

    def test_sessions_skip_when_a_store_is_missing_or_ambiguous(self):
        shutil.rmtree(self.dst_desk / 'claude-code-sessions')
        entry = links.sessions_entry(self.src_desk, self.dst_desk)
        self.assertEqual((entry['action'], entry['previous']), ('skip', 'no_session_store'))
        (self.dst_desk / 'claude-code-sessions' / 'acct-b' / 'org-b').mkdir(parents=True)
        (self.dst_desk / 'claude-code-sessions' / 'acct-b' / 'org-b2').mkdir()
        entry = links.sessions_entry(self.src_desk, self.dst_desk)
        self.assertEqual((entry['action'], entry['previous']), ('skip', 'several_accounts_or_organisations'))

    def test_no_sessions_flag_leaves_the_store_alone(self):
        code, result = self.run_main('--apply', '--approved', '--replace-files', '--no-sessions')
        self.assertEqual(code, 0)
        self.assertFalse(links.is_link(self.sess_b))
        self.assertEqual((self.sess_b / 'scheduled-tasks.json').read_text(encoding='utf-8'), '{"scheduledTasks":[],"b":true}')

    def test_stock_source_uses_the_home_claude_json_when_its_own_has_no_servers(self):
        home = self.root / 'home'
        stock = home / '.claude'
        stock.mkdir(parents=True)
        (stock / '.claude.json').write_text(json.dumps({'oauthAccount': {'email': 'a@example.invalid'}}), encoding='utf-8')
        (home / '.claude.json').write_text(json.dumps({'mcpServers': {'home-srv': {'command': 'h'}}, 'userID': 'x'}), encoding='utf-8')
        with patch.object(links, 'home_dir', return_value=home):
            plan = links.mcp_plan(stock, self.dst_cfg, False)
        self.assertEqual((plan['action'], plan['servers']), ('copy', ['home-srv']))
        self.assertEqual(Path(plan['source']), home / '.claude.json')
        self.assertEqual(Path(plan['target']), self.dst_cfg / '.claude.json')

    def test_stock_source_prefers_its_own_file_when_it_has_servers(self):
        home = self.root / 'home2'
        stock = home / '.claude'
        stock.mkdir(parents=True)
        (stock / '.claude.json').write_text(json.dumps({'mcpServers': {'own': {}}}), encoding='utf-8')
        (home / '.claude.json').write_text(json.dumps({'mcpServers': {'home-srv': {}}}), encoding='utf-8')
        with patch.object(links, 'home_dir', return_value=home):
            plan = links.mcp_plan(stock, self.dst_cfg, False)
        self.assertEqual(plan['servers'], ['own'])

    def test_non_stock_source_never_reads_the_home_file(self):
        home = self.root / 'home3'
        home.mkdir()
        (home / '.claude.json').write_text(json.dumps({'mcpServers': {'home-srv': {}}}), encoding='utf-8')
        (self.src_cfg / '.claude.json').write_text(json.dumps({'oauthAccount': {}}), encoding='utf-8')
        with patch.object(links, 'home_dir', return_value=home):
            plan = links.mcp_plan(self.src_cfg, self.dst_cfg, False)
        self.assertEqual(plan['action'], 'skip')

    def test_different_mcp_list_is_refused_without_flag(self):
        (self.dst_cfg / '.claude.json').write_text(json.dumps({'mcpServers': {'other': {}}}), encoding='utf-8')
        code, result = self.run_main('--apply', '--approved')
        self.assertEqual((code, result['reason']), (2, 'TARGET_MCP_SERVERS_DIFFER_USE_REPLACE_MCP'))

    def test_second_apply_is_idempotent_and_keeps_the_first_previous_state(self):
        self.run_main('--apply', '--approved', '--replace-files')
        code, result = self.run_main('--apply', '--approved', '--replace-files')
        self.assertEqual((code, result['status']), (0, 'APPLIED'))
        code, preview = self.run_main()
        self.assertTrue(all(e['action'] in ('already', 'skip') for e in preview['plan']), preview['plan'])
        self.run_main('--rollback', '--approved')
        self.assertFalse((self.dst_cfg / '.claude.json').exists())

    def test_running_target_profile_is_refused(self):
        with patch.object(links, 'profile_running', return_value=True):
            code, result = self.run_main('--apply', '--approved')
        self.assertEqual((code, result['reason']), (2, 'TARGET_PROFILE_RUNNING_CLOSE_IT_FIRST'))
        self.assertFalse(links.is_link(self.dst_cfg / 'agents'))

    def test_packaged_process_is_refused(self):
        import NativeWindowsIO
        self.patches[0].stop()
        try:
            with patch.object(NativeWindowsIO, 'require_unpackaged_process',
                              side_effect=NativeWindowsIO.bridge.BridgeError('PACKAGED_PROCESS_REFUSED')):
                code, result = self.run_main('--apply', '--approved')
        finally:
            self.patches[0].start()
        self.assertEqual((code, result['reason']), (2, 'PACKAGED_PROCESS_REFUSED'))
        self.assertFalse(links.is_link(self.dst_cfg / 'agents'))

    def test_never_list_is_disjoint_from_linked_items(self):
        linked = {name for _, name in links.CONFIG_ITEMS + links.DESKTOP_ITEMS}
        self.assertFalse(links.NEVER & linked)
        for secret in ('.credentials.json', '.claude.json', 'config.json', 'remote-settings.json'):
            self.assertIn(secret, links.NEVER)

    def test_source_equal_target_is_refused(self):
        code, result = self.run_main('--target-config', str(self.src_cfg))
        self.assertEqual((code, result['reason']), (2, 'SOURCE_AND_TARGET_ARE_THE_SAME'))


if __name__ == '__main__':
    unittest.main()
