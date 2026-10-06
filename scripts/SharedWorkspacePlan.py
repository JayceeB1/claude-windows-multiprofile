"""Additive workspace preview. No install, activation or OS registration here."""
from dataclasses import dataclass, field
import json
from pathlib import Path

import SharedMemoryPlan as bridge

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
