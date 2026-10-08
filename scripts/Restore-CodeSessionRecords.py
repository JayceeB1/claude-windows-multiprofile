#!/usr/bin/env python3
"""Restore the sidebar records of Claude Desktop Code sessions whose transcript is still on disk.

The Code tab lists sessions from small records (``local_<uuid>.json``) kept in
``<dataDir>\\claude-code-sessions\\<account>\\<organisation>``. The conversation itself lives in a transcript
(``~/.claude/projects/<project>/<cliSessionId>.jsonl``). When a record is missing the transcript is intact but the session
no longer shows up, in Claude or in Claude B (B's folder is a junction to A's).

This tool lists the Desktop transcripts that have no record and, only with --apply, writes a new record for the selected
ones. It never overwrites or deletes anything, never touches a transcript, and skips sessions that were deleted from the
app (``deleted_<id>`` marker). Run it from a normal shell, with both Claude windows closed: a process started from inside
the Claude app is packaged and refused (its writes would be redirected to a private store).

  python scripts/Restore-CodeSessionRecords.py                       # list candidates (preview)
  python scripts/Restore-CodeSessionRecords.py --match leitmotif     # preview what would be written
  python scripts/Restore-CodeSessionRecords.py --match leitmotif --apply
"""
import argparse
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SESSIONS_DIR = 'claude-code-sessions'
# Fields every record carries; identity and history come from the transcript, settings from the newest record.
INHERITED = ('model', 'effort', 'permissionMode', 'enabledMcpTools', 'remoteMcpServersConfig', 'alwaysAllowedReasons',
             'sessionPermissionUpdates', 'classifierSummaryEnabled', 'chromePermissionMode')


def records_folder(data_dir):
    base = os.path.join(data_dir, SESSIONS_DIR)
    folders = [p for acct in glob.glob(os.path.join(base, '*')) for p in glob.glob(os.path.join(acct, '*'))
               if os.path.isdir(p)]
    if len(folders) != 1:
        sys.exit('REFUSED: expected one <account>/<organisation> folder under %s, found %d' % (base, len(folders)))
    return folders[0]


