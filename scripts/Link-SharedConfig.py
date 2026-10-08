"""Share selected Claude config between two profiles with links; never identity or credentials.

Directory junctions (no admin) and file symlinks (Windows Developer Mode) point profile B's
config at profile A's, so both Desktop windows see the same skills, agents, plugins, mods,
project memory, global instructions, settings and Desktop MCP configuration. The Code sessions list (the sidebar) is NOT
linked, because the app refuses to save into a linked folder: see SessionRecordSync.py. Identity and
credentials (`.credentials.json`, `.claude.json`, `config.json`, remote/policy files) are never
linked or copied; user-scope MCP servers are copied once into B's `.claude.json`.

Preview by default. `--apply --approved` writes; `--rollback --approved` restores the recorded
previous state. Existing non-empty targets are refused, never merged. Differing files are only
replaced with `--replace-files`, after a recorded backup. Refuses from an MSIX-packaged process
tree and while profile B's Desktop is running. Removal of a link never follows it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

import _winapi

# (kind, name): relative to the profile's Code config dir, or to its Desktop data dir.
CONFIG_ITEMS = [('dir', n) for n in ('agents', 'dev-mods', 'mods', 'plugins', 'projects', 'skills')] + \
               [('file', n) for n in ('CLAUDE.md', 'settings.json', 'keybindings.json')]
DESKTOP_ITEMS = [('file', 'claude_desktop_config.json')]
# Identity, credentials and account-bound state: never linked, never copied.
NEVER = {'.credentials.json', '.claude.json', 'config.json', 'remote-settings.json', 'policy-limits.json',
         'policy-limits.json.stamp.json', 'mcp-needs-auth-cache.json', 'ant-did', 'ant-device-registry.json',
         'ccd-ids.json', 'buddy-tokens.json', 'Local State', 'Preferences', 'Network', 'Cookies'}
assert not NEVER & {name for _, name in CONFIG_ITEMS + DESKTOP_ITEMS}


class Refused(Exception):
    pass


def is_link(path):
    p = Path(path)
    return p.is_symlink() or os.path.isjunction(p)


def link_target(path):
    p = Path(path)
    if p.is_symlink():
        return os.readlink(p)
    return os.path.realpath(p) if os.path.isjunction(p) else None


def same(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_unpackaged():
    scripts = str(Path(__file__).resolve().parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import NativeWindowsIO
    try:
        NativeWindowsIO.require_unpackaged_process()
    except Exception as error:  # BridgeError carries a closed reason code
        raise Refused(str(error) if re.fullmatch('[A-Z_]+', str(error)) else 'PACKAGE_CONTEXT_UNDETERMINED') from error


def profile_running(data_dir):
    """True when profile's main Claude Desktop process is alive; fail closed when it cannot be told."""
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " \
             "Get-CimInstance Win32_Process -Filter \"Name='Claude.exe'\" | ForEach-Object { $_.CommandLine }"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8', timeout=60,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise Refused('RUNNING_CHECK_FAILED')
    wanted = os.path.normcase(str(data_dir)).rstrip('\\/')
    for line in result.stdout.splitlines():
        if re.search(r'(^|\s)--type=', line):
            continue
        for m in re.finditer(r'--user-data-dir=(?:"([^"]*)"|(\S+))', line):
            value = os.path.normcase(m.group(1) or m.group(2)).rstrip('\\/')
            if value == wanted:
                return True
    return False


def classify(kind, source, target, replace_files):
    """Return (action, previous) for one item; action in link|already|skip|refuse:<code>."""
    if not os.path.lexists(source):
        return 'skip', 'source_missing'
    if is_link(source) is False and kind == 'file' and Path(source).is_dir():
        return 'refuse:SOURCE_KIND_MISMATCH', None
    if os.path.lexists(target):
        if is_link(target):
            return ('already', 'linked') if same(target, source) else ('refuse:TARGET_LINKS_ELSEWHERE', None)
        if kind == 'dir':
            if Path(target).is_dir() and not any(Path(target).iterdir()):
                return 'link', 'empty_dir'
            return 'refuse:TARGET_DIRECTORY_NOT_EMPTY', None
        if Path(target).is_file():
            if replace_files:
                return 'link', 'file_backup'
            return 'refuse:TARGET_FILE_EXISTS_USE_REPLACE_FILES', None
        return 'refuse:TARGET_KIND_MISMATCH', None
    return 'link', 'absent'


