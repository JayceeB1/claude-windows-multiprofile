"""Preview-only admission of the user-supplied slice1 bridge design.

Lineage: ZIP SHA256 654c158ae9f506d422a66cab688c79888e966adc9a46d34985d759e7c8de7d60.
The archive has no explicit license grant: no verbatim module is redistributed.
This fork adaptation implements its reviewed planner contract with native identity,
bounded readers, explicit provenance and per-project isolation. No apply/restore CLI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import re

_spec = importlib.util.spec_from_file_location('workspace_inventory',
    Path(__file__).with_name('Inspect-SharedWorkspace.py'))
inventory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inventory)
KEY = 'autoMemoryDirectory'
MAX_JSON = 65536
MAX_ENTRIES = 4096


class BridgeError(Exception):
    """Fixed reason codes only: never expose paths, values or raw OS errors."""


def digest(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def safe_path(value: str | Path, *, directory: bool = False) -> Path:
    try:
        path = Path(value)
        spelling = str(path)
        if not re.fullmatch(r'[A-Za-z]:[\\/].*', spelling) or any(
                part in ('.', '..') or part.endswith(('.', ' ')) or
                re.search(r'[\x00-\x1f:*?"<>|]', part) or
                re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I)
                for part in re.split(r'[\\/]', spelling[3:]) if part):
            raise BridgeError('LOCAL_UNAMBIGUOUS_PATH_REQUIRED')
        inventory.no_reparse(path)
        identity = inventory.physical_path(str(path))
        if directory and (not identity['exists'] or not identity['directory']):
            raise BridgeError('DIRECTORY_REQUIRED')
        return path
    except (inventory.Unknown, OSError, ValueError, TypeError):
        raise BridgeError('PATH_REFUSED') from None


def identity(path: Path) -> dict:
    safe_path(path)
    return inventory.physical_path(str(path))


def overlap(left: Path, right: Path) -> bool:
    return inventory.relationship(identity(left), identity(right)) != 'independent'


def object_json(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BridgeError('DUPLICATE_JSON')
            result[key] = value
        return result
    def nonfinite(_):
        raise BridgeError('NONFINITE_JSON')
    try:
        if len(raw) > MAX_JSON:
            raise BridgeError('JSON_LIMIT')
        result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=nonfinite)
        if not isinstance(result, dict):
            raise BridgeError('JSON_OBJECT_REQUIRED')
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise BridgeError('INVALID_JSON') from None


def read_optional(path: Path) -> bytes | None:
    safe_path(path)
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise BridgeError('SINGLE_REGULAR_FILE_REQUIRED')
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        with path.open('rb') as stream:
            if signature(os.fstat(stream.fileno())) != signature(before):
                raise BridgeError('READ_CHANGED')
            raw = stream.read(MAX_JSON + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_JSON or signature(after) != signature(before) or \
                signature(path.stat()) != signature(before):
            raise BridgeError('READ_LIMIT_OR_CHANGED')
        return raw
    except FileNotFoundError:
        return None
    except OSError:
        raise BridgeError('READ_UNAVAILABLE') from None


def validate_memory(path: Path) -> tuple:
    safe_path(path, directory=True)
    entries = []
    def visit(folder):
        with os.scandir(folder) as stream:
            for entry in stream:
                if len(entries) >= MAX_ENTRIES:
                    raise BridgeError('MEMORY_ENTRY_LIMIT')
                child = safe_path(Path(entry.path))
                info = child.stat()
                if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or
                        child.suffix.lower() != '.md' or info.st_nlink != 1):
                    raise BridgeError('MEMORY_MARKDOWN_ONLY')
                entries.append((str(child.relative_to(path)), identity(child), info.st_size, info.st_mtime_ns))
                if stat.S_ISDIR(info.st_mode):
                    visit(child)
    try:
        visit(path)
        if entries and not (path / 'MEMORY.md').is_file():
            raise BridgeError('MEMORY_INDEX_REQUIRED')
        return tuple(sorted(entries, key=lambda entry: entry[0]))
    except (OSError, RecursionError):
        raise BridgeError('MEMORY_UNAVAILABLE') from None


def validate_profiles(profiles: dict) -> dict:
    if not isinstance(profiles, dict) or set(profiles) != {'A', 'B'}:
        raise BridgeError('EXPLICIT_A_B_REQUIRED')
    roots = []
    result = {}
    for role in ('A', 'B'):
        profile = profiles[role]
        if not isinstance(profile, dict) or set(profile) != {'dataDir', 'configDir'}:
            raise BridgeError('PROFILE_SCHEMA')
        result[role] = {}
        for key in ('dataDir', 'configDir'):
            value = profile[key]
            if not isinstance(value, str) or not value:
                raise BridgeError('EXPLICIT_ROOT_REQUIRED')
            path = safe_path(value, directory=(role == 'A'))
            info = identity(path)
            if role == 'B' and info['exists']:
                raise BridgeError('B_ROOT_ALREADY_EXISTS_UNOWNED')
            if any(overlap(path, prior) for prior in roots):
                raise BridgeError('PROFILE_ROOT_COLLISION')
            roots.append(path)
            result[role][key] = path
    return result


@dataclass(frozen=True)
class Evidence:
    """Operator evidence, never guessed from folder existence or an environment."""
    config_provenance: bool
    memory_provenance: bool
    trust_confirmed: bool
    external_policy_reviewed: bool
    version: str
    surface: str = 'desktop_user_report'


@dataclass(frozen=True)
class Plan:
    project: Path
    memory: Path
    settings: Path
    profiles: dict = field(repr=False)
    evidence: Evidence
    before: bytes | None = field(repr=False)
    after: bytes = field(repr=False)
    snapshots: tuple = field(repr=False)
    memory_snapshot: tuple = field(repr=False)
    roots_snapshot: tuple = field(repr=False)

    @property
    def changed(self):
        return self.before != self.after

    def summary(self):
        return {'status': 'PLAN' if self.changed else 'ALREADY_CONFIGURED',
                'writes': int(self.changed), 'selected_keys': [KEY] if self.changed else [],
                'apply_allowed': False, 'runtime_qualification': 'NOT_TESTED',
                'credential_files_read': 0, 'memory_files_copied': 0}

    def private_preview(self):
        return {**self.summary(), 'project': str(self.project), 'memory': str(self.memory),
                'settings': str(self.settings), 'before_sha256': digest(self.before),
                'after_sha256': digest(self.after), 'version': self.evidence.version,
                'provenance': self.evidence.surface,
                'change': {KEY: str(self.memory)} if self.changed else {}}


def make_plan(project: Path, memory: Path, profiles: dict, evidence: Evidence) -> Plan:
    if not isinstance(evidence, Evidence) or not all(value is True for value in (
            evidence.config_provenance, evidence.memory_provenance, evidence.trust_confirmed,
            evidence.external_policy_reviewed)) or not isinstance(evidence.version, str) or \
            not evidence.version or len(evidence.version) > 80 or evidence.surface not in (
                'desktop_user_report', 'native_observation', 'synthetic_fixture'):
        raise BridgeError('PROVENANCE_TRUST_OR_POLICY_UNRESOLVED')
    project = safe_path(project, directory=True)
    memory = safe_path(memory, directory=True)
    roots = validate_profiles(profiles)
    for role, profile in roots.items():
        for key, root in profile.items():
            if overlap(project, root):
                raise BridgeError('PROJECT_PROFILE_COLLISION')
            if role == 'B' or key == 'dataDir':
                if overlap(memory, root):
                    raise BridgeError('MEMORY_DELETION_ROOT_COLLISION')
            elif identity(memory)['canonical'] == identity(root)['canonical'] or \
                    identity(root)['canonical'].startswith(identity(memory)['canonical'].rstrip('\\') + '\\'):
                raise BridgeError('MEMORY_CONTAINS_A_CONFIG')
    settings = safe_path(project / '.claude' / 'settings.local.json')
    if overlap(memory, settings.parent):
        raise BridgeError('MEMORY_SETTINGS_COLLISION')
    paths = [roots['A']['configDir'] / 'settings.json', roots['B']['configDir'] / 'settings.json',
             project / '.claude' / 'settings.json', settings]
    snapshots = tuple((p, read_optional(p)) for p in paths)
    for scope, raw in snapshots:
        obj = object_json(raw) if raw is not None else {}
        if 'autoMemoryEnabled' in obj and obj['autoMemoryEnabled'] is not True:
            raise BridgeError('MEMORY_DISABLED_OR_INVALID')
        env = obj.get('env', {})
        if not isinstance(env, dict) or any(key in env for key in (
                'CLAUDE_CODE_DISABLE_AUTO_MEMORY', 'CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_PROJECT_DIR_NAME')):
            raise BridgeError('ENVIRONMENT_OVERRIDE_UNRESOLVED')
        permissions = obj.get('permissions', {})
        if not isinstance(permissions, dict) or permissions.get('blockReadsOutsideWorkingDirectories') is True:
            raise BridgeError('READ_POLICY_REQUIRES_SEPARATE_REVIEW')
        if KEY in obj:
            if not isinstance(obj[KEY], str) or identity(safe_path(obj[KEY]))['canonical'] != identity(memory)['canonical']:
                raise BridgeError('DIRECTORY_OVERRIDE_CONFLICT')
    before = snapshots[-1][1]
    obj = object_json(before) if before is not None else {}
    if KEY in obj:
        after = before
    else:
        obj[KEY] = str(memory)
        after = (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(after) > MAX_JSON:
        raise BridgeError('PROPOSED_JSON_LIMIT')
    root_paths = [project, memory, *(p for role in roots.values() for p in role.values()),
                  settings.parent, *(p for p, _ in snapshots)]
    return Plan(project, memory, settings, roots, evidence, before, after, snapshots,
                validate_memory(memory), tuple((p, identity(p)) for p in root_paths))


def revalidate(plan: Plan) -> None:
    for path, before in plan.roots_snapshot:
        if identity(path) != before:
            raise BridgeError('PLAN_ROOT_CHANGED')
    for path, before in plan.snapshots:
        if read_optional(path) != before:
            raise BridgeError('PLAN_SETTINGS_CHANGED')
    if validate_memory(plan.memory) != plan.memory_snapshot:
        raise BridgeError('PLAN_MEMORY_CHANGED')


def make_plans(requests: list[tuple]) -> tuple[Plan, ...]:
    plans = []
    for request in requests:
        plan = make_plan(*request)
        for prior in plans:
            if overlap(plan.project, prior.project) or overlap(plan.memory, prior.memory):
                raise BridgeError('DISTINCT_PROJECT_MAPPING_REQUIRED')
        plans.append(plan)
    return tuple(plans)