def read_json(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def known_ids(folder):
    """cliSessionIds already listed, plus the ids the app deleted on purpose."""
    listed, template = set(), None
    newest = 0
    for path in glob.glob(os.path.join(folder, 'local_*.json')):
        record = read_json(path)
        if not record:
            continue
        listed.add(record.get('cliSessionId'))
        listed.update(record.get('priorCliSessionIds') or [])
        if record.get('lastActivityAt', 0) >= newest:
            newest, template = record.get('lastActivityAt', 0), record
    deleted = {os.path.basename(p)[len('deleted_'):] for p in glob.glob(os.path.join(folder, 'deleted_*'))}
    return listed, deleted, template


def summarize(path):
    """What the record needs from a transcript, or None when it is not a Desktop conversation."""
    info = {'entrypoint': None, 'first': None, 'last': None, 'cwd_first': None, 'cwd_last': None, 'relocated': None,
            'title': None, 'model': None, 'turns': 0}
    with open(path, encoding='utf-8', errors='replace') as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            info['entrypoint'] = info['entrypoint'] or item.get('entrypoint')
            stamp = item.get('timestamp')
            if stamp:
                info['first'] = info['first'] or stamp
                info['last'] = stamp
            if item.get('cwd'):
                info['cwd_first'] = info['cwd_first'] or item['cwd']
                info['cwd_last'] = item['cwd']
            kind = item.get('type')
            if kind == 'relocated':
                info['relocated'] = item.get('relocatedCwd')
            elif kind == 'custom-title':
                info['title'] = item.get('customTitle')
            elif kind == 'assistant' and not item.get('isSidechain'):
                info['model'] = (item.get('message') or {}).get('model') or info['model']
            elif kind == 'user' and not item.get('isSidechain') and not item.get('isMeta'):
                content = (item.get('message') or {}).get('content')
                if isinstance(content, list):
                    content = ' '.join(p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text')
                if isinstance(content, str) and content.strip() and not content.lstrip().startswith('<'):
                    info['turns'] += 1
    return info if info['entrypoint'] == 'claude-desktop' else None


def epoch_ms(stamp):
    """ISO-8601 UTC stamp ('2026-10-08T16:27:01.223Z') to epoch milliseconds."""
    if not stamp:
        return 0
    moment = datetime.datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    return int(moment.timestamp() * 1000)


def build_record(cli_id, info, template):
    record = {'sessionId': 'local_' + cli_id, 'cliSessionId': cli_id}
    record['cwd'] = info['relocated'] or info['cwd_last'] or info['cwd_first']
    record['originCwd'] = info['cwd_first'] or record['cwd']
    record['createdAt'] = epoch_ms(info['first'])
    record['lastActivityAt'] = epoch_ms(info['last'])
    record['isArchived'] = False
    if info['title']:
        record['title'], record['titleSource'] = info['title'], 'user'
    record['completedTurns'] = info['turns']
    for key in INHERITED:
        if template and key in template:
            record[key] = template[key]
    record['model'] = info['model'] or record.get('model')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--data-dir', default=os.path.join(os.environ.get('APPDATA', ''), 'Claude'),
                        help="Desktop data dir holding claude-code-sessions (default: Claude's)")
    parser.add_argument('--claude-dir', default=os.path.join(os.path.expanduser('~'), '.claude'),
                        help='Claude Code config dir holding projects (default: ~/.claude)')
    parser.add_argument('--match', help='only transcripts whose project folder, title or id contains this text')
    parser.add_argument('--untitled', action='store_true', help='also list sessions that have no title')
    parser.add_argument('--apply', action='store_true', help='write the records (default: preview only)')
    args = parser.parse_args()

    folder = records_folder(args.data_dir)
    listed, deleted, template = known_ids(folder)
    needle = (args.match or '').lower()
    picked = []
    for path in sorted(glob.glob(os.path.join(args.claude_dir, 'projects', '*', '*.jsonl'))):
        cli_id = os.path.basename(path)[:-len('.jsonl')]
        project = os.path.basename(os.path.dirname(path))
        if cli_id in listed or cli_id in deleted or '-Temp-' in project:
            continue
        info = summarize(path)
        if not info or not info['first'] or (not info['title'] and not args.untitled):
            continue
        if needle and needle not in (project + ' ' + (info['title'] or '') + ' ' + cli_id).lower():
            continue
        picked.append((cli_id, project, info))

    print('records folder: %s' % folder)
    print('%d session(s) have a transcript but no record%s' % (len(picked), '' if args.match else ' (use --match to select)'))
    for cli_id, project, info in picked:
        print('  %s  %-30s  %s' % (cli_id[:8], (info['title'] or '(untitled)')[:30], info['relocated'] or info['cwd_last']))
    if not args.apply or not picked:
        if picked and args.match:
            print('Preview only. Add --apply to write %d record(s).' % len(picked))
        return 0
    if not args.match:
        sys.exit('REFUSED: --apply needs --match, so only the sessions you name are restored')

    import NativeWindowsIO
    try:
        NativeWindowsIO.require_unpackaged_process()
    except Exception as error:                                        # BridgeError: started from inside the Claude app
        sys.exit('REFUSED (%s): run this from a normal PowerShell window, not from inside Claude.' % error)
    for cli_id, _project, info in picked:
        target = os.path.join(folder, 'local_%s.json' % cli_id)
        with open(target, 'x', encoding='utf-8') as handle:        # exclusive create: never overwrites
            json.dump(build_record(cli_id, info, template), handle, ensure_ascii=False)
        print('written: %s' % target)
    print('Reopen Claude and Claude B: the sessions appear under their project.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