SESSIONS_DIR = 'claude-code-sessions'


def session_store(data_dir):
    """The single <account>/<organisation> folder of a Desktop profile's Code sessions, or (None, reason)."""
    root = Path(data_dir) / SESSIONS_DIR
    if not root.is_dir():
        return None, 'no_session_store'
    pairs = [org for account in sorted(p for p in root.iterdir() if p.is_dir())
             for org in sorted(p for p in account.iterdir() if p.is_dir())]
    if not pairs:
        return None, 'no_account_folder'
    if len(pairs) > 1:
        return None, 'several_accounts_or_organisations'
    return pairs[0], None


def sessions_entry(src_desk, dst_desk):
    """The Code sessions list is never linked: the app refuses to save a record into a linked folder, so a linked profile
    lists the other's sessions but loses its own. SessionRecordSync.py copies the records instead."""
    source, reason_a = session_store(src_desk)
    target, reason_b = session_store(dst_desk)
    base = {'role': 'sessions', 'kind': 'dir', 'name': SESSIONS_DIR,
            'source': str(source or Path(src_desk) / SESSIONS_DIR), 'target': str(target or Path(dst_desk) / SESSIONS_DIR)}
    if source is None or target is None:
        return {**base, 'action': 'skip', 'previous': reason_a or reason_b}
    if is_link(target):
        return {**base, 'action': 'skip', 'previous': 'legacy_junction_run_SessionRecordSync'}
    return {**base, 'action': 'skip', 'previous': 'copied_by_SessionRecordSync'}


def build_plan(src_cfg, dst_cfg, src_desk, dst_desk, replace_files):
    plan = []
    for root_src, root_dst, items, role in ((src_cfg, dst_cfg, CONFIG_ITEMS, 'config'),
                                            (src_desk, dst_desk, DESKTOP_ITEMS, 'desktop')):
        for kind, name in items:
            source, target = Path(root_src) / name, Path(root_dst) / name
            action, previous = classify(kind, source, target, replace_files)
            plan.append({'role': role, 'kind': kind, 'name': name, 'source': str(source), 'target': str(target),
                         'action': action, 'previous': previous})
    plan.append(sessions_entry(src_desk, dst_desk))
    return plan


def home_dir():
    return Path.home()


def claude_json_candidates(cfg):
    """Where Claude Code keeps user-level state for a config dir.

    With CLAUDE_CONFIG_DIR set it is `<dir>/.claude.json`; for the stock `~/.claude` (variable unset,
    e.g. a natively launched app or the terminal CLI) it is `~/.claude.json`. Both can exist.
    """
    candidates = [Path(cfg) / '.claude.json']
    if same(cfg, home_dir() / '.claude'):
        candidates.append(home_dir() / '.claude.json')
    return candidates


def mcp_plan(src_cfg, dst_cfg, replace_mcp):
    source, servers = None, {}
    for candidate in claude_json_candidates(src_cfg):
        if candidate.is_file():
            found = json.loads(candidate.read_text(encoding='utf-8')).get('mcpServers') or {}
            if found:
                source, servers = candidate, found
                break
    if not source:
        return {'action': 'skip', 'reason': 'no_user_scope_servers', 'servers': []}
    target = claude_json_candidates(dst_cfg)[-1]
    current = None
    if target.is_file():
        current = json.loads(target.read_text(encoding='utf-8')).get('mcpServers') or {}
        if current == servers:
            return {'action': 'already', 'servers': sorted(servers)}
        if current and not replace_mcp:
            return {'action': 'refuse:TARGET_MCP_SERVERS_DIFFER_USE_REPLACE_MCP', 'servers': sorted(servers)}
    return {'action': 'copy', 'servers': sorted(servers), 'target_existed': target.is_file(),
            'previous': current, 'target': str(target), 'source': str(source)}


def write_json_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def make_link(kind, source, target):
    if kind == 'dir':
        _winapi.CreateJunction(str(source), str(target))
        return
    try:
        os.symlink(source, target)
    except OSError as error:
        raise Refused('SYMLINK_NOT_PERMITTED') from error


def remove_link(kind, target):
    # Never follow: rmdir on a junction removes only the junction; unlink only the symlink.
    if kind == 'dir':
        os.rmdir(target)
    else:
        os.unlink(target)


