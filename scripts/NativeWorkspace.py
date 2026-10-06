"""Native workspace candidate: explicit approval, journals and conservative recovery.

IMPLEMENTED_NOT_TESTED. No auto login/restart, no package uninstall. Checks serialize
cooperating writers; they do not provide CAS against arbitrary external editors.
"""
import json
import os
from pathlib import Path
import shutil
import ctypes

import SharedMemoryPlan as bridge
import SharedMemoryApply as tx
import SharedWorkspacePlan as workspace
import NativeWindowsIO as windows

SCHEMA = 2


def require_approval(approved, writers_closed):
    if os.name != 'nt' or ctypes.sizeof(ctypes.c_void_p) != 8 or approved is not True or writers_closed is not True:
        raise bridge.BridgeError('NATIVE_APPROVAL_AND_CLOSED_WRITERS_REQUIRED')


def seal(value):
    raw = tx.encode(value)
    if len(raw) > bridge.MAX_JSON:
        raise bridge.BridgeError('NATIVE_RECEIPT_LIMIT')
    return {'record': value, 'sha256': bridge.digest(raw)}


def read_sealed(path):
    raw = bridge.read_optional(bridge.safe_path(path))
    if raw is None:
        raise bridge.BridgeError('NATIVE_RECEIPT_REQUIRED')
    envelope = bridge.object_json(raw)
    if set(envelope) != {'record', 'sha256'} or not isinstance(envelope['record'], dict) or \
            envelope != seal(envelope['record']):
        raise bridge.BridgeError('NATIVE_RECEIPT_INTEGRITY')
    return envelope['record'], raw


def specification_hash(path):
    if not path.name.endswith('.workspace.local.json'):
        raise bridge.BridgeError('PRIVATE_SPEC_NAME_REQUIRED')
    raw = bridge.read_optional(bridge.safe_path(path))
    if raw is None:
        raise bridge.BridgeError('SPEC_REQUIRED')
    return bridge.digest(raw)


def prepare(plan, spec):
    workspace.revalidate_workspace(plan)
    before = windows.registry_snapshot() if plan.protocol_change else None
    if plan.protocol_change and (plan.protocol_before is not None or not windows.empty_registry(before)):
        raise bridge.BridgeError('EXISTING_ROUTER_NOT_ADOPTED')
    record = {'schema': SCHEMA, 'kind': 'native_approval_preview', 'workspace': plan.private_preview(),
              'specification_sha256': specification_hash(spec),
              'workspace_identities': plan.snapshots,
              'memory_identities': [p.roots_snapshot for p in plan.memory_plans],
              'memory_inventory': [p.memory_snapshot for p in plan.memory_plans],
              'scope_hashes': [[(str(path), bridge.digest(raw)) for path, raw in p.snapshots]
                               for p in plan.memory_plans],
              'registry_before': before,
              'registry_after': windows.desired_registry(plan.install) if plan.protocol_change else None}
    # Roundtrip tuple/Path entries to an immutable JSON representation without settings contents.
    record = json.loads(json.dumps(record, default=str))
    return seal(record)


def save_preview(path, capsule, plan, spec):
    path = bridge.safe_path(path)
    protected = [plan.install, plan.desktop, spec]
    for memory in plan.memory_plans:
        protected += [memory.project, memory.memory, *(p for role in memory.profiles.values() for p in role.values())]
    if not path.name.endswith('.native.local.json') or any(bridge.overlap(path, root) for root in protected):
        raise bridge.BridgeError('NATIVE_PREVIEW_OUTPUT_PROTECTED')
    tx.create_once(path, tx.encode(capsule))


def approval(path):
    if not path.name.endswith('.native.local.json'):
        raise bridge.BridgeError('NATIVE_PREVIEW_NAME_REQUIRED')
    record, _ = read_sealed(path)
    fields = {'schema', 'kind', 'workspace', 'specification_sha256', 'workspace_identities', 'memory_identities', 'memory_inventory',
              'scope_hashes', 'registry_before', 'registry_after'}
    if set(record) != fields or record['schema'] != SCHEMA or record['kind'] != 'native_approval_preview':
        raise bridge.BridgeError('NATIVE_PREVIEW_SCHEMA')
    return record


