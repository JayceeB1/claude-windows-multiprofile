<#
.SYNOPSIS
    Gives one Claude Desktop profile its own taskbar button and icon.
.DESCRIPTION
    Both profiles run the same packaged executable, so Windows groups their windows
    under one taskbar button (the package identity) and shows one icon. This module
    sets an explicit AppUserModelID and window icons on the windows of ONE profile,
    found through its --user-data-dir. Windows then shows a separate button, and a
    pinned shortcut carrying the same AppUserModelID owns it.
    Nothing is injected into Claude: only documented shell window properties and
    WM_SETICON are used, from a separate process. The change lives as long as the
    window; Watch-ClaudeWindowIdentity re-applies it if the window is recreated.
.NOTES
    Windows PowerShell 5.1 and PowerShell 7, no admin rights. Dot-sourcing defines
    functions only. The shortcut helper writes only the shortcut it is given.
#>
[CmdletBinding()]
param()

if (-not ('ClaudeIdentityNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class ClaudeIdentityNative {
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc p, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, uint cmd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr LoadImage(IntPtr hi, string name, uint type, int cx, int cy, uint flags);
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("shell32.dll")] static extern int SHGetPropertyStoreForWindow(IntPtr h, ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object ps);
    [DllImport("ole32.dll")] static extern int PropVariantClear(ref PropVariant v);

    [StructLayout(LayoutKind.Sequential, Pack = 4)] public struct PropertyKey { public Guid fmtid; public uint pid; }
    [StructLayout(LayoutKind.Explicit, Size = 24)] public struct PropVariant {
        [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; [FieldOffset(16)] public IntPtr q; }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPropertyStore {
        [PreserveSig] int GetCount(out uint c);
        [PreserveSig] int GetAt(uint i, out PropertyKey k);
        [PreserveSig] int GetValue(ref PropertyKey k, out PropVariant v);
        [PreserveSig] int SetValue(ref PropertyKey k, ref PropVariant v);
        [PreserveSig] int Commit();
    }

    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellLinkW {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int n, IntPtr fd, uint fl);
        void GetIDList(out IntPtr p); void SetIDList(IntPtr p);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int n);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int n);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int n);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
        void GetHotkey(out short h); void SetHotkey(short h);
        void GetShowCmd(out int c); void SetShowCmd(int c);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int n, out int i);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s, int i);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s, uint r);
        void Resolve(IntPtr h, uint f);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
    }
    [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPersistFile {
        void GetClassID(out Guid c); [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint m);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string f, [MarshalAs(UnmanagedType.Bool)] bool remember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string f);
    }
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class ShellLinkObject { }

    static PropertyKey AppId() {
        return new PropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
    }

    static string Read(IPropertyStore store) {
        PropertyKey k = AppId(); PropVariant v;
        if (store.GetValue(ref k, out v) != 0) return null;
        string s = v.vt == 31 ? Marshal.PtrToStringUni(v.p) : null;
        PropVariantClear(ref v);
        return s;
    }

    static void Write(IPropertyStore store, string appId) {
        PropertyKey k = AppId();
        PropVariant v = new PropVariant(); v.vt = 31; v.p = Marshal.StringToCoTaskMemUni(appId);
        int hr = store.SetValue(ref k, ref v); PropVariantClear(ref v);
        if (hr != 0) Marshal.ThrowExceptionForHR(hr);
        hr = store.Commit(); if (hr != 0) Marshal.ThrowExceptionForHR(hr);
    }

    /// Visible, titled, unowned top-level windows of one process.
    public static IntPtr[] Windows(uint pid) {
        var found = new List<IntPtr>();
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p);
            if (p != pid || !IsWindowVisible(h) || GetWindow(h, 4) != IntPtr.Zero) return true; // 4 = GW_OWNER
            var sb = new StringBuilder(8); GetWindowText(h, sb, 8);
            if (sb.Length > 0) found.Add(h);
            return true;
        }, IntPtr.Zero);
        return found.ToArray();
    }

    public static string WindowAppId(IntPtr hwnd) {
        Guid iid = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"); object o;
        if (SHGetPropertyStoreForWindow(hwnd, ref iid, out o) != 0) return null;
        return Read((IPropertyStore)o);
    }

    /// Returns true when something had to be changed on this window.
    public static bool ApplyToWindow(IntPtr hwnd, string appId, IntPtr big, IntPtr small) {
        Guid iid = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"); object o;
        int hr = SHGetPropertyStoreForWindow(hwnd, ref iid, out o);
        if (hr != 0) Marshal.ThrowExceptionForHR(hr);
        var store = (IPropertyStore)o;
        bool changed = false;
        if (!string.Equals(Read(store), appId, StringComparison.Ordinal)) { Write(store, appId); changed = true; }
        if (big != IntPtr.Zero) SendMessage(hwnd, 0x80, (IntPtr)1, big);     // WM_SETICON, ICON_BIG
        if (small != IntPtr.Zero) SendMessage(hwnd, 0x80, (IntPtr)0, small); // WM_SETICON, ICON_SMALL
        return changed;
    }

    public static IntPtr LoadIcon(string path, int size) {
        return LoadImage(IntPtr.Zero, path, 1, size, size, 0x10); // IMAGE_ICON, LR_LOADFROMFILE
    }

    /// Writes (or rewrites) a .lnk with an explicit AppUserModelID, so a pinned copy owns the taskbar button.
    public static void WriteShortcut(string lnk, string target, string arguments, string workDir,
                                     string iconPath, string description, string appId) {
        var link = (IShellLinkW)new ShellLinkObject();
        link.SetPath(target); link.SetArguments(arguments); link.SetWorkingDirectory(workDir);
        link.SetIconLocation(iconPath, 0); link.SetDescription(description); link.SetShowCmd(1);
        if (!string.IsNullOrEmpty(appId)) Write((IPropertyStore)link, appId);
        ((IPersistFile)link).Save(lnk, true);
    }

    public static string ShortcutAppId(string lnk) {
        var link = (IShellLinkW)new ShellLinkObject();
        ((IPersistFile)link).Load(lnk, 0);
        return Read((IPropertyStore)link);
    }
}
'@
}