def journal_paths(install):
    base = Path(install) / 'shared-config'
    return base / 'journal.json', base / 'backups'


def load_journal(install):
    path, _ = journal_paths(install)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def apply(plan, mcp, install, src_cfg, dst_cfg, with_mcp):
    journal_file, backups = journal_paths(install)
    refusals = [e for e in plan if e['action'].startswith('refuse:')] + \
               ([mcp] if mcp['action'].startswith('refuse:') else [])
    if refusals:
        raise Refused(refusals[0]['action'].split(':', 1)[1])
    todo = [e for e in plan if e['action'] == 'link']
    # A later run completes an existing journal (new items, repaired links) instead of starting over.
    journal = load_journal(install) or {'schema': 1, 'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'entries': [],
                                        'mcp': None, 'source_config': str(src_cfg), 'target_config': str(dst_cfg)}
    if any(e['state'] == 'doing' for e in journal['entries']):
        raise Refused('INTERRUPTED_RUN_ROLLBACK_FIRST')
    journal_file.parent.mkdir(parents=True, exist_ok=True)
    backups.mkdir(parents=True, exist_ok=True)
    write_json_atomic(journal_file, journal)
    for entry in todo:
        source, target = Path(entry['source']), Path(entry['target'])
        record = {'kind': entry['kind'], 'source': entry['source'], 'target': entry['target'],
                  'previous': entry['previous'], 'backup': None, 'state': 'doing'}
        journal['entries'].append(record)
        write_json_atomic(journal_file, journal)        # journal first: a crash is recoverable
        target.parent.mkdir(parents=True, exist_ok=True)
        if entry['previous'] == 'empty_dir':
            target.rmdir()
        elif entry['previous'] in ('file_backup', 'dir_backup'):
            backup = backups / (hashlib.sha256(str(target).encode()).hexdigest()[:12] + '-' + target.name)
            shutil.move(str(target), str(backup))
            record['backup'] = str(backup)
        make_link(entry['kind'], source, target)
        record['state'] = 'done'
        write_json_atomic(journal_file, journal)
    if with_mcp and mcp['action'] == 'copy':
        target = Path(mcp['target'])
        data = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else {}
        first = journal.get('mcp')   # keep the very first "previous" so rollback restores the original state
        record = {'target': str(target), 'state': 'doing', 'servers': mcp['servers'],
                  'target_existed': first['target_existed'] if first else mcp['target_existed'],
                  'previous': first['previous'] if first else mcp['previous']}
        journal['mcp'] = record
        write_json_atomic(journal_file, journal)
        source_servers = json.loads(Path(mcp['source']).read_text(encoding='utf-8'))['mcpServers']
        data['mcpServers'] = source_servers
        write_json_atomic(target, data)
        record['state'] = 'done'
        write_json_atomic(journal_file, journal)
    return verify(journal)


def is_legacy_sessions_entry(entry):
    """Journals written before 2026-10-08 hold a sessions junction; it is replaced by SessionRecordSync.py, not verified."""
    return SESSIONS_DIR in Path(entry['target']).parts


def verify(journal):
    problems = []
    for e in journal['entries']:
        if is_legacy_sessions_entry(e):
            continue
        t = Path(e['target'])
        if not is_link(t) or not same(t, e['source']):
            problems.append(e['target'])
        elif e['kind'] == 'dir':
            list(os.scandir(t))
        else:
            Path(t).read_bytes()
    return {'linked': len(journal['entries']), 'problems': problems,
            'mcp_copied': bool(journal['mcp'] and journal['mcp']['state'] == 'done')}


