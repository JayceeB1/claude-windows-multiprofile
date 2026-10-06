"""Preview-first entry; native candidate actions require explicit reviewed approval."""
import argparse
import json
from pathlib import Path
import re
import sys
import zipfile
import os

import SharedMemoryPlan as memory
import SharedWorkspacePlan as workspace

PACKAGE_FILES = ('Launch-Claude.ps1', 'launch.vbs', 'ClaudeOpenShim.ps1', 'Arm-ClaudeLogin.ps1',
                 'Test-ClaudeRouting.ps1', 'Inspect-SharedWorkspace.py', 'SharedMemoryPlan.py',
                 'SharedMemoryApply.py', 'SharedWorkspacePlan.py', 'SharedWorkspace.py', 'Uninstall.ps1',
                 'Setup.ps1', 'NativeWindowsIO.py', 'NativeWorkspace.py')
PACKAGE_DOCS = ('README.md', 'LICENSE', 'MANUAL-TEST.md', 'docs/PROTOCOL-ROUTING.md',
                'docs/SHARED-WORKSPACE-ROADMAP.md', 'docs/SHARED-WORKSPACE-LEDGER.md',
                'docs/SHARED-WORKSPACE-QUALIFICATION.md', 'docs/REA-QUALIFICATION.md',
                'docs/REA-SMOKE-20261006.md', 'docs/REA-SMOKE-20261006.json',
                'tests/fixtures/rea/package-recipe.json', 'tests/Run-ReaPackagedSmoke.py')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print('{"status":"REFUSED","reason":"INVALID_ARGUMENTS"}')
        raise SystemExit(2)


def spec_plan(path: Path):
    if not path.name.endswith('.workspace.local.json'):
        raise memory.BridgeError('PRIVATE_SPEC_NAME_REQUIRED')
    raw = memory.read_optional(path)
    if raw is None:
        raise memory.BridgeError('SPEC_REQUIRED')
    obj = memory.object_json(raw)
    if set(obj) != {'schema', 'profiles', 'projects', 'install_dir', 'desktop_dir', 'protocol'} or obj['schema'] != 1:
        raise memory.BridgeError('SPEC_SCHEMA')
    projects = obj['projects']
    if not isinstance(projects, list) or not 1 <= len(projects) <= 16:
        raise memory.BridgeError('PROJECT_MAPPING_LIMIT')
    requests = []
    for project in projects:
        if not isinstance(project, dict) or set(project) != {'project', 'memory', 'evidence'}:
            raise memory.BridgeError('PROJECT_SCHEMA')
        evidence = project['evidence']
        if not isinstance(evidence, dict) or set(evidence) != {'config_provenance', 'memory_provenance',
                'trust_confirmed', 'external_policy_reviewed', 'version', 'surface'}:
            raise memory.BridgeError('EVIDENCE_SCHEMA')
        requests.append((Path(project['project']), Path(project['memory']), obj['profiles'], memory.Evidence(**evidence)))
    protocol = obj['protocol']
    if not isinstance(protocol, dict) or set(protocol) != {'change', 'consent', 'expected_before'}:
        raise memory.BridgeError('PROTOCOL_SCHEMA')
    plans = memory.make_plans(requests)
    return workspace.make_workspace_plan(plans, Path(obj['install_dir']), Path(obj['desktop_dir']),
        protocol_change=protocol['change'], protocol_consent=protocol['consent'], protocol_before=protocol['expected_before'])


def private_report(path: Path, plan, spec: Path):
    path = memory.safe_path(path)
    protected = [plan.install, plan.desktop, spec]
    for item in plan.memory_plans:
        protected.extend((item.project, item.memory))
        protected.extend(p for role in item.profiles.values() for p in role.values())
    if not str(path).endswith('.local.md') or any(memory.overlap(path, p) for p in protected):
        raise memory.BridgeError('PRIVATE_OUTPUT_PROTECTION')
    with path.open('xb') as stream:
        stream.write((json.dumps(plan.private_preview(), indent=2) + '\n').encode('utf-8'))


