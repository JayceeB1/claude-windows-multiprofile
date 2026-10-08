"""Write the router registration into the REAL per-user registry, from an unpackaged process.

Why this exists: a process running inside an MSIX package (Codex, Claude Desktop and their
children) has HKCU writes and AppData file writes redirected to a private per-package store.
Windows Settings and the protocol picker read the real registry, so keys written from such a
process never appear there. This helper refuses to run unless the current process and none of its
ancestors has a package identity, and writes only the router namespaces already declared in the receipt.

No UserChoice change, no classic `claude` key change, no profile or package operation.
Run it from a PowerShell opened from the Start menu, not from Codex or Claude Desktop.
"""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-dir', type=Path, default=Path.home() / 'ClaudeProfiles')
    parser.add_argument('--apply', action='store_true', help='write the registration (default: check only)')
    parser.add_argument('--approved', action='store_true', help='required together with --apply')
    args = parser.parse_args()
    install = args.install_dir
    report = {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import NativeWindowsIO as windows
        try:
            windows.require_unpackaged_process()
            report['package_context'] = 'UNPACKAGED_TREE'
        except Exception:
            report['package_context'] = 'PACKAGED_TREE'
        receipt = json.loads((install / 'native-ownership.json').read_text(encoding='utf-8'))['record']
        desired = windows.desired_registry(install)
        current = windows.registry_snapshot()
        report.update(receipt_phase=receipt['phase'], receipt_registry_phase=receipt['registry_phase'],
                      receipt_matches_desired=receipt['registry_after'] == desired,
                      real_registry_empty=windows.empty_registry(current),
                      real_registry_matches_desired=current == desired,
                      router_exe=(install / 'bin' / 'ClaudeLoginRouter.exe').is_file())
        if args.apply:
            if report['package_context'] != 'UNPACKAGED_TREE':
                raise PermissionError('REFUSED_PACKAGED_PROCESS')
            if not args.approved:
                raise PermissionError('REFUSED_APPROVAL_REQUIRED')
            if not report['receipt_matches_desired'] or receipt['registry_phase'] != 'applied':
                raise PermissionError('REFUSED_RECEIPT_MISMATCH')
            if not report['real_registry_empty']:
                raise PermissionError('REFUSED_REGISTRY_NOT_EMPTY' if not report['real_registry_matches_desired']
                                      else 'ALREADY_REGISTERED')
            windows.install_registry(current, desired)
            report['applied'] = windows.registry_snapshot() == desired
    except PermissionError as error:
        report['result'] = str(error)
    except Exception as error:  # report the class, never hide the failure
        report['error'] = type(error).__name__
    print(json.dumps(report, indent=2))
    return 0 if report.get('applied') or 'result' not in report and 'error' not in report else 2


if __name__ == '__main__':
    raise SystemExit(main())
