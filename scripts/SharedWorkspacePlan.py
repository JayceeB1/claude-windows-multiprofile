"""Additive workspace preview. No install, activation or OS registration here."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import os
import tempfile

import SharedMemoryPlan as bridge
import SharedMemoryApply as transactions

ASSETS = ('Launch-Claude.ps1', 'launch.vbs', 'ClaudeOpenShim.ps1',
          'Arm-ClaudeLogin.ps1', 'Test-ClaudeRouting.ps1')


@dataclass(frozen=True)
class WorkspacePlan:
    memory_plans: tuple
    install: Path
    desktop: Path
    source: Path
    assets: tuple = field(repr=False)
    shortcuts: tuple
    manifest: bytes = field(repr=False)
    snapshots: tuple = field(repr=False)
    protocol_change: bool = False
    protocol_before: str | None = field(default=None, repr=False)

    def summary(self):
        return {'status': 'ADDITIVE_PLAN', 'new_profiles': ['B'], 'existing_profiles': ['A'],
                'memory_projects': len(self.memory_plans), 'new_shortcuts': len(self.shortcuts),
                'assets': len(self.assets), 'protocol_change': self.protocol_change,
                'apply_allowed': False, 'runtime_qualification': 'NOT_TESTED',
                'official_package_removal': False}

    def private_preview(self):
        return {**self.summary(), 'install': str(self.install),
                'shortcuts': [str(p) for p, _ in self.shortcuts],
                'assets_sha256': {name: bridge.digest(raw) for name, raw in self.assets},
                'profiles': json.loads(self.manifest)['profiles'],
                'memory': [p.private_preview() for p in self.memory_plans]}


def make_workspace_plan(memory_plans: tuple, install: Path, desktop: Path,
                        source: Path | None = None, *, protocol_change=False,
                        protocol_consent=False, protocol_before=None) -> WorkspacePlan:
    if not memory_plans:
        raise bridge.BridgeError('PROJECT_MAPPING_REQUIRED')
    if type(protocol_change) is not bool or protocol_change and protocol_consent is not True:
        raise bridge.BridgeError('SEPARATE_PROTOCOL_CONSENT_REQUIRED')
    if protocol_before is not None and (not isinstance(protocol_before, str) or
            len(protocol_before) > 4096 or any(c in protocol_before for c in '\r\n\x00')):
        raise bridge.BridgeError('PROTOCOL_SNAPSHOT_INVALID')
    profiles = memory_plans[0].profiles
    protected = [root for profile in profiles.values() for root in profile.values()]
    for plan in memory_plans:
        bridge.revalidate(plan)
        if plan.profiles != profiles:
            raise bridge.BridgeError('PROFILE_MAPPING_MISMATCH')
        protected.extend((plan.project, plan.memory))
    for number, plan in enumerate(memory_plans):
        if any(bridge.overlap(plan.project, prior.project) or bridge.overlap(plan.memory, prior.memory)
               for prior in memory_plans[:number]):
            raise bridge.BridgeError('DISTINCT_PROJECT_MAPPING_REQUIRED')
    install = bridge.safe_path(install)
    desktop = bridge.safe_path(desktop, directory=True)
    if install.exists() or any(bridge.overlap(install, root) for root in [desktop, *protected]) or \
            any(bridge.overlap(desktop, root) for root in protected):
        raise bridge.BridgeError('INSTALL_OR_DESKTOP_COLLISION')
    if not install.parent.is_dir():
        raise bridge.BridgeError('INSTALL_PARENT_REQUIRED')
    source = bridge.safe_path(source or Path(__file__).parent, directory=True)
    assets = []
    for name in ASSETS:
        raw = bridge.read_optional(source / name)
        if raw is None:
            raise bridge.BridgeError('ASSET_UNAVAILABLE')
        assets.append((name, raw))
    shortcuts = []
    for role, label in (('A', 'A existing'), ('B', 'B added')):
        path = bridge.safe_path(desktop / ('Claude (' + label + ').lnk'))
        if path.exists():
            raise bridge.BridgeError('SHORTCUT_ALREADY_EXISTS_UNOWNED')
        shortcuts.append((path, {'script': str(install / 'bin' / 'launch.vbs'),
                                'dataDir': str(profiles[role]['dataDir']),
                                'configDir': str(profiles[role]['configDir']), 'role': role}))
    manifest = (json.dumps({'defaultProfile': 'None', 'generated': 'owned-additive-plan',
                           'profiles': {role: {'dataDir': str(p['dataDir']), 'configDir': str(p['configDir']),
                                              'isDefault': False} for role, p in profiles.items()}},
                          indent=2) + '\n').encode('utf-8')
    watched = [install, desktop, *(p for p, _ in shortcuts), source,
               *(source / name for name in ASSETS)]
    return WorkspacePlan(tuple(memory_plans), install, desktop, source, tuple(assets), tuple(shortcuts), manifest,
                         tuple((p, bridge.identity(p)) for p in watched), protocol_change, protocol_before)


def revalidate_workspace(plan):
    for memory in plan.memory_plans:
        bridge.revalidate(memory)
    for path, before in plan.snapshots:
        if bridge.identity(path) != before:
            raise bridge.BridgeError('WORKSPACE_INPUT_CHANGED')
    for name, raw in plan.assets:
        if bridge.read_optional(plan.source / name) != raw:
            raise bridge.BridgeError('ASSET_CHANGED')


class FixtureWindows:
    """OS double bounded to a TEMP fixture. It cannot touch a real profile/registry."""
    surface = 'synthetic_fixture'

    def __init__(self, root: Path):
        self.root = bridge.safe_path(root, directory=True)
        parent = bridge.identity(Path(tempfile.gettempdir()))['canonical'].rstrip('\\') + '\\'
        if not bridge.identity(root)['canonical'].startswith(parent) or \
                not root.name.startswith('shared-plan-fixture-'):
            raise bridge.BridgeError('OWNED_TEMP_FIXTURE_REQUIRED')
        self.protocol = None
        self.fail_after = None
        self.calls = 0

    def check(self, path):
        path = bridge.safe_path(path)
        root = bridge.identity(self.root)['canonical'].rstrip('\\') + '\\'
        if not bridge.identity(path)['canonical'].startswith(root):
            raise bridge.BridgeError('FIXTURE_TARGET_ESCAPE')
        return path

    def shortcut_bytes(self, specification):
        # This JSON is a double, never a valid native .lnk qualification receipt.
        return transactions.encode({'fixture_shortcut': specification})

    def before_operation(self):
        self.calls += 1
        if self.fail_after is not None and self.calls == self.fail_after:
            raise bridge.BridgeError('INJECTED_FIXTURE_FAILURE')


def receipt_bytes(record):
    return transactions.encode({'record': record, 'sha256': bridge.digest(transactions.encode(record))})


def read_receipt(path):
    raw = bridge.read_optional(path)
    if raw is None:
        raise bridge.BridgeError('OWNERSHIP_RECEIPT_MISSING')
    envelope = bridge.object_json(raw)
    if set(envelope) != {'record', 'sha256'} or not isinstance(envelope['record'], dict) or \
            envelope['sha256'] != bridge.digest(transactions.encode(envelope['record'])):
        raise bridge.BridgeError('OWNERSHIP_RECEIPT_INTEGRITY')
    return envelope['record'], raw


def save_receipt(path, record):
    before = bridge.read_optional(path)
    transactions.replace_checked(path, receipt_bytes(record), before)


def execute_fixture(plan: WorkspacePlan, adapter: FixtureWindows, *, writers_closed: bool):
    """S4c execution qualification ONLY. No native Windows adapter is admitted yet."""
    if writers_closed is not True or type(adapter) is not FixtureWindows:
        raise bridge.BridgeError('FIXTURE_CLOSED_WRITERS_REQUIRED')
    adapter.check(plan.install)
    receipt = plan.install / 'ownership.json'
    if plan.install.exists():
        record, _ = read_receipt(receipt)
        if record.get('phase') != 'installed' or record.get('manifest_sha256') != bridge.digest(plan.manifest):
            raise bridge.BridgeError('INSTALL_RECOVERY_REQUIRED')
        check_owned_record(record, adapter)
        if record['protocol_change'] and adapter.protocol != record['protocol_written']:
            raise bridge.BridgeError('PROTOCOL_CONFLICT')
        return {'status': 'ALREADY_INSTALLED_FIXTURE', 'native_install': 'NOT_RUN'}
    revalidate_workspace(plan)
    protected = [str(p.project) for p in plan.memory_plans] + [str(p.memory) for p in plan.memory_plans]
    protected += [str(p) for p in plan.memory_plans[0].profiles['A'].values()]
    roots_b = list(plan.memory_plans[0].profiles['B'].values())
    targets = [plan.install, plan.install / 'bin', *roots_b, *(p for p, _ in plan.shortcuts)]
    for target in targets:
        adapter.check(target)
    if plan.protocol_change and adapter.protocol != plan.protocol_before:
        raise bridge.BridgeError('PROTOCOL_CHANGED_SINCE_PLAN')
    plan.install.mkdir()
    record = {'schema': 1, 'surface': 'synthetic_fixture', 'phase': 'installing',
              'install': str(plan.install), 'install_identity': bridge.identity(plan.install),
              'manifest_sha256': bridge.digest(plan.manifest), 'protected': protected,
              'b_roots': [str(p) for p in roots_b], 'directories': [], 'files': [],
              'protocol_change': plan.protocol_change, 'protocol_before': plan.protocol_before,
              'protocol_written': 'fixture-router:' + str(plan.install), 'protocol_applied': False}
    transactions.create_once(receipt, receipt_bytes(record))
    for directory in [plan.install / 'bin', *roots_b]:
        adapter.before_operation()
        directory.mkdir()
        record['directories'].append({'path': str(directory), 'identity': bridge.identity(directory)})
        save_receipt(receipt, record)
    files = [(plan.install / 'bin' / name, raw) for name, raw in plan.assets]
    files += [(plan.install / 'bin' / 'profiles.json', plan.manifest)]
    files += [(path, adapter.shortcut_bytes(spec)) for path, spec in plan.shortcuts]
    for path, raw in files:
        adapter.before_operation()
        transactions.create_once(path, raw)
        record['files'].append({'path': str(path), 'sha256': bridge.digest(raw), 'identity': bridge.identity(path)})
        save_receipt(receipt, record)
    if plan.protocol_change:
        adapter.before_operation()
        adapter.protocol = record['protocol_written']
        record['protocol_applied'] = True
        save_receipt(receipt, record)
    record['phase'] = 'installed'
    save_receipt(receipt, record)
    return {'status': 'INSTALLED_FIXTURE', 'native_install': 'NOT_RUN', 'official_package_removal': False}


def check_owned_record(record, adapter):
    fields = {'schema', 'surface', 'phase', 'install', 'install_identity', 'manifest_sha256', 'protected',
              'b_roots', 'directories', 'files', 'protocol_change', 'protocol_before',
              'protocol_written', 'protocol_applied'}
    if set(record) != fields or record['schema'] != 1 or record['surface'] != 'synthetic_fixture' or \
            record['phase'] not in ('installing', 'installed', 'b_removed', 'b_removing'):
        raise bridge.BridgeError('OWNERSHIP_SCHEMA')
    install = adapter.check(Path(record['install']))
    if bridge.identity(install) != record['install_identity']:
        raise bridge.BridgeError('INSTALL_IDENTITY_CHANGED')
    protected = [bridge.safe_path(p) for p in record['protected']]
    for entry in record['directories']:
        path = adapter.check(Path(entry['path']))
        if bridge.identity(path) != entry['identity'] or any(bridge.overlap(path, p) for p in protected):
            raise bridge.BridgeError('OWNED_DIRECTORY_CHANGED')
    for entry in record['files']:
        path = adapter.check(Path(entry['path']))
        if any(bridge.overlap(path, p) for p in protected) or bridge.identity(path) != entry['identity'] or \
                bridge.digest(bridge.read_optional(path)) != entry['sha256']:
            raise bridge.BridgeError('OWNED_FILE_CHANGED')
    return install


def rollback_fixture(install: Path, adapter: FixtureWindows, *, writers_closed: bool):
    if writers_closed is not True or type(adapter) is not FixtureWindows:
        raise bridge.BridgeError('FIXTURE_CLOSED_WRITERS_REQUIRED')
    install = adapter.check(install)
    receipt = install / 'ownership.json'
    record, _ = read_receipt(receipt)
    check_owned_record(record, adapter)
    if record['protocol_applied'] and adapter.protocol != record['protocol_written']:
        raise bridge.BridgeError('PROTOCOL_CONFLICT')
    if record['protocol_change'] and not record['protocol_applied'] and adapter.protocol != record['protocol_before']:
        raise bridge.BridgeError('INTERRUPTED_PROTOCOL_CHANGE_REQUIRES_REVIEW')
    recorded = {entry['path'] for entry in record['files']} | {entry['path'] for entry in record['directories']}
    recorded.add(str(receipt))
    for folder in (install, install / 'bin'):
        if folder.exists() and any(str(path) not in recorded for path in folder.iterdir()):
            raise bridge.BridgeError('UNRECORDED_ADDITION_PRESERVED')
    lock = install / 'bin' / 'route.lock'
    # Refuse every outstanding runtime sidecar before cleanup; no name-only ownership.
    for name in ('target.txt', 'route.state.json', 'route.log'):
        if (install / 'bin' / name).exists():
            raise bridge.BridgeError('RUNTIME_SIDECAR_REQUIRES_REVIEW')
    if lock.exists():
        with transactions.locked(lock):
            raise bridge.BridgeError('RUNTIME_LOCK_REQUIRES_REVIEW')
    if record['protocol_applied']:
        adapter.protocol = record['protocol_before']
    for entry in reversed(record['files']):
        adapter.check(Path(entry['path'])).unlink()
    for entry in reversed(record['directories']):
        path = adapter.check(Path(entry['path']))
        # Retain B data/config by default, even if empty. Never recursively delete.
        if str(path) not in record['b_roots']:
            if any(path.iterdir()):
                raise bridge.BridgeError('UNRECORDED_ADDITION_PRESERVED')
            path.rmdir()
    receipt.unlink()
    if not any(install.iterdir()):
        install.rmdir()
    return {'status': 'ROLLED_BACK_FIXTURE', 'b_data_retained': True, 'official_package_removal': False}


def remove_b_fixture(install: Path, adapter: FixtureWindows, *, writers_closed: bool, delete_b_data=False):
    """Remove only receipt-owned B additions; retain A routing and official package."""
    if writers_closed is not True or type(adapter) is not FixtureWindows or type(delete_b_data) is not bool:
        raise bridge.BridgeError('FIXTURE_CLOSED_WRITERS_REQUIRED')
    install = adapter.check(install)
    receipt = install / 'ownership.json'
    record, _ = read_receipt(receipt)
    check_owned_record(record, adapter)
    if record['phase'] not in ('installed', 'b_removed'):
        raise bridge.BridgeError('PARTIAL_INSTALL_OR_REMOVAL_REQUIRES_REVIEW')
    if record['protocol_applied'] and adapter.protocol != record['protocol_written']:
        raise bridge.BridgeError('PROTOCOL_CONFLICT')
    for name in ('target.txt', 'route.state.json', 'route.log', 'route.lock'):
        sidecar = install / 'bin' / name
        if sidecar.exists():
            if name == 'route.lock':
                with transactions.locked(sidecar):
                    raise bridge.BridgeError('UNOWNED_RUNTIME_LOCK_REQUIRES_REVIEW')
            raise bridge.BridgeError('RUNTIME_SIDECAR_REQUIRES_REVIEW')
    b_directories = [entry for entry in record['directories'] if entry['path'] in record['b_roots']]
    if delete_b_data:
        count = 0
        for entry in b_directories:
            root = adapter.check(Path(entry['path']))
            for folder, directories, files in os.walk(root, followlinks=False):
                for name in directories + files:
                    count += 1
                    if count > bridge.MAX_ENTRIES:
                        raise bridge.BridgeError('B_DELETION_INSPECTION_LIMIT')
                    path = adapter.check(Path(folder) / name)
                    if path.is_file() and path.stat().st_nlink != 1:
                        raise bridge.BridgeError('B_DELETION_ALIAS_REFUSED')
    if record['phase'] == 'b_removed' and not delete_b_data:
        return {'status': 'B_ALREADY_REMOVED_FIXTURE', 'b_data_retained': True}
    record['phase'] = 'b_removing'
    save_receipt(receipt, record)
    manifest = install / 'bin' / 'profiles.json'
    before = bridge.read_optional(manifest)
    profiles = bridge.object_json(before)
    if set(profiles['profiles']) not in ({'A', 'B'}, {'A'}):
        raise bridge.BridgeError('MANIFEST_MAPPING_CHANGED')
    profiles['profiles'].pop('B', None)
    after = transactions.encode(profiles)
    transactions.replace_checked(manifest, after, before)
    for entry in record['files']:
        if entry['path'] == str(manifest):
            entry.update(sha256=bridge.digest(after), identity=bridge.identity(manifest))
    record['manifest_sha256'] = bridge.digest(after)
    save_receipt(receipt, record)
    for entry in list(record['files']):
        path = Path(entry['path'])
        if path.suffix.lower() == '.lnk':
            spec = bridge.object_json(bridge.read_optional(path)).get('fixture_shortcut', {})
            if spec.get('role') == 'B':
                adapter.check(path).unlink()
                record['files'].remove(entry)
                save_receipt(receipt, record)
    if delete_b_data:
        import shutil
        for entry in b_directories:
            root = adapter.check(Path(entry['path']))
            if bridge.identity(root) != entry['identity']:
                raise bridge.BridgeError('B_DELETION_IDENTITY_CHANGED')
            shutil.rmtree(root)  # Explicit fixture-only deletion, checked absolute TEMP roots.
            record['directories'].remove(entry)
            save_receipt(receipt, record)
    record['phase'] = 'b_removed'
    save_receipt(receipt, record)
    return {'status': 'B_REMOVED_FIXTURE', 'b_data_retained': not delete_b_data,
            'a_routing_retained': True, 'memory_deleted': False, 'official_package_removal': False}