def persist(path, record):
    tx.replace_checked(path, tx.encode(seal(record)), bridge.read_optional(path))


def record_path(install):
    return bridge.safe_path(install, directory=True) / 'native-ownership.json'


def load(install):
    record, _ = read_sealed(record_path(install))
    fields = {'schema', 'kind', 'phase', 'install', 'install_identity', 'approval_sha256', 'protected',
              'protected_identities', 'approved_layout', 'b_roots', 'directories', 'files', 'projects', 'registry_before',
              'registry_after', 'registry_phase'}
    if set(record) != fields or record['schema'] != SCHEMA or record['kind'] != 'native_workspace' or \
            record['phase'] not in ('installing', 'installed', 'removing_b', 'b_removed', 'rolling_back', 'rolled_back'):
        raise bridge.BridgeError('NATIVE_OWNERSHIP_SCHEMA')
    if str(install) != record['install'] or bridge.identity(install) != record['install_identity']:
        raise bridge.BridgeError('NATIVE_INSTALL_IDENTITY_CHANGED')
    layout = record['approved_layout']
    if layout['install'] != str(install) or set(layout['profiles']) != {'A', 'B'}:
        raise bridge.BridgeError('NATIVE_APPROVED_LAYOUT_CHANGED')
    expected_protected = [p['project'] for p in layout['memory']] + [p['memory'] for p in layout['memory']]
    expected_protected += [layout['profiles']['A'][key] for key in ('dataDir', 'configDir')]
    if record['protected'] != expected_protected or record['b_roots'] != [layout['profiles']['B'][key]
            for key in ('dataDir', 'configDir')]:
        raise bridge.BridgeError('NATIVE_APPROVED_LAYOUT_CHANGED')
    if record['registry_after'] is not None and (not windows.empty_registry(record['registry_before']) or
            record['registry_after'] != windows.desired_registry(install)):
        raise bridge.BridgeError('NATIVE_APPROVED_REGISTRY_CHANGED')
    if record['registry_phase'] not in ('not_applied', 'applying', 'applied', 'restoring', 'restored') or \
            (record['registry_after'] is None and record['registry_phase'] != 'not_applied'):
        raise bridge.BridgeError('NATIVE_REGISTRY_PHASE_INVALID')
    protected = [bridge.safe_path(path, directory=True) for path in record['protected']]
    if [(str(p), bridge.identity(p)) for p in protected] != [tuple(item) for item in record['protected_identities']]:
        raise bridge.BridgeError('NATIVE_PROTECTED_ROOT_CHANGED')
    b_roots = [bridge.safe_path(p) for p in record['b_roots']]
    if len(b_roots) != 2 or any(bridge.overlap(install, p) for p in b_roots) or \
            any(bridge.overlap(p, root) for p in [install, *b_roots] for root in protected) or \
            bridge.overlap(b_roots[0], b_roots[1]):
        raise bridge.BridgeError('NATIVE_OWNERSHIP_ROOT_COLLISION')
    approved_projects = {item['project'] for item in layout['memory']}
    if len({item['project'] for item in record['projects']}) != len(record['projects']) or any(
            set(item) != {'project', 'changed', 'phase'} or item['project'] not in approved_projects or
            type(item['changed']) is not bool or item['phase'] not in ('prepared', 'applied', 'restored')
            for item in record['projects']):
        raise bridge.BridgeError('NATIVE_PROJECT_RECEIPT_INVALID')
    for entries in (record['directories'], record['files']):
        if len({item['path'] for item in entries}) != len(entries):
            raise bridge.BridgeError('NATIVE_DUPLICATE_OWNERSHIP_PATH')
    for entry in record['directories']:
        path = bridge.safe_path(entry['path'], directory=True)
        if not (str(path) in record['b_roots'] or bridge.identity(path)['canonical'].startswith(
                bridge.identity(install)['canonical'].rstrip('\\') + '\\')) or bridge.identity(path) != entry['identity']:
            raise bridge.BridgeError('NATIVE_OWNED_DIRECTORY_CHANGED')
    for entry in record['files']:
        path = bridge.safe_path(entry['path'])
        allowed = entry['role'] == 'asset' and path == install / 'bin' / path.name and path.name in workspace.ASSETS
        if entry['role'] == 'manifest':
            allowed = path == install / 'bin' / 'profiles.json'
        if entry['role'] in ('shortcut_A', 'shortcut_B'):
            allowed = str(path) == layout['shortcuts'][0 if entry['role'] == 'shortcut_A' else 1]
        if not allowed or any(bridge.overlap(path, root) for root in protected) or \
                bridge.identity(path) != entry['identity'] or bridge.digest(bridge.read_optional(path)) != entry['sha256']:
            raise bridge.BridgeError('NATIVE_OWNED_FILE_CHANGED')
    if record['phase'] in ('installed', 'b_removed', 'removing_b') and \
            sum(entry['role'] == 'manifest' for entry in record['files']) != 1:
        raise bridge.BridgeError('NATIVE_MANIFEST_RECEIPT_REQUIRED')
    return record


