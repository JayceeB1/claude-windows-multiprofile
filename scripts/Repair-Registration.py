"""Repair only owned v1 router metadata; no default choice, URI or profile operation."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys
import uuid

import SharedMemoryPlan as bridge
import SharedMemoryApply as tx
import SharedWorkspace as entry
import NativeWindowsIO as windows


def installed_record(install):
    # Validate through the installed version, before replacing any owned bytes.
    program = "import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import NativeWorkspace as n;print(json.dumps(n.load(Path(sys.argv[2]))))"
    result = subprocess.run([sys.executable, '-B', '-c', program, str(install / 'bin'), str(install)],
        capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise bridge.BridgeError('INSTALLED_OWNERSHIP_REFUSED')
    return bridge.object_json(result.stdout)


def repair(install):
    install = bridge.safe_path(install, directory=True)
    with tx.locked(install / 'operation.lock'):
        record = installed_record(install)
        if record['phase'] != 'installed' or record['registry_phase'] != 'applied':
            raise bridge.BridgeError('REGISTRATION_REPAIR_PHASE_REFUSED')
        with windows.routing_guard(install / 'bin' / 'route.lock'):
            if windows.route_intent_pending(install / 'bin' / 'target.txt'):
                raise bridge.BridgeError('REGISTRATION_REPAIR_REQUIRES_DISARM')
            before = record['registry_after']
            desired = windows.desired_registry(install)
            if windows.registry_snapshot() != before:
                raise bridge.BridgeError('REGISTRATION_REPAIR_CONFLICT')
            if before == desired:
                windows.notify_association_changed()
                return {'status': 'REGISTRATION_METADATA_ALREADY_CURRENT', 'picker': 'NOT_OBSERVED'}
            target = install / 'bin' / 'NativeWindowsIO.py'
            owned = next(f for f in record['files'] if f['path'] == str(target) and f['role'] == 'asset')
            old_source = bridge.read_optional(target)
            if bridge.identity(target) != owned['identity'] or bridge.digest(old_source) != owned['sha256']:
                raise bridge.BridgeError('REGISTRATION_REPAIR_SOURCE_CHANGED')
            source = bridge.read_optional(Path(__file__).with_name('NativeWindowsIO.py'))
            ast.parse(source.decode('utf-8-sig'))
            command_before = before['router']['children']['shell']['children']['open']['children']['command']['values']['']
            command_after = desired['router']['children']['shell']['children']['open']['children']['command']['values']['']
            host_upgrade = command_before != command_after
            replacements = [(target, source)]
            additions = []
            if host_upgrade:
                legacy_v2 = windows.legacy_host_registry(desired, install)
                legacy_v1 = copy.deepcopy(legacy_v2)
                legacy_v1['router']['children'].pop('Application')
                legacy_v1['router']['children'].pop('DefaultIcon')
                old_caps = legacy_v1['capabilities']['children']['Capabilities']['values']
                old_caps.pop('ApplicationIcon')
                old_caps['ApplicationName'] = 'Claude Login Router'
                if before not in (legacy_v1, legacy_v2):
                    raise bridge.BridgeError('ROUTER_HOST_UPGRADE_NOT_EXPECTED_VERSION')
                repo = Path(__file__).parent
                for name in ('SharedWorkspacePlan.py', 'SharedWorkspace.py'):
                    replacements.append((install / 'bin' / name, bridge.read_optional(repo / name)))
                additions = [(install / 'bin/ClaudeLoginRouter.cs', bridge.read_optional(repo / 'ClaudeLoginRouter.cs')),
                             (install / 'bin/ClaudeLoginRouter.exe', bridge.read_optional(repo / 'ClaudeLoginRouter.exe'))]
                if not additions[-1][1] or not additions[-1][1].startswith(b'MZ'):
                    raise bridge.BridgeError('ROUTER_HOST_BUILD_REQUIRED')
                for path, payload in additions:
                    if bridge.safe_path(path).exists():
                        raise bridge.BridgeError('ROUTER_HOST_ADDITION_ALREADY_EXISTS')
                for path, payload in replacements:
                    match = next(f for f in record['files'] if f['path'] == str(path) and f['role'] == 'asset')
                    if bridge.identity(path) != match['identity'] or bridge.digest(bridge.read_optional(path)) != match['sha256']:
                        raise bridge.BridgeError('ROUTER_HOST_SOURCE_CONFLICT')
            receipt = install / 'native-ownership.json'
            receipt_before = bridge.read_optional(receipt)
            # Code/ownership backups only, never settings, credentials or session data.
            journal = install / ('registration-repair-' + uuid.uuid4().hex + '.json')
            backup = journal.with_suffix('.source-backup')
            tx.create_once(backup, old_source)
            state = {'schema': 1, 'phase': 'prepared', 'receipt_before': bridge.object_json(receipt_before),
                     'source_backup': str(backup), 'source_after_sha256': bridge.digest(source),
                     'registry_after': desired, 'UserChoice_modified': False}
            tx.create_once(journal, tx.encode(state))
            if host_upgrade:
                # Prepare new ownership in memory; the sealed receipt is persisted
                # below. An interruption requires journal review, not automatic retry.
                # Never adopt an existing file or rewrite a profile/default association.
                for path, payload in additions:
                    tx.create_once(path, payload)
                    record['files'].append({'path': str(path), 'role': 'asset', 'identity': bridge.identity(path),
                                            'sha256': bridge.digest(payload)})
                    record['approved_layout']['assets_sha256'][path.name] = bridge.digest(payload)
                if before == legacy_v1:
                    windows.repair_registration_metadata(before, legacy_v2)
                windows.upgrade_host_registration(legacy_v2, desired, install)
            else:
                windows.repair_registration_metadata(before, desired)
            state['phase'] = 'registry_updated'
            tx.replace_checked(journal, tx.encode(state), bridge.read_optional(journal))
            for path, payload in replacements:
                original = bridge.read_optional(path)
                if path != target:
                    tx.create_once(journal.with_name(journal.stem + '-' + path.name + '.source-backup'), original)
                tx.replace_checked(path, payload, original)
                match = next(f for f in record['files'] if f['path'] == str(path))
                match.update(identity=bridge.identity(path), sha256=bridge.digest(payload))
                record['approved_layout']['assets_sha256'][path.name] = bridge.digest(payload)
            record['registry_after'] = desired
            envelope = {'record': record, 'sha256': bridge.digest(tx.encode(record))}
            tx.replace_checked(receipt, tx.encode(envelope), receipt_before)
            checked = installed_record(install)
            if checked['registry_after'] != windows.registry_snapshot():
                raise bridge.BridgeError('REGISTRATION_REPAIR_FINAL_READBACK_FAILED')
            state['phase'] = 'completed'
            tx.replace_checked(journal, tx.encode(state), bridge.read_optional(journal))
    return {'status': 'REGISTRATION_METADATA_REPAIRED', 'UserChoice_modified': False,
            'profile_settings_modified': False, 'B_launched': False, 'picker': 'NOT_OBSERVED'}


def main():
    parser = entry.Parser(description=__doc__)
    parser.add_argument('--install-dir', type=Path, required=True)
    parser.add_argument('--approved', action='store_true')
    args = parser.parse_args()
    try:
        if not args.approved:
            raise bridge.BridgeError('REGISTRATION_REPAIR_APPROVAL_REQUIRED')
        windows.require_unpackaged_process()
        print(json.dumps(repair(args.install_dir)))
        return 0
    except (bridge.BridgeError, OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
        print('{"status":"REFUSED","reason":"REGISTRATION_REPAIR_REQUIRES_REVIEW"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
