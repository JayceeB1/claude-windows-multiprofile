"""Keep the Code sessions lists (sidebar records) of two Claude Desktop profiles in step, without a link.

Each Desktop profile keeps one small record per Code session (`local_<uuid>.json`) in
`<dataDir>\\claude-code-sessions\\<account>\\<organisation>`. The app refuses to save a record when that folder is a link
(junction or symlink): "Refusing non-directory at private dir path (symlink/file plant)". A profile whose folder was
junctioned to the other's therefore listed the other's sessions but could not register its own, and every conversation
started there vanished from the list on the next opening. Both folders must be real directories, so the records are copied
instead:

  - a record present on one side only is copied to the other;
  - a record present on both sides and different: the one with the later `lastActivityAt` wins, the other is kept in a backup;
  - a session the app deleted on purpose (`deleted_<id>` marker on either side) is never copied back;
  - a session filed in a Project (Space) the other profile does not have arrives as a plain folder session, since Projects
    are per account (`local-agent-mode-sessions\\<account>\\<org>\\spaces.json`, never linked, never copied here);
  - nothing else is touched (scheduled tasks, markers, transcripts, credentials).

Each app reads its list when it starts, so run this between closings and openings; a window that is already open shows the
new sessions after it is reopened. A legacy junction to the other profile's folder is replaced by a real directory first
(removing a junction never follows it; its content is the other profile's, which is then copied back in).

Preview by default. `--apply --approved` writes. Refuses from an MSIX-packaged process tree, and replaces a legacy junction
only while profile B's Desktop is closed.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

_SPEC = importlib.util.spec_from_file_location('link_shared_config', Path(__file__).with_name('Link-SharedConfig.py'))
links = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(links)

Refused = links.Refused
RECORD_PREFIX, MARKER_PREFIX = 'local_', 'deleted_'


SPACE_KEYS = ('spaceId', 'spaceIdSetBy')       # a Project (Space) is per account: its id means nothing in the other profile


def read_record(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def space_ids(store):
    """Ids of the Projects (Spaces) that exist next to a records folder: <desk>\\local-agent-mode-sessions\\<account>\\<org>."""
    store = Path(store)
    path = store.parents[1] / 'local-agent-mode-sessions' / store.parent.name / store.name / 'spaces.json'
    try:
        found = json.loads(path.read_text(encoding='utf-8')).get('spaces') or []
    except (OSError, ValueError, AttributeError):
        return set()
    return {s.get('id') for s in found if isinstance(s, dict) and s.get('id')}


def comparable(raw):
    """A record without its Project assignment, so a difference that only concerns a Project never triggers a copy."""
    try:
        data = json.loads(raw.decode('utf-8'))
    except ValueError:
        return raw
    for key in SPACE_KEYS:
        data.pop(key, None)
    return json.dumps(data, sort_keys=True).encode('utf-8')


def adapt(raw, destination_spaces):
    """The record as the destination should hold it: a Project the destination does not have becomes a plain folder session."""
    try:
        data = json.loads(raw.decode('utf-8'))
    except ValueError:
        return raw
    if not data.get('spaceId') or data['spaceId'] in destination_spaces:
        return raw
    for key in SPACE_KEYS:
        data.pop(key, None)
    return json.dumps(data, ensure_ascii=False).encode('utf-8')


def listing(folder):
    """{name: record_info} for the record files of a folder, plus the set of deleted ids."""
    records, markers = {}, set()
    if folder is None or not Path(folder).is_dir():
        return records, markers
    for item in Path(folder).iterdir():
        if item.name.startswith(MARKER_PREFIX):
            markers.add(item.name[len(MARKER_PREFIX):])
        elif item.name.startswith(RECORD_PREFIX) and item.name.endswith('.json') and item.is_file():
            data = read_record(item) or {}
            session = str(data.get('sessionId') or item.stem)
            records[item.name] = {
                'path': item, 'activity': data.get('lastActivityAt') or 0, 'mtime': item.stat().st_mtime,
                'ids': {i for i in (data.get('cliSessionId'), session, session[len(RECORD_PREFIX):]) if i},
                'bytes': item.read_bytes()}
    return records, markers


def newer(a, b):
    return (a['activity'], a['mtime']) > (b['activity'], b['mtime'])


def plan(source, target):
    """What a run would do between A's folder `source` and B's folder `target` (both may be None/absent)."""
    legacy_link = target is not None and links.is_link(target)
    a_records, a_markers = listing(source)
    b_records, b_markers = listing(None if legacy_link else target)      # a legacy link only mirrors A's own records
    deleted = a_markers | b_markers
    steps = []
    for name in sorted(set(a_records) | set(b_records)):
        a, b = a_records.get(name), b_records.get(name)
        if deleted & ((a or b)['ids']):
            steps.append({'name': name, 'action': 'skip', 'why': 'deleted_in_app'})
        elif a and not b:
            steps.append({'name': name, 'action': 'copy', 'to': 'B', 'why': 'only_in_A'})
        elif b and not a:
            steps.append({'name': name, 'action': 'copy', 'to': 'A', 'why': 'only_in_B'})
        elif comparable(a['bytes']) != comparable(b['bytes']):
            steps.append({'name': name, 'action': 'copy', 'to': 'B' if newer(a, b) else 'A', 'why': 'newer', 'replaces': True})
    return {'replace_legacy_link': legacy_link, 'steps': steps}


def write_atomic(path, data):
    path = Path(path)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.sync-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def apply(source, target, planned, backup_dir):
    if planned['replace_legacy_link']:
        os.rmdir(target)                          # never follows: removes the junction only
        Path(target).mkdir()
    a_records, _ = listing(source)
    b_records, _ = listing(target)
    done, stamp = [], time.strftime('%Y%m%d-%H%M%S')
    spaces = {'A': space_ids(source), 'B': space_ids(target)}
    # A legacy link made every A record visible in B: re-list B after the swap so the copies below are computed afresh.
    for step in plan(source, target)['steps']:
        if step['action'] != 'copy':
            continue
        name, to = step['name'], step['to']
        origin, destination = (a_records, Path(target)) if to == 'B' else (b_records, Path(source))
        record = origin[name]
        replaced = destination / name
        if step.get('replaces') and replaced.exists():
            kept = Path(backup_dir) / ('sessions-' + stamp) / ('side-' + to)
            kept.mkdir(parents=True, exist_ok=True)
            shutil.copy2(replaced, kept / name)
        write_atomic(replaced, adapt(record['bytes'], spaces[to]))
        done.append({**step})
    return done


def summarize(planned):
    counts = {}
    for step in planned['steps']:
        key = step['action'] if step['action'] == 'skip' else 'copy_to_' + step['to']
        counts[key] = counts.get(key, 0) + 1
    return {'replace_legacy_link': planned['replace_legacy_link'], **counts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--install-dir', type=Path, default=Path.home() / 'ClaudeProfiles')
    parser.add_argument('--from-profile', default='A')
    parser.add_argument('--to-profile', default='B')
    parser.add_argument('--source-desktop', type=Path)
    parser.add_argument('--target-desktop', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approved', action='store_true', help='required with --apply')
    args = parser.parse_args(argv)
    try:
        profiles = links.load_profiles(args.install_dir)
        src_desk = args.source_desktop or profiles.get(args.from_profile.upper(), {}).get('dataDir')
        dst_desk = args.target_desktop or profiles.get(args.to_profile.upper(), {}).get('dataDir')
        if not (src_desk and dst_desk):
            raise Refused('PROFILE_PATHS_UNKNOWN')
        if links.same(src_desk, dst_desk):
            raise Refused('SOURCE_AND_TARGET_ARE_THE_SAME')
        source, why_a = links.session_store(src_desk)
        target, why_b = links.session_store(dst_desk)
        if source is None or target is None:
            raise Refused((why_a or why_b).upper())
        planned = plan(source, target)
        if not args.apply:
            steps = [{k: s[k] for k in ('name', 'action', 'to', 'why') if k in s} for s in planned['steps']]
            print(json.dumps({'status': 'PREVIEW', 'writes_nothing': True, **summarize(planned), 'steps': steps}, indent=2))
            return 0
        if not args.approved:
            raise Refused('APPROVAL_REQUIRED')
        links.require_unpackaged()
        if planned['replace_legacy_link'] and links.profile_running(dst_desk):
            raise Refused('TARGET_PROFILE_RUNNING_CLOSE_IT_FIRST')
        done = apply(source, target, planned, links.journal_paths(args.install_dir)[1])
        print(json.dumps({'status': 'APPLIED', **summarize(planned), 'written': len(done)}, indent=2))
        return 0
    except Refused as error:
        print(json.dumps({'status': 'REFUSED', 'reason': str(error)}))
        return 2
    except Exception as error:  # class only: paths and record contents stay out of the output
        print(json.dumps({'status': 'FAILED', 'error': type(error).__name__}))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
