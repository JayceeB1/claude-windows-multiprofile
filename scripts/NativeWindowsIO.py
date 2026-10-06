"""Windows COM/registry primitives; imported lazily, never used by default preview.

No package uninstall, classic claude key rewrite or UserChoice mutation. Registry
ownership is limited to two new router namespaces and one RegisteredApplications
value. Existing namespaces are refused, not adopted. Not yet runtime-qualified.
"""
from contextlib import contextmanager
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import tempfile
import winreg

import SharedMemoryPlan as bridge

ROUTER = r'Software\Classes\ClaudeShim.claude'
CAPABILITIES = r'Software\ClaudeShim'
REGISTERED = r'Software\RegisteredApplications'
VALUE = 'ClaudeShim'
MUTEX_NAME = r'Local\ClaudeSharedWorkspaceRouter-v2'
MAX_KEYS = 32
MAX_VALUES = 64


def windows_root():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetWindowsDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    api.GetWindowsDirectoryW.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    size = api.GetWindowsDirectoryW(buffer, len(buffer))
    if not size or size >= len(buffer):
        raise bridge.BridgeError('WINDOWS_DIRECTORY_UNAVAILABLE')
    return bridge.safe_path(buffer.value, directory=True)


@contextmanager
def registry_guard():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.ReleaseMutex.argtypes = [wintypes.HANDLE]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise bridge.BridgeError('ROUTER_MUTEX_UNAVAILABLE')
    acquired = False
    try:
        outcome = api.WaitForSingleObject(handle, 0)
        if outcome not in (0, 0x80):
            raise bridge.BridgeError('ROUTER_MUTEX_BUSY')
        acquired = True
        yield
    finally:
        if acquired:
            api.ReleaseMutex(handle)
        api.CloseHandle(handle)


def registry_snapshot():
    """Read only router-owned candidate namespaces, never auth/session stores."""
    count = [0, 0]
    def tree(path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ)
        except FileNotFoundError:
            return None
        with key:
            count[0] += 1
            if count[0] > MAX_KEYS:
                raise bridge.BridgeError('ROUTER_REGISTRY_LIMIT')
            values, children = {}, {}
            index = 0
            while True:
                try:
                    name, value, kind = winreg.EnumValue(key, index)
                except OSError as error:
                    if error.winerror == 259:
                        break
                    raise
                count[1] += 1
                if count[1] > MAX_VALUES or kind != winreg.REG_SZ or not isinstance(value, str) or len(value) > 4096:
                    raise bridge.BridgeError('ROUTER_REGISTRY_VALUE_REFUSED')
                values[name] = value
                index += 1
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(key, index)
                except OSError as error:
                    if error.winerror == 259:
                        break
                    raise
                children[name] = tree(path + '\\' + name)
                index += 1
            return {'values': values, 'children': children}
    registered = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTERED, 0, winreg.KEY_READ) as key:
            try:
                value, kind = winreg.QueryValueEx(key, VALUE)
                if kind != winreg.REG_SZ or not isinstance(value, str) or len(value) > 4096:
                    raise bridge.BridgeError('ROUTER_REGISTRY_VALUE_REFUSED')
                registered = value
            except FileNotFoundError:
                pass
    except FileNotFoundError:
        pass
    return {'router': tree(ROUTER), 'capabilities': tree(CAPABILITIES), 'registered_value': registered}


def empty_registry(snapshot):
    return snapshot == {'router': None, 'capabilities': None, 'registered_value': None}


def desired_registry(install):
    powershell = str(windows_root() / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    shim = str(bridge.safe_path(install / 'bin/ClaudeOpenShim.ps1'))
    conhost = str(windows_root() / 'System32/conhost.exe')
    command = f'"{conhost}" --headless "{powershell}" -NoProfile -ExecutionPolicy Bypass -File "{shim}" -Url "%1"'
    leaf = lambda values, children=None: {'values': values, 'children': children or {}}
    return {'router': leaf({'': 'URL:Claude Protocol', 'URL Protocol': ''},
                          {'shell': leaf({}, {'open': leaf({}, {'command': leaf({'': command})})})}),
            'capabilities': leaf({}, {'Capabilities': leaf({
                'ApplicationName': 'Claude Login Router',
                'ApplicationDescription': 'Explicit named-profile Claude login router'},
                {'URLAssociations': leaf({'claude': 'ClaudeShim.claude'})})}),
            'registered_value': r'Software\ClaudeShim\Capabilities'}


def _install_registry(expected_before, desired):
    if not empty_registry(expected_before) or registry_snapshot() != expected_before:
        raise bridge.BridgeError('ROUTER_REGISTRY_UNOWNED_OR_CHANGED')
    def write(path, node):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as key:
            for name, value in node['values'].items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, child in node['children'].items():
            write(path + '\\' + name, child)
    write(ROUTER, desired['router'])
    write(CAPABILITIES, desired['capabilities'])
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTERED, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, desired['registered_value'])
    if registry_snapshot() != desired:
        raise bridge.BridgeError('ROUTER_REGISTRY_READBACK_FAILED')


def partial_owned(snapshot, desired):
    def subset(actual, planned):
        if actual is None:
            return True
        if planned is None:
            return False
        return all(name in planned['values'] and planned['values'][name] == value
                   for name, value in actual['values'].items()) and all(
                       name in planned['children'] and subset(child, planned['children'][name])
                       for name, child in actual['children'].items())
    return subset(snapshot['router'], desired['router']) and subset(snapshot['capabilities'], desired['capabilities']) and \
        snapshot['registered_value'] in (None, desired['registered_value'])


