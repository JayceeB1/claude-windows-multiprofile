"""Bounded native Windows Q1 qualification; no installed profiles or real launch.

Usage (Python 3.12+): python tests/Test-RoutingProcesses.py [--shell powershell|pwsh|both]
Each process parses guarded fixture copies before importing. IPC events prove
interleavings; a recording launch double replaces Claude. No sleeps, registry,
profile discovery, process scanning, credentials, or external dependencies.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid


CASE_SECONDS = 15
SUITE_SECONDS = 120
WORKER = Path(__file__).resolve().parent / 'fixtures' / 'RouteWorker.ps1'
SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'
CALLBACK_EVENTS = {'ROUTE_BUSY', 'TARGET_READ_FAILED', 'LAUNCH_REQUESTED', 'DISPATCH_COMPLETE'}


class Failure(Exception):
    """Only a fixed assertion identifier is exposed by the runner."""


def require(condition: bool, label: str) -> None:
    if not condition:
        raise Failure(label)


class Child:
    def __init__(self, case: Case, mode: str, profile: str = 'B', hold: bool = False):
        self.case = case
        self.events: queue.Queue = queue.Queue()
        args = [case.shell, '-NoLogo', '-NoProfile', '-NonInteractive',
                '-ExecutionPolicy', 'Bypass', '-File', str(WORKER),
                '-FixtureRoot', str(case.root), '-Token', case.token,
                '-Mode', mode, '-Profile', profile]
        if hold:
            args.append('-Hold')
        self.process = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # Own the Popen object/Windows handle from creation; never rediscover a PID.
        case.children.append(self)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        ready = self.expect('ready')
        require(ready.get('mode') == mode, 'WORKER_MODE_MISMATCH')
        version = ready.get('shell', '')
        require(isinstance(version, str) and
                version.startswith('5.1.' if Path(case.shell).stem == 'powershell' else '7.'),
                'SHELL_VERSION_MISMATCH')

    def _read(self) -> None:
        try:
            for line in self.process.stdout:
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    event = {'event': 'invalid-output'}
                self.events.put(event)
        finally:
            self.events.put({'event': 'eof'})

    def expect(self, expected: str, timeout: float | None = None) -> dict:
        remaining = self.case.remaining()
        if timeout is not None:
            remaining = min(remaining, timeout)
        try:
            event = self.events.get(timeout=remaining)
        except queue.Empty as exc:
            raise Failure('BARRIER_TIMEOUT') from exc
        require(isinstance(event, dict) and event.get('event') == expected,
                'UNEXPECTED_WORKER_EVENT')
        require(event.get('pid') == self.process.pid, 'WORKER_PID_MISMATCH')
        return event

    def send(self, command: str) -> None:
        self.case.remaining()
        self.process.stdin.write(command + '\n')
        self.process.stdin.flush()

    def finish(self, code: int) -> None:
        result = self.expect('result')
        require(result.get('code') == code, 'RESULT_CODE_MISMATCH')
        require(self.process.wait(timeout=self.case.remaining()) == code, 'EXIT_CODE_MISMATCH')
        require(self.events.get(timeout=self.case.remaining()).get('event') == 'eof',
                'OUTPUT_AFTER_RESULT')


class Case:
    def __init__(self, shell: str, suite_deadline: float):
        self.shell = shell
        self.deadline = min(time.monotonic() + CASE_SECONDS, suite_deadline)
        self.children: list[Child] = []
        self.root = Path(tempfile.mkdtemp(prefix='ClaudeRouteQ1-')).resolve()
        self.token = uuid.uuid4().hex
        (self.root / 'owner.txt').write_text(self.token, encoding='ascii')
        (self.root / 'bin').mkdir()
        for name in ('ClaudeOpenShim.ps1', 'Arm-ClaudeLogin.ps1', 'Launch-Claude.ps1'):
            shutil.copyfile(SCRIPTS / name, self.root / 'bin' / name)
        (self.root / 'package' / 'app').mkdir(parents=True)
        (self.root / 'package' / 'app' / 'Claude.exe').write_text('SYNTHETIC ONLY', encoding='ascii')
        manifest = {'defaultProfile': 'A', 'profiles': {}}
        for name in ('A', 'B'):
            manifest['profiles'][name] = {
                'dataDir': str(self.root / ('Data ' + name)),
                'configDir': str(self.root / ('Config ' + name)),
                'isDefault': name == 'A',
            }
        self.manifest = json.dumps(manifest).encode('utf-8')
        (self.root / 'bin' / 'profiles.json').write_bytes(self.manifest)

    def remaining(self) -> float:
        value = self.deadline - time.monotonic()
        require(value > 0, 'CASE_DEADLINE')
        return value

    def child(self, mode: str, profile: str = 'B', hold: bool = False) -> Child:
        self.remaining()
        return Child(self, mode, profile, hold)

    def run(self, mode: str, code: int = 0, profile: str = 'B') -> None:
        child = self.child(mode, profile)
        child.send('go')
        child.finish(code)

    def marker_bytes(self) -> bytes:
        return (self.root / 'bin' / 'target.txt').read_bytes()

    def status(self, wanted: str, profile: str | None = None) -> None:
        marker = json.loads(self.marker_bytes())
        require(marker['version'] == 2 and marker['status'] == wanted, 'MARKER_STATUS')
        if profile:
            require(marker['profile'] == profile, 'MARKER_PROFILE')

    def no_launch(self) -> None:
        require(not list(self.root.glob('launch-*.json')), 'UNEXPECTED_LAUNCH')

    def stable_metadata(self) -> None:
        require((self.root / 'bin' / 'profiles.json').read_bytes() == self.manifest,
                'MANIFEST_CHANGED')
        require(not list((self.root / 'bin').glob('*.tmp')), 'ORPHAN_TEMP')
        require(not (self.root / 'Data A').exists() and not (self.root / 'Data B').exists()
                and not (self.root / 'Config A').exists() and not (self.root / 'Config B').exists(),
                'PROFILE_ROOT_CREATED')

    def logs(self, events: list[str]) -> None:
        lines = (self.root / 'bin' / 'route.log').read_text(encoding='utf-8-sig').splitlines()
        observed = []
        for line in lines:
            match = re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d event=(\w+) target=(unknown|profile)', line)
            require(match is not None and match[1] in CALLBACK_EVENTS, 'LOG_SCHEMA')
            kind = 'unknown' if match[1] in {'ROUTE_BUSY', 'TARGET_READ_FAILED'} else 'profile'
            require(match[2] == kind, 'LOG_TARGET_KIND')
            observed.append(match[1])
        require(observed == events, 'LOG_EVENTS')

    def cleanup(self) -> None:
        # Wait for all OWNED process handles to exit before removing metadata.
        # Popen terminate on Windows targets its retained handle, never a PID scan.
        for child in self.children:
            if child.process.poll() is None:
                child.process.terminate()
            child.process.wait(timeout=2)
            child.reader.join(timeout=2)
            require(not child.reader.is_alive(), 'READER_STILL_ACTIVE')
            child.process.stdin.close()
            child.process.stdout.close()
        require(self.root.parent == Path(tempfile.gettempdir()).resolve()
                and self.root.name.startswith('ClaudeRouteQ1-')
                and not self.root.is_junction() and not self.root.is_symlink()
                and (self.root / 'owner.txt').read_text(encoding='ascii') == self.token,
                'CLEANUP_OWNERSHIP')
        require(not any(p.is_symlink() or p.is_junction() for p in self.root.rglob('*')),
                'CLEANUP_ALIAS')
        self.check_cleanup_lock()
        # All child handles are closed and the non-aliased fixture is owned.
        shutil.rmtree(self.root)
        require(not self.root.exists(), 'CLEANUP_INCOMPLETE')

    def check_cleanup_lock(self) -> None:
        # Independently refuse cleanup if ANY process still holds route.lock.
        lock_path = self.root / 'bin' / 'route.lock'
        if lock_path.exists():
            api = ctypes.WinDLL('kernel32', use_last_error=True)
            api.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                       ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                       ctypes.c_void_p]
            api.CreateFileW.restype = ctypes.c_void_p
            api.CloseHandle.argtypes = [ctypes.c_void_p]
            api.CloseHandle.restype = ctypes.c_int
            handle = api.CreateFileW(str(lock_path), 0x80000000 | 0x40000000,
                                     0, None, 3, 0x80, None)
            require(handle != ctypes.c_void_p(-1).value, 'CLEANUP_LOCK_BUSY')
            require(api.CloseHandle(handle) != 0, 'CLEANUP_LOCK_CLOSE')


def callbacks(case: Case) -> None:
    case.run('Arm')
    case.status('armed', 'B')
    first = case.child('Callback', hold=True)
    second = case.child('Callback')
    first.send('go')
    first.expect('consumed')  # production lock is held, tombstone already flushed
    consumed = case.marker_bytes()
    case.status('consumed')
    second.send('go')
    second.finish(1)
    require(case.marker_bytes() == consumed, 'CONTENDER_CHANGED_MARKER')
    case.no_launch()
    first.send('release')
    first.expect('launch-recorded')
    first.finish(0)
    receipts = list(case.root.glob('launch-*.json'))
    require(len(receipts) == 1, 'LAUNCH_COUNT')
    receipt = json.loads(receipts[0].read_text(encoding='utf-8'))
    require(receipt == {'pid': first.process.pid, 'profile': 'B',
                        'configMatched': True, 'parentUnchanged': True}, 'LAUNCH_RECEIPT')
    case.run('Callback', 1)  # replay after lock release is still refused
    require(len(list(case.root.glob('launch-*.json'))) == 1, 'REPLAY_LAUNCHED')
    require(case.marker_bytes() == consumed, 'REPLAY_CHANGED_MARKER')
    case.run('Probe')
    case.logs(['ROUTE_BUSY', 'LAUNCH_REQUESTED', 'DISPATCH_COMPLETE', 'TARGET_READ_FAILED'])


def concurrent_arm(case: Case) -> None:
    first = case.child('Arm', hold=True)
    second = case.child('Arm', profile='A')
    first.send('go')
    first.expect('armed')  # armer's Launch double holds production lock
    case.status('armed', 'B')
    armed = case.marker_bytes()
    second.send('go')
    second.finish(1)
    require(case.marker_bytes() == armed, 'BUSY_ARM_OVERWROTE')
    first.send('release')
    first.finish(0)
    case.run('Arm', 1, 'A')  # outstanding intent blocks arm even after release
    require(case.marker_bytes() == armed, 'OUTSTANDING_ARM_OVERWROTE')
    case.run('Probe')
    case.no_launch()


def occupied_lock(case: Case) -> None:
    case.run('Arm')
    armed = case.marker_bytes()
    holder = case.child('Lock')
    holder.send('go')
    holder.expect('lock-held')
    try:
        case.check_cleanup_lock()
    except Failure as exc:
        require(str(exc) == 'CLEANUP_LOCK_BUSY', 'WRONG_CLEANUP_REFUSAL')
    else:
        raise Failure('HELD_LOCK_NOT_DETECTED')
    case.run('Arm', 1, 'A')
    case.run('Callback', 1)
    require(case.marker_bytes() == armed, 'LOCKED_MARKER_CHANGED')
    case.no_launch()
    holder.send('release')
    holder.finish(0)
    case.run('Probe')
    case.status('armed', 'B')
    case.logs(['ROUTE_BUSY'])


def timeout_control(case: Case) -> None:
    holder = case.child('Lock')
    holder.send('go')
    holder.expect('lock-held')
    try:
        holder.expect('result', timeout=0.25)  # deliberately withhold release
    except Failure as exc:
        require(str(exc) == 'BARRIER_TIMEOUT', 'WRONG_TIMEOUT_FAILURE')
    else:
        raise Failure('TIMEOUT_NOT_DETECTED')
    # Recover explicitly; normal cleanup remains verifiable, no crash claim.
    holder.send('release')
    holder.finish(0)
    case.run('Probe')
    case.no_launch()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shell', choices=('powershell', 'pwsh', 'both'), default='both')
    args = parser.parse_args()
    require(os.name == 'nt', 'WINDOWS_ONLY')
    require(sys.version_info >= (3, 12), 'PYTHON_VERSION')
    names = ('powershell', 'pwsh') if args.shell == 'both' else (args.shell,)
    shells = [(name, shutil.which(name)) for name in names]
    require(all(path for _, path in shells), 'SHELL_MISSING')
    suite_deadline = time.monotonic() + SUITE_SECONDS
    total = 0
    for name, shell in shells:
        for label, test in (('callbacks', callbacks), ('concurrent-arm', concurrent_arm),
                            ('occupied-lock', occupied_lock), ('timeout-control', timeout_control)):
            case = Case(shell, suite_deadline)
            try:
                case.run('Preflight')
                test(case)
                case.stable_metadata()
            finally:
                case.cleanup()
            total += 1
            print(f'PASS {name} {label}: real metadata IO / synthetic launch only', flush=True)
    require(time.monotonic() <= suite_deadline, 'SUITE_DEADLINE')
    print(f'PASS Q1: {total} cases; owned fixtures removed; no Desktop qualification', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Failure, OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        # Do not dump child output, inherited environment or caller paths.
        label = str(exc) if isinstance(exc, Failure) else type(exc).__name__
        print('FAIL Q1: ' + label, file=sys.stderr)
        sys.exit(1)