def package(output: Path):
    output = memory.safe_path(output)
    source = Path(__file__).resolve().parent
    if output.suffix.lower() != '.zip' or memory.overlap(output, source.parent):
        raise memory.BridgeError('PACKAGE_OUTPUT_PROTECTION')
    files = {}
    for name in PACKAGE_FILES:
        raw = memory.read_optional(source / name)
        if raw is None:
            raise memory.BridgeError('PACKAGE_MEMBER_MISSING')
        files['scripts/' + name] = raw
    for name in PACKAGE_DOCS:
        raw = memory.read_optional(source.parent / name)
        if raw is None:
            raise memory.BridgeError('PACKAGE_MEMBER_MISSING')
        files[name] = raw
    receipt = {'schema': 1, 'source': 'WORKTREE_SNAPSHOT', 'native_execution': 'IMPLEMENTED_NOT_TESTED',
               'sha256': {name: memory.digest(raw) for name, raw in files.items()}}
    files['PACKAGE.json'] = (json.dumps(receipt, indent=2) + '\n').encode('utf-8')
    with output.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
    return {'status': 'PACKAGED', 'members': len(files), 'native_execution': 'IMPLEMENTED_NOT_TESTED'}


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('action', nargs='?', default='help')
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--approval', type=Path, help='Exact saved *.native.local.json preview')
    parser.add_argument('--install-dir', type=Path)
    parser.add_argument('--approved', action='store_true', help='Explicit approval for this local operation')
    parser.add_argument('--writers-closed', action='store_true')
    parser.add_argument('--approve-protocol', action='store_true')
    parser.add_argument('--delete-owned-b-data', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'help':
            parser.print_help()
            return 0
        if args.action == 'preview':
            if args.approval or args.install_dir or args.approved or args.writers_closed or args.approve_protocol or args.delete_owned_b_data:
                raise memory.BridgeError('PREVIEW_ARGUMENTS')
            if args.spec is None:
                raise memory.BridgeError('SPEC_REQUIRED')
            plan = spec_plan(args.spec)
            if args.output:
                private_report(args.output, plan, args.spec)
            result = {**plan.summary(), 'private_report': 'saved' if args.output else 'not_saved'}
        elif args.action.startswith('native-'):
            if os.name != 'nt':
                raise memory.BridgeError('WINDOWS_NATIVE_REQUIRED')
            import NativeWorkspace as native
            if args.action == 'native-preview':
                if args.spec is None or args.output is None or args.approved or args.approval or args.install_dir or \
                        args.writers_closed or args.approve_protocol or args.delete_owned_b_data:
                    raise memory.BridgeError('NATIVE_PREVIEW_ARGUMENTS')
                plan = spec_plan(args.spec)
                capsule = native.prepare(plan, args.spec)
                native.save_preview(args.output, capsule, plan, args.spec)
                result = {**plan.summary(), 'status': 'NATIVE_PREVIEW_SAVED', 'preview_sha256': capsule['sha256'],
                          'native_qualification': 'NOT_TESTED'}
            elif args.action == 'native-install':
                native.require_approval(args.approved, args.writers_closed)
                if args.spec is None or args.approval is None or args.output or args.install_dir or args.delete_owned_b_data:
                    raise memory.BridgeError('NATIVE_INSTALL_ARGUMENTS')
                capsule_record = native.approval(args.approval)
                install_dir = memory.safe_path(capsule_record['workspace']['install'])
                if install_dir.exists():
                    result = native.installed_again(install_dir, capsule_record, args.spec,
                        approved=args.approved, writers_closed=args.writers_closed)
                else:
                    plan = spec_plan(args.spec)
                    result = native.install(plan, capsule_record, args.spec, approved=args.approved,
                        writers_closed=args.writers_closed, approve_protocol=args.approve_protocol)
            elif args.action in ('native-remove-b', 'native-rollback'):
                native.require_approval(args.approved, args.writers_closed)
                if args.install_dir is None or args.spec or args.output or args.approval:
                    raise memory.BridgeError('NATIVE_RECOVERY_ARGUMENTS')
                if args.action == 'native-remove-b':
                    if args.approve_protocol:
                        raise memory.BridgeError('B_REMOVAL_RETAINS_PROTOCOL')
                    result = native.remove_b(args.install_dir, approved=args.approved,
                        writers_closed=args.writers_closed, delete_b_data=args.delete_owned_b_data)
                else:
                    if args.delete_owned_b_data:
                        raise memory.BridgeError('ROLLBACK_RETAINS_B_DATA')
                    result = native.rollback(args.install_dir, approved=args.approved,
                        writers_closed=args.writers_closed, approve_protocol=args.approve_protocol)
            else:
                raise memory.BridgeError('NATIVE_ACTION_NOT_ADMITTED')
        elif args.action == 'package':
            if args.output is None or args.spec is not None or args.approval or args.install_dir or args.approved or \
                    args.writers_closed or args.approve_protocol or args.delete_owned_b_data:
                raise memory.BridgeError('PACKAGE_ARGUMENTS')
            result = package(args.output)
        else:
            raise memory.BridgeError('NATIVE_ACTION_NOT_ADMITTED')
        print(json.dumps(result))
        return 0
    except (memory.BridgeError, memory.inventory.Unknown, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, memory.BridgeError) and re.fullmatch('[A-Z_]+', str(exc)) else 'INPUT_OR_IO_REFUSED'
        print(json.dumps({'status': 'REFUSED', 'reason': reason, 'apply_allowed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