function Test-ClaudeCommandLine {
    <# True for the MAIN process of the profile whose data dir is $DataDir (not a --type= child). #>
    param([string]$CommandLine, [string]$DataDir)
    if ([string]::IsNullOrWhiteSpace($CommandLine) -or [string]::IsNullOrWhiteSpace($DataDir)) { return $false }
    if ($CommandLine -match '(^|\s)--type=') { return $false }
    $wanted = $DataDir.TrimEnd('\', '/')
    foreach ($m in [regex]::Matches($CommandLine, '--user-data-dir=(?:"(?<q>[^"]*)"|(?<u>\S+))')) {
        $value = if ($m.Groups['q'].Success) { $m.Groups['q'].Value } else { $m.Groups['u'].Value }
        if ($value.TrimEnd('\', '/') -ieq $wanted) { return $true }
    }
    return $false
}

function Get-ClaudeProfileProcessId {
    param([string]$DataDir)
    $match = Get-CimInstance Win32_Process -Filter "Name='Claude.exe'" -ErrorAction SilentlyContinue |
        Where-Object { Test-ClaudeCommandLine -CommandLine $_.CommandLine -DataDir $DataDir } |
        Select-Object -First 1
    if ($match) { return [uint32]$match.ProcessId }
    return $null
}

function Set-ClaudeWindowIdentity {
    <# Applies AppId + icons to every eligible window of one process. Returns the number of windows changed. #>
    param([Parameter(Mandatory)][uint32]$ProcessId, [Parameter(Mandatory)][string]$AppId,
          [Parameter(Mandatory)][string]$IconPath, [hashtable]$Seen = @{})
    if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) { throw 'IconPath is missing.' }
    $big = [ClaudeIdentityNative]::LoadIcon($IconPath, 64)
    $small = [ClaudeIdentityNative]::LoadIcon($IconPath, 16)
    $changed = 0
    foreach ($hwnd in [ClaudeIdentityNative]::Windows($ProcessId)) {
        $key = $hwnd.ToInt64()
        # A window already seen with the right id keeps its icon; a new or drifted one is redone.
        if ($Seen.ContainsKey($key) -and ([ClaudeIdentityNative]::WindowAppId($hwnd) -ceq $AppId)) { continue }
        if ([ClaudeIdentityNative]::ApplyToWindow($hwnd, $AppId, $big, $small)) { $changed++ }
        $Seen[$key] = $true
    }
    return $changed
}

function Watch-ClaudeWindowIdentity {
    <# Waits for the profile's window, applies the identity, and keeps it until the profile exits. #>
    param([Parameter(Mandatory)][string]$DataDir, [Parameter(Mandatory)][string]$AppId,
          [Parameter(Mandatory)][string]$IconPath, [int]$StartupSeconds = 120)
    $seen = @{}
    $deadline = (Get-Date).AddSeconds($StartupSeconds)
    $processId = $null
    while (-not $processId -and (Get-Date) -lt $deadline) {
        $processId = Get-ClaudeProfileProcessId -DataDir $DataDir
        if (-not $processId) { Start-Sleep -Milliseconds 500 }
    }
    if (-not $processId) { return }
    while ($true) {
        if (-not (Get-Process -Id $processId -ErrorAction SilentlyContinue)) { return }
        try { $null = Set-ClaudeWindowIdentity -ProcessId $processId -AppId $AppId -IconPath $IconPath -Seen $seen } catch { }
        # Fast while the window is appearing, slow once settled.
        Start-Sleep -Milliseconds $(if ($seen.Count -eq 0) { 200 } else { 2000 })
    }
}

function New-ClaudeIdentityShortcut {
    <# Creates the shortcut (icon + AppUserModelID) that launches the identity launcher. #>
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Target, [string]$Arguments = '',
          [string]$WorkingDirectory = '', [Parameter(Mandatory)][string]$IconPath,
          [string]$AppId = '', [string]$Description = '')
    [ClaudeIdentityNative]::WriteShortcut($Path, $Target, $Arguments, $WorkingDirectory, $IconPath, $Description, $AppId)
}
