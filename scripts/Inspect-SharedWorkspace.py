"""Read-only Windows inventory; private paths stay in an optional .local.md report.

No profile-content traversal, process command lines, activation, registry mutation,
settings changes or ownership inferred from names. Native handles establish current
physical identity only. Actual effective Desktop configuration requires user proof.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess


class Unknown(Exception):
    """An observation is unavailable; raw OS errors are never emitted."""


class FileInfo(ctypes.Structure):
    _fields_ = [('attributes', wintypes.DWORD), ('created', wintypes.FILETIME),
                ('accessed', wintypes.FILETIME), ('written', wintypes.FILETIME),
                ('volume', wintypes.DWORD), ('size_high', wintypes.DWORD),
                ('size_low', wintypes.DWORD), ('links', wintypes.DWORD),
                ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]


def native_identity(path: str) -> dict:
    if os.name != 'nt':
        raise Unknown('WINDOWS_ONLY')
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
    api.GetFileInformationByHandle.restype = wintypes.BOOL
    api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                           wintypes.DWORD, wintypes.DWORD]
    api.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    # FILE_READ_ATTRIBUTES, share read/write/delete, OPEN_EXISTING, BACKUP_SEMANTICS.
    handle = api.CreateFileW(path, 0x80, 7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise Unknown('IDENTITY_UNAVAILABLE')
    try:
        info = FileInfo()
        if not api.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise Unknown('IDENTITY_UNAVAILABLE')
        buffer = ctypes.create_unicode_buffer(32768)
        size = api.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not size or size >= len(buffer):
            raise Unknown('FINAL_PATH_UNAVAILABLE')
        final = buffer.value
        if not final.startswith('\\\\?\\') or final.startswith('\\\\?\\UNC\\'):
            raise Unknown('NONLOCAL_FINAL_PATH')
        return {'canonical': ntpath.normpath(final[4:]).casefold(),
                'file_id': [info.volume, info.index_high, info.index_low],
                'directory': bool(info.attributes & 0x10)}
    finally:
        api.CloseHandle(handle)


def physical_path(path: str) -> dict:
    if not isinstance(path, str) or not re.fullmatch(r'[A-Za-z]:[\\/].*', path):
        raise Unknown('LOCAL_ABSOLUTE_PATH_REQUIRED')
    parts = re.split(r'[\\/]', path[3:])
    if any(p in ('.', '..') or p.endswith(('.', ' ')) or
           re.search(r'[\x00-\x1f:*?"<>|]', p) or
           re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I)
           for p in parts if p):
        raise Unknown('AMBIGUOUS_PATH')
    current = ntpath.normpath(path)
    pending = []
    # A dangling alias is existing but unresolved, never treated as new ownership.
    while not os.path.lexists(current):
        parent, name = ntpath.split(current)
        if not name or parent == current:
            raise Unknown('ANCESTOR_UNAVAILABLE')
        pending.insert(0, name)
        current = parent
    identity = native_identity(current)
    if pending and not identity['directory']:
        raise Unknown('ANCESTOR_NOT_DIRECTORY')
    return {**identity, 'canonical': ntpath.join(identity['canonical'], *pending).casefold(),
            'exists': not pending, 'projected': bool(pending),
            'file_id': None if pending else identity['file_id']}


def relationship(left: dict, right: dict) -> str:
    if left['file_id'] is not None and left['file_id'] == right['file_id']:
        return 'alias'
    a, b = left['canonical'], right['canonical']
    if a == b:
        return 'alias'
    if a.startswith(b.rstrip('\\') + '\\') or b.startswith(a.rstrip('\\') + '\\'):
        return 'nested'
    return 'independent'


def inventory_roots(specs: dict, probe=physical_path) -> dict:
    roots = {}; conflicts = []
    for label, item in specs.items():
        try:
            if item['role'] not in ('protected', 'addition'):
                raise Unknown('ROLE_UNKNOWN')
            identity = probe(item['path'])
            if not identity['directory'] and identity['exists']:
                raise Unknown('ROOT_NOT_DIRECTORY')
            state = 'preserve' if item['role'] == 'protected' else (
                'existing_unowned' if identity['exists'] else 'prospective_unowned')
            roots[label] = {'path': item['path'], 'role': item['role'], 'identity': identity,
                            'state': state, 'ownership': 'unproven'}
        except (Unknown, OSError, ValueError, KeyError):
            roots[label] = {'role': item.get('role', 'unknown'), 'state': 'unknown',
                            'ownership': 'unproven'}
    labels = list(roots)
    for index, first in enumerate(labels):
        for second in labels[index + 1:]:
            if 'identity' not in roots[first] or 'identity' not in roots[second]:
                continue
            relation = relationship(roots[first]['identity'], roots[second]['identity'])
            if relation != 'independent':
                conflicts.append({'roots': [first, second], 'kind': relation})
    return {'roots': roots, 'conflicts': conflicts, 'apply_allowed': False,
            'effective_a': 'unconfirmed', 'purpose': 'read_only_inventory'}


def read_manifest(install_dir: str) -> dict:
    """Only bounded routing metadata, never arbitrary installed source/config."""
    marker = Path(install_dir) / 'bin' / 'profiles.json'
    try:
        # Refuse metadata aliases; directory aliases remain visible in root identities.
        if marker.is_symlink() or marker.is_junction():
            return {'state': 'unknown', 'profiles': {}}
        with marker.open('rb') as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            return {'state': 'invalid', 'profiles': {}}
        cfg = json.loads(data.decode('utf-8-sig'))
        profiles = cfg.get('profiles')
        if not isinstance(profiles, dict) or not 1 <= len(profiles) <= 32:
            return {'state': 'invalid', 'profiles': {}}
        clean = {}
        for name, record in profiles.items():
            if not isinstance(record, dict) or not isinstance(record.get('dataDir'), str) or \
                    not isinstance(record.get('configDir'), str):
                return {'state': 'invalid', 'profiles': {}}
            clean[name] = {'dataDir': record['dataDir'], 'configDir': record['configDir']}
        return {'state': 'readable', 'profiles': clean}
    except FileNotFoundError:
        return {'state': 'missing', 'profiles': {}}
    except (OSError, ValueError, AttributeError):
        return {'state': 'unknown', 'profiles': {}}


def installed_package() -> dict:
    script = "$ErrorActionPreference='Stop'; try { $p=@(Get-AppxPackage -Name '*Claude*' -ErrorAction Stop | Select-Object Name,Version,InstallLocation); ConvertTo-Json -InputObject $p -Compress } catch { '[]' }"
    try:
        result = subprocess.run(['powershell', '-NoLogo', '-NoProfile', '-NonInteractive',
                                 '-Command', script], capture_output=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        packages = json.loads(result.stdout.decode('utf-8-sig'))
        if not isinstance(packages, list):
            return {'state': 'unknown', 'packages': []}
        return {'state': 'observed' if packages else 'unknown', 'packages': packages}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {'state': 'unknown', 'packages': []}


def read_route_state(install_dir: str) -> dict:
    path = Path(install_dir) / 'bin' / 'target.txt'
    try:
        if path.is_symlink() or path.is_junction():
            return {'state': 'unknown'}
        with path.open('rb') as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            return {'state': 'invalid'}
        record = json.loads(data.decode('utf-8-sig'))
        if not isinstance(record, dict) or record.get('version') != 2 or \
                record.get('status') not in ('armed', 'consumed', 'disarmed'):
            return {'state': 'invalid'}
        # Observation only, no dispatchability/expiry claim; no profile or URL.
        return {'state': record['status'], 'consistency': 'not_qualified'}
    except FileNotFoundError:
        return {'state': 'missing'}
    except (OSError, ValueError):
        return {'state': 'unknown'}


def installed_assets(install_dir: str) -> dict:
    # Presence cannot establish who installed/owns an asset or permit removal.
    bin_dir = Path(install_dir) / 'bin'
    names = ('Launch-Claude.ps1', 'launch.vbs', 'ClaudeOpenShim.ps1', 'Arm-ClaudeLogin.ps1')
    return {name: {'present': (bin_dir / name).is_file(), 'ownership': 'unproven'} for name in names}


def inspect_entry(path: str | None) -> dict:
    # No command-line collection or shell execution. An explicit entry can be
    # inventoried by physical identity but cannot establish effective config.
    if not path:
        return {'state': 'unknown', 'source': 'not_supplied'}
    try:
        identity = physical_path(path)
        return {'state': 'observed' if identity['exists'] else 'missing',
                'source': 'user_candidate', 'path': path, 'identity': identity}
    except (Unknown, OSError, ValueError):
        return {'state': 'unknown', 'source': 'user_candidate'}


def save_private(path: str, report: dict, protected: dict) -> None:
    target = physical_path(path)
    if target['exists'] or not path.endswith('.local.md'):
        raise Unknown('OUTPUT_NOT_NEW_PRIVATE_FILE')
    for item in protected.values():
        if 'identity' not in item:
            raise Unknown('OUTPUT_PROTECTION_UNKNOWN')
        if relationship(target, item['identity']) != 'independent':
            raise Unknown('OUTPUT_INSIDE_PROTECTED_ROOT')
    # Exclusive create, no overwrite; output is the ONLY optional write.
    with open(path, 'x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-dir', required=True)
    parser.add_argument('--a-data', required=True)
    parser.add_argument('--a-config', required=True)
    parser.add_argument('--entry-point')
    parser.add_argument('--entry-kind', choices=('unknown', 'registered_app', 'custom'), default='unknown',
                        help='User-reported opening method; does not prove effective config')
    parser.add_argument('--output', help='New private .local.md JSON report outside observed roots')
    args = parser.parse_args()
    report = inventory_roots({'a_data': {'path': args.a_data, 'role': 'protected'},
                              'a_config': {'path': args.a_config, 'role': 'protected'},
                              'install_metadata': {'path': args.install_dir, 'role': 'protected'}})
    if 'identity' in report['roots']['install_metadata']:
        report['manifest'] = read_manifest(args.install_dir)
        report['route_state'] = read_route_state(args.install_dir)
        report['assets'] = installed_assets(args.install_dir)
    else:
        report['manifest'] = {'state': 'unknown', 'profiles': {}}
        report['route_state'] = {'state': 'unknown'}
        report['assets'] = {}
    report['package'] = installed_package()
    report['entry_point'] = inspect_entry(args.entry_point)
    if args.entry_kind != 'unknown':
        report['entry_point']['reported_kind'] = args.entry_kind
        report['entry_point']['opening_method_source'] = 'user_report'
    report['a_source'] = 'user_candidates_not_effective_desktop_proof'
    if args.output:
        save_private(args.output, report, report['roots'])
    # Public stdout is fixed and path-free, even when the private report has paths.
    print(json.dumps({'event': 'INVENTORY_READ_ONLY', 'effective_a': 'unconfirmed',
                      'apply_allowed': False, 'private_report': 'saved' if args.output else 'not_saved',
                      'package': report['package']['state'], 'manifest': report['manifest']['state'],
                      'entry_point': report['entry_point']['state'],
                      'conflicts': len(report['conflicts'])}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Unknown, OSError, ValueError, KeyError):
        print('{"event":"INVENTORY_UNKNOWN","apply_allowed":false}')
        raise SystemExit(1)