def _restore_registry(before, expected, allow_partial=False):
    current = registry_snapshot()
    if allow_partial and partial_owned(current, expected):
        expected = current
    if not empty_registry(before) or current != expected:
        raise bridge.BridgeError('ROUTER_REGISTRY_RESTORE_CONFLICT')
    def remove(path, node):
        for name, child in node['children'].items():
            remove(path + '\\' + name, child)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    if expected['router'] is not None:
        remove(ROUTER, expected['router'])
    if expected['capabilities'] is not None:
        remove(CAPABILITIES, expected['capabilities'])
    if expected['registered_value'] is not None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTERED, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE)
    # Never delete the shared RegisteredApplications key or unrelated values.
    if registry_snapshot() != before:
        raise bridge.BridgeError('ROUTER_REGISTRY_RESTORE_READBACK_FAILED')


def install_registry(expected_before, desired):
    with registry_guard():
        _install_registry(expected_before, desired)


def restore_registry(before, expected, allow_partial=False):
    with registry_guard():
        _restore_registry(before, expected, allow_partial)


def shortcut_bytes(specification, staging):
    """Create/read back one COM shortcut in owned staging, then admit its bytes."""
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
$s = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
namespace NativeLinks {
 [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IShellLinkW {
  void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int n, IntPtr data, uint flags);
  void GetIDList(out IntPtr p); void SetIDList(IntPtr p);
  void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int n);
  void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string p);
  void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int n);
  void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string p);
  void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int n);
  void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string p);
  void GetHotkey(out short p); void SetHotkey(short p);
  void GetShowCmd(out int p); void SetShowCmd(int p);
  void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int n, out int index);
  void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string p, int index);
  void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string p, uint reserved);
  void Resolve(IntPtr window, uint flags);
  void SetPath([MarshalAs(UnmanagedType.LPWStr)] string p);
 }
 public static class Link {
  static object NewLink() { return Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046"))); }
  public static bool SaveRead(string path, string target, string args, string dir, string icon, string desc) {
   object created = NewLink();
   try {
    IShellLinkW c = (IShellLinkW)created;
    c.SetPath(target); c.SetArguments(args); c.SetWorkingDirectory(dir);
    c.SetIconLocation(icon, 0); c.SetDescription(desc);
    ((IPersistFile)created).Save(path, true);
   } finally { Marshal.FinalReleaseComObject(created); }
   object loaded = NewLink();
   try {
    ((IPersistFile)loaded).Load(path, 0);
    IShellLinkW r = (IShellLinkW)loaded;
    StringBuilder t = new StringBuilder(32768), a = new StringBuilder(32768),
      d = new StringBuilder(32768), i = new StringBuilder(32768), s = new StringBuilder(32768);
    int index;
    r.GetPath(t, t.Capacity, IntPtr.Zero, 4); r.GetArguments(a, a.Capacity);
    r.GetWorkingDirectory(d, d.Capacity); r.GetIconLocation(i, i.Capacity, out index);
    r.GetDescription(s, s.Capacity);
    return String.Equals(t.ToString(), target, StringComparison.OrdinalIgnoreCase) &&
      String.Equals(a.ToString(), args, StringComparison.Ordinal) &&
      String.Equals(d.ToString(), dir, StringComparison.OrdinalIgnoreCase) &&
      String.Equals(i.ToString(), icon, StringComparison.OrdinalIgnoreCase) && index == 0 &&
      String.Equals(s.ToString(), desc, StringComparison.Ordinal);
   } finally { Marshal.FinalReleaseComObject(loaded); }
  }
 }
}
'@
if (-not [NativeLinks.Link]::SaveRead($s.path, $s.target, $s.arguments, $s.directory, $s.icon, $s.description)) {
    throw 'SHORTCUT_READBACK_FAILED'
}
'''
    windows = windows_root()
    powershell = windows / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    launcher = bridge.safe_path(specification['script'])
    data = bridge.safe_path(specification['dataDir'])
    config = bridge.safe_path(specification['configDir'])
    staging = bridge.safe_path(staging, directory=True)
    with tempfile.TemporaryDirectory(prefix='.shortcut-', dir=staging) as temporary:
        path = Path(temporary) / 'owned.lnk'
        payload = {'path': str(path), 'target': str(windows / 'System32/wscript.exe'),
                   'arguments': f'"{launcher}" "{data}" "{config}"',
                   'directory': str(launcher.parent), 'icon': str(windows / 'System32/shell32.dll'),
                   'description': 'Claude Desktop - ' + specification['role'] + (' existing' if specification['role'] == 'A' else ' added')}
        try:
            result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand',
                                     base64.b64encode(script.encode('utf-16-le')).decode('ascii')],
                                    input=json.dumps(payload).encode('utf-8'), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise bridge.BridgeError('SHORTCUT_COM_TIMEOUT') from None
        if result.returncode != 0:
            raise bridge.BridgeError('SHORTCUT_COM_OR_READBACK_FAILED')
        raw = bridge.read_optional(path)
        if raw is None:
            raise bridge.BridgeError('SHORTCUT_MISSING')
        return raw


@contextmanager
def routing_guard(path):
    """Interop with the PowerShell router's FileShare.None; never unlink its lock."""
    path = bridge.safe_path(path)
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handle = api.CreateFileW(str(path), 0x80000000 | 0x40000000, 0, None, 4, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise bridge.BridgeError('ROUTER_BUSY_OR_LOCK_UNAVAILABLE')
    try:
        yield
    finally:
        api.CloseHandle(handle)