def rollback(install):
    journal_file, _ = journal_paths(install)
    journal = load_journal(install)
    if journal is None:
        raise Refused('NO_JOURNAL')
    notes = []
    mcp = journal.get('mcp')
    if mcp and mcp['state'] in ('doing', 'done'):
        target = Path(mcp['target'])
        if target.is_file():
            data = json.loads(target.read_text(encoding='utf-8'))
            if not mcp['target_existed'] and set(data) <= {'mcpServers'}:
                target.unlink()
            elif mcp['previous'] is None or mcp['previous'] == {}:
                data.pop('mcpServers', None)
                write_json_atomic(target, data)
            else:
                data['mcpServers'] = mcp['previous']
                write_json_atomic(target, data)
            notes.append('mcp_restored')
    for e in reversed(journal['entries']):
        target = Path(e['target'])
        if e['state'] in ('doing', 'done') and is_link(target):
            if not same(target, e['source']):
                notes.append('LEFT_CHANGED:' + e['target'])
                continue
            remove_link(e['kind'], target)
        elif e['state'] == 'done':
            if not is_legacy_sessions_entry(e):
                notes.append('NOT_A_LINK_LEFT:' + e['target'])
            continue
        if e['previous'] == 'empty_dir' and not os.path.lexists(target):
            target.mkdir()
        elif e['previous'] in ('file_backup', 'dir_backup') and e['backup'] and Path(e['backup']).exists() \
                and not os.path.lexists(target):
            shutil.move(e['backup'], str(target))
    journal_file.replace(journal_file.with_name('journal.rolled-back.' + time.strftime('%Y%m%d%H%M%S') + '.json'))
    return {'rolled_back': len(journal['entries']), 'notes': notes}


def load_profiles(install):
    path = Path(install) / 'bin' / 'profiles.json'
    if not path.exists():
        return {}
    return {k.upper(): v for k, v in json.loads(path.read_text(encoding='utf-8'))['profiles'].items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--install-dir', type=Path, default=Path.home() / 'ClaudeProfiles')
    parser.add_argument('--from-profile', default='A')
    parser.add_argument('--to-profile', default='B')
    parser.add_argument('--source-config', type=Path)
    parser.add_argument('--target-config', type=Path)
    parser.add_argument('--source-desktop', type=Path)
    parser.add_argument('--target-desktop', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--approved', action='store_true', help='required with --apply or --rollback')
    parser.add_argument('--replace-files', action='store_true', help='back up and replace differing target files')
    parser.add_argument('--replace-mcp', action='store_true', help='overwrite a different user-scope MCP list in B')
    parser.add_argument('--no-mcp', action='store_true')
    args = parser.parse_args(argv)
    try:
        require_unpackaged()
        profiles = load_profiles(args.install_dir)
        src = profiles.get(args.from_profile.upper(), {})
        dst = profiles.get(args.to_profile.upper(), {})
        src_cfg = args.source_config or src.get('configDir')
        dst_cfg = args.target_config or dst.get('configDir')
        src_desk = args.source_desktop or src.get('dataDir')
        dst_desk = args.target_desktop or dst.get('dataDir')
        if not all((src_cfg, dst_cfg, src_desk, dst_desk)):
            raise Refused('PROFILE_PATHS_UNKNOWN')
        if same(src_cfg, dst_cfg) or same(src_desk, dst_desk):
            raise Refused('SOURCE_AND_TARGET_ARE_THE_SAME')
        if args.rollback:
            if not args.approved:
                raise Refused('APPROVAL_REQUIRED')
            if profile_running(dst_desk):
                raise Refused('TARGET_PROFILE_RUNNING_CLOSE_IT_FIRST')
            result = {'status': 'ROLLED_BACK', **rollback(args.install_dir)}
        else:
            plan = build_plan(src_cfg, dst_cfg, src_desk, dst_desk, args.replace_files)
            mcp = {'action': 'skip', 'reason': 'disabled', 'servers': []} if args.no_mcp else \
                mcp_plan(src_cfg, dst_cfg, args.replace_mcp)
            if not args.apply:
                result = {'status': 'PREVIEW', 'writes_nothing': True,
                          'plan': [{k: e[k] for k in ('role', 'kind', 'name', 'action', 'previous')} for e in plan],
                          'mcp_servers': {'action': mcp['action'], 'servers': mcp['servers']}}
            else:
                if not args.approved:
                    raise Refused('APPROVAL_REQUIRED')
                if profile_running(dst_desk):
                    raise Refused('TARGET_PROFILE_RUNNING_CLOSE_IT_FIRST')
                result = {'status': 'APPLIED', **apply(plan, mcp, args.install_dir, src_cfg, dst_cfg, not args.no_mcp)}
        print(json.dumps(result, indent=2))
        return 0
    except Refused as error:
        print(json.dumps({'status': 'REFUSED', 'reason': str(error)}))
        return 2
    except Exception as error:  # report the class only; paths and contents stay out of the output
        print(json.dumps({'status': 'FAILED', 'error': type(error).__name__}))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