def install(plan, capsule_record, spec, *, approved, writers_closed, approve_protocol=False):
    require_approval(approved, writers_closed)
    if plan.protocol_change and approve_protocol is not True:
        raise bridge.BridgeError('SEPARATE_NATIVE_PROTOCOL_APPROVAL_REQUIRED')
    if prepare(plan, spec)['record'] != capsule_record:
        raise bridge.BridgeError('NATIVE_PREVIEW_STALE')
    protected = [p.project for p in plan.memory_plans] + [p.memory for p in plan.memory_plans]
    protected += list(plan.memory_plans[0].profiles['A'].values())
    b_roots = list(plan.memory_plans[0].profiles['B'].values())
    plan.install.mkdir()
    path = record_path(plan.install)
    record = {'schema': SCHEMA, 'kind': 'native_workspace', 'phase': 'installing',
              'install': str(plan.install), 'install_identity': bridge.identity(plan.install),
              'approval_sha256': bridge.digest(tx.encode(capsule_record)), 'protected': [str(p) for p in protected],
              'protected_identities': [(str(p), bridge.identity(p)) for p in protected],
              'approved_layout': capsule_record['workspace'],
              'b_roots': [str(p) for p in b_roots], 'directories': [], 'files': [], 'projects': [],
              'registry_before': capsule_record['registry_before'], 'registry_after': capsule_record['registry_after'],
              'registry_phase': 'not_applied'}
    tx.create_once(path, tx.encode(seal(record)))
    with tx.locked(plan.install / 'operation.lock'):
        bin_dir = plan.install / 'bin'
        bin_dir.mkdir()
        record['directories'].append({'path': str(bin_dir), 'identity': bridge.identity(bin_dir)})
        persist(path, record)
        # Memory plans revalidate while B roots are still missing. Shared memory is never copied/moved.
        for memory in plan.memory_plans:
            record['projects'].append({'project': str(memory.project), 'changed': memory.changed, 'phase': 'prepared'})
            persist(path, record)
            tx.apply_plan(memory, plan.install / 'memory-transactions', writers_closed=True)
            record['projects'][-1]['phase'] = 'applied'
            persist(path, record)
        for directory in b_roots:
            bridge.safe_path(directory)
            directory.mkdir()
            record['directories'].append({'path': str(directory), 'identity': bridge.identity(directory)})
            persist(path, record)
        files = [(bin_dir / name, raw, 'asset') for name, raw in plan.assets]
        files.append((bin_dir / 'profiles.json', plan.manifest, 'manifest'))
        for target, raw, role in files:
            tx.create_once(target, raw)
            record['files'].append({'path': str(target), 'role': role, 'identity': bridge.identity(target),
                                    'sha256': bridge.digest(raw)})
            persist(path, record)
        for target, specification in plan.shortcuts:
            raw = windows.shortcut_bytes(specification, plan.install)
            tx.create_once(target, raw)
            record['files'].append({'path': str(target), 'role': 'shortcut_' + specification['role'],
                                    'identity': bridge.identity(target), 'sha256': bridge.digest(raw)})
            persist(path, record)
        if plan.protocol_change:
            record['registry_phase'] = 'applying'
            persist(path, record)
            windows.install_registry(record['registry_before'], record['registry_after'])
            record['registry_phase'] = 'applied'
            persist(path, record)
        record['phase'] = 'installed'
        persist(path, record)
    return {'status': 'NATIVE_INSTALLED', 'runtime_qualification': 'NOT_TESTED',
            'default_app_choice': 'MANUAL' if plan.protocol_change else 'UNCHANGED'}


