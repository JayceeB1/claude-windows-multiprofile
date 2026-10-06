"""Selected-key transactions. API only; no action CLI or real-profile invocation.

Tests exercise owned TEMP fixtures. Callers must acknowledge closed writers.
The lock serializes cooperating bridge writers, not arbitrary editors. Replacement
is checked before writing but is not CAS against a non-cooperating concurrent editor.
"""
from contextlib import contextmanager
import json
import msvcrt
import os
from pathlib import Path
import tempfile

import SharedMemoryPlan as bridge


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def create_once(path: Path, value: bytes):
    bridge.safe_path(path)
    try:
        with path.open('xb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise bridge.BridgeError('STATE_ALREADY_EXISTS') from None


@contextmanager
def locked(path: Path):
    bridge.safe_path(path)
    # Keep the lock pathname after release. Never unlink a held lock.
    stream = path.open('a+b')
    acquired = False
    try:
        if os.fstat(stream.fileno()).st_nlink != 1:
            raise bridge.BridgeError('LOCK_ALIAS_REFUSED')
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            acquired = True
        except OSError:
            raise bridge.BridgeError('TRANSACTION_BUSY') from None
        yield
    finally:
        if acquired:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        stream.close()


def replace_checked(path: Path, payload: bytes | None, expected: bytes | None):
    bridge.safe_path(path)
    if bridge.read_optional(path) != expected:
        raise bridge.BridgeError('TARGET_CHANGED')
    if payload is None:
        path.unlink()
        return
    if len(payload) > bridge.MAX_JSON:
        raise bridge.BridgeError('PROPOSED_JSON_LIMIT')
    fd, filename = tempfile.mkstemp(prefix='.bridge-', dir=path.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        bridge.safe_path(path)
        if bridge.read_optional(path) != expected:
            raise bridge.BridgeError('TARGET_CHANGED')
        if expected is None:
            os.link(temporary, path)  # Atomic no-overwrite admission.
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def state_paths(project: Path, state: Path, protected: list[Path]):
    project = bridge.safe_path(project, directory=True)
    state = bridge.safe_path(state)
    if any(bridge.overlap(state, root) for root in [project, *protected]):
        raise bridge.BridgeError('STATE_PROTECTED_COLLISION')
    token = bridge.digest(bridge.identity(project)['canonical'].encode('utf-8'))
    return state / (token + '.json'), state / 'bridge.lock'


def ensure_state(state: Path):
    marker = state / 'owner.json'
    if state.exists():
        if bridge.read_optional(marker) != encode({'schema': 1, 'owner': 'shared-memory-bridge'}):
            raise bridge.BridgeError('STATE_UNOWNED')
    else:
        state.mkdir()  # Parent must already exist; never recursively claim a tree.
        create_once(marker, encode({'schema': 1, 'owner': 'shared-memory-bridge'}))


def apply_plan(plan: bridge.Plan, state: Path, *, writers_closed: bool) -> dict:
    if writers_closed is not True:
        raise bridge.BridgeError('CLOSED_WRITERS_ACK_REQUIRED')
    protected = [plan.memory, *(p for role in plan.profiles.values() for p in role.values())]
    journal, lock = state_paths(plan.project, state, protected)
    bridge.revalidate(plan)
    if not plan.changed:
        return plan.summary()
    ensure_state(state)
    with locked(lock):
        bridge.revalidate(plan)
        if journal.exists():
            raise bridge.BridgeError('EARLIER_TRANSACTION_REQUIRES_RECOVERY')
        obj = bridge.object_json(plan.before) if plan.before is not None else {}
        record = {'schema': 1, 'project': str(plan.project), 'project_identity': bridge.identity(plan.project),
                  'memory': str(plan.memory), 'protected': [str(p) for p in protected],
                  'before_file_existed': plan.before is not None, 'before_present': bridge.KEY in obj,
                  'before_value': obj.get(bridge.KEY), 'written_value': str(plan.memory),
                  'before_sha256': bridge.digest(plan.before), 'after_sha256': bridge.digest(plan.after),
                  'phase': 'prepared', 'target_identity': None}
        # Selected non-secret key only; no settings/env/hooks bytes in state.
        journal_bytes = encode({'record': record, 'sha256': bridge.digest(encode(record))})
        create_once(journal, journal_bytes)
        if not plan.settings.parent.exists():
            plan.settings.parent.mkdir()
        replace_checked(plan.settings, plan.after, plan.before)
        record.update(phase='applied', target_identity=bridge.identity(plan.settings))
        replace_checked(journal, encode({'record': record, 'sha256': bridge.digest(encode(record))}), journal_bytes)
    return {**plan.summary(), 'status': 'APPLIED', 'writes': 1}


def restore(project: Path, state: Path, *, writers_closed: bool) -> dict:
    if writers_closed is not True:
        raise bridge.BridgeError('CLOSED_WRITERS_ACK_REQUIRED')
    journal, lock = state_paths(project, state, [])
    if not state.exists():
        return {'status': 'NO_TRANSACTION', 'memory_deleted': False}
    ensure_state(state)
    with locked(lock):
        raw = bridge.read_optional(journal)
        if raw is None:
            return {'status': 'NO_TRANSACTION', 'memory_deleted': False}
        envelope = bridge.object_json(raw)
        if set(envelope) != {'record', 'sha256'} or not isinstance(envelope['record'], dict) or \
                envelope['sha256'] != bridge.digest(encode(envelope['record'])):
            raise bridge.BridgeError('JOURNAL_INTEGRITY')
        record = envelope['record']
        fields = {'schema', 'project', 'project_identity', 'memory', 'protected', 'before_file_existed',
                  'before_present', 'before_value', 'written_value', 'before_sha256', 'after_sha256',
                  'phase', 'target_identity'}
        if set(record) != fields or record['schema'] != 1 or record['project'] != str(project) or \
                record['project_identity'] != bridge.identity(project) or \
                type(record['before_file_existed']) is not bool or type(record['before_present']) is not bool:
            raise bridge.BridgeError('JOURNAL_IDENTITY_OR_SCHEMA')
        if record['before_present'] and record['before_value'] != record['written_value']:
            raise bridge.BridgeError('JOURNAL_SELECTED_VALUE_INVALID')
        if not isinstance(record['written_value'], str) or record['memory'] != record['written_value'] or \
                (not record['before_present'] and record['before_value'] is not None) or \
                not isinstance(record['protected'], list) or not all(isinstance(p, str) for p in record['protected']):
            raise bridge.BridgeError('JOURNAL_SELECTED_VALUE_INVALID')
        bridge.safe_path(record['memory'], directory=True)
        state_paths(project, state, [Path(p) for p in record['protected']])
        settings = bridge.safe_path(project / '.claude' / 'settings.local.json')
        current = bridge.read_optional(settings)
        if record['phase'] == 'applied':
            if current is None or bridge.identity(settings) != record['target_identity']:
                raise bridge.BridgeError('APPLIED_TARGET_REPLACED_OR_MISSING')
        elif record['phase'] != 'prepared' or record['target_identity'] is not None:
            raise bridge.BridgeError('JOURNAL_PHASE_INVALID')
        obj = bridge.object_json(current) if current is not None else {}
        present, value = bridge.KEY in obj, obj.get(bridge.KEY)
        already_before = present == record['before_present'] and value == record['before_value']
        if record['phase'] == 'prepared' and not already_before:
            raise bridge.BridgeError('INTERRUPTED_APPLY_REQUIRES_REVIEW')
        if not already_before:
            if not present or value != record['written_value']:
                raise bridge.BridgeError('SELECTED_KEY_CHANGED_RECOVERY_REFUSED')
            if record['before_present']:
                obj[bridge.KEY] = record['before_value']
            else:
                del obj[bridge.KEY]
            # Preserve later unrelated keys, rather than replace a whole-file backup.
            payload = None if not obj and not record['before_file_existed'] else encode(obj)
            replace_checked(settings, payload, current)
        journal.unlink()  # Only this transaction record, never memory/profile roots.
    return {'status': 'RESTORED', 'memory_deleted': False, 'profile_deleted': False}