def installed_again(install, capsule_record, spec, *, approved, writers_closed):
    require_approval(approved, writers_closed)
    if specification_hash(spec) != capsule_record['specification_sha256']:
        raise bridge.BridgeError('NATIVE_PREVIEW_STALE')
    with tx.locked(bridge.safe_path(install, directory=True) / 'operation.lock'):
        record = load(install)
        if record['phase'] != 'installed' or record['approval_sha256'] != bridge.digest(tx.encode(capsule_record)):
            raise bridge.BridgeError('NATIVE_REINSTALL_REQUIRES_NEW_PLAN_OR_RECOVERY')
        if record['registry_phase'] == 'applied' and windows.registry_snapshot() != record['registry_after']:
            raise bridge.BridgeError('NATIVE_ROUTER_CHANGED')
        for mapping in record['approved_layout']['memory']:
            settings = bridge.safe_path(Path(mapping['project']) / '.claude' / 'settings.local.json')
            raw = bridge.read_optional(settings)
            if raw is None or bridge.object_json(raw).get(bridge.KEY) != mapping['memory']:
                raise bridge.BridgeError('NATIVE_INSTALLED_MEMORY_SETTING_CHANGED')
    return {'status': 'NATIVE_ALREADY_INSTALLED', 'runtime_qualification': 'NOT_TESTED'}


def quiescent(install):
    if bridge.safe_path(install / 'bin' / 'target.txt').exists():
        raise bridge.BridgeError('NATIVE_ROUTING_INTENT_REQUIRES_DISARM')


def unlink_owned(entry):
    path = bridge.safe_path(entry['path'])
    if bridge.identity(path) != entry['identity'] or bridge.digest(bridge.read_optional(path)) != entry['sha256']:
        raise bridge.BridgeError('NATIVE_OWNED_FILE_CHANGED')
    path.unlink()


def delete_inspection(record):
    directories = [entry for entry in record['directories'] if entry['path'] in record['b_roots']]
    count = 0
    for entry in directories:
        root = bridge.safe_path(entry['path'], directory=True)
        for folder, children, files in os.walk(root, followlinks=False):
            for name in children + files:
                count += 1
                if count > bridge.MAX_ENTRIES:
                    raise bridge.BridgeError('NATIVE_B_DELETE_LIMIT')
                child = bridge.safe_path(Path(folder) / name)
                if child.is_file() and child.stat().st_nlink != 1:
                    raise bridge.BridgeError('NATIVE_B_DELETE_ALIAS')
    return directories


def remove_b(install, *, approved, writers_closed, delete_b_data=False):
    require_approval(approved, writers_closed)
    install = bridge.safe_path(install, directory=True)
    with tx.locked(install / 'operation.lock'):
        record = load(install)
        if record['phase'] not in ('installed', 'b_removed'):
            raise bridge.BridgeError('NATIVE_PARTIAL_OPERATION_REQUIRES_ROLLBACK')
        with windows.routing_guard(install / 'bin' / 'route.lock'):
            quiescent(install)
            if record['registry_phase'] == 'applied' and windows.registry_snapshot() != record['registry_after']:
                raise bridge.BridgeError('NATIVE_ROUTER_CHANGED')
            directories = delete_inspection(record) if delete_b_data is True else []
            if record['phase'] == 'b_removed' and not delete_b_data:
                return {'status': 'NATIVE_B_ALREADY_REMOVED', 'b_data_retained': True}
            record['phase'] = 'removing_b'
            persist(record_path(install), record)
            manifest = next(entry for entry in record['files'] if entry['role'] == 'manifest')
            target = Path(manifest['path'])
            before = bridge.read_optional(target)
            obj = bridge.object_json(before)
            if set(obj['profiles']) not in ({'A', 'B'}, {'A'}):
                raise bridge.BridgeError('NATIVE_MANIFEST_CHANGED')
            obj['profiles'].pop('B', None)
            after = tx.encode(obj)
            tx.replace_checked(target, after, before)
            manifest.update(identity=bridge.identity(target), sha256=bridge.digest(after))
            persist(record_path(install), record)
            for entry in list(record['files']):
                if entry['role'] == 'shortcut_B':
                    unlink_owned(entry)
                    record['files'].remove(entry)
                    persist(record_path(install), record)
            for entry in directories:
                root = bridge.safe_path(entry['path'], directory=True)
                if bridge.identity(root) != entry['identity']:
                    raise bridge.BridgeError('NATIVE_B_ROOT_CHANGED')
                shutil.rmtree(root)  # Explicit deletion of checked receipt-owned B roots only.
                record['directories'].remove(entry)
                persist(record_path(install), record)
            record['phase'] = 'b_removed'
            persist(record_path(install), record)
    return {'status': 'NATIVE_B_REMOVED', 'b_data_retained': not delete_b_data,
            'a_routing_retained': True, 'official_package_removal': False}


def rollback(install, *, approved, writers_closed, approve_protocol=False):
    require_approval(approved, writers_closed)
    install = bridge.safe_path(install, directory=True)
    with tx.locked(install / 'operation.lock'):
        record = load(install)
        if record['phase'] == 'rolled_back':
            return {'status': 'NATIVE_ALREADY_ROLLED_BACK', 'b_data_retained': True}
        active_registry = record['registry_phase'] in ('applying', 'applied', 'restoring')
        if active_registry:
            current = windows.registry_snapshot()
            matches = current == record['registry_after'] if record['registry_phase'] == 'applied' else \
                windows.partial_owned(current, record['registry_after'])
            if approve_protocol is not True or not matches:
                raise bridge.BridgeError('NATIVE_REGISTRY_ROLLBACK_APPROVAL_OR_CONFLICT')
        guard = windows.routing_guard(install / 'bin' / 'route.lock') if (install / 'bin').exists() else tx.locked(install / 'empty-route.lock')
        with guard:
            quiescent(install)
            record['phase'] = 'rolling_back'
            persist(record_path(install), record)
            for project in reversed(record['projects']):
                if project['changed'] and project['phase'] != 'restored':
                    tx.restore(Path(project['project']), install / 'memory-transactions', writers_closed=True)
                    project['phase'] = 'restored'
                    persist(record_path(install), record)
            if active_registry:
                allow_partial = record['registry_phase'] in ('applying', 'restoring')
                record['registry_phase'] = 'restoring'
                persist(record_path(install), record)
                windows.restore_registry(record['registry_before'], record['registry_after'], allow_partial)
                record['registry_phase'] = 'restored'
                persist(record_path(install), record)
            for entry in list(reversed(record['files'])):
                unlink_owned(entry)
                record['files'].remove(entry)
                persist(record_path(install), record)
            # Retain B roots, locks, logs, non-secret journals and unrelated additions.
            record['phase'] = 'rolled_back'
            persist(record_path(install), record)
    return {'status': 'NATIVE_ROLLED_BACK', 'b_data_retained': True, 'official_package_removal': False}
