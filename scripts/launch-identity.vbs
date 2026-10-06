' Runs Launch-ClaudeIdentity.ps1 fully hidden (no console flash).
' The .ps1 files are expected to live next to this .vbs file.
'
' Usage:  wscript.exe launch-identity.vbs "<profile-data-dir>" "<claude-config-dir or empty>" "<app-id>" "<icon.ico>"

Set args = WScript.Arguments
If args.Count < 4 Then
    WScript.Echo "Usage: launch-identity.vbs ""<profile-data-dir>"" ""<claude-config-dir>"" ""<app-id>"" ""<icon.ico>"""
    WScript.Quit 1
End If

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = fso.BuildPath(scriptDir, "Launch-ClaudeIdentity.ps1")

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """" & _
      " -ProfileDir """ & args(0) & """" & _
      " -AppId """ & args(2) & """" & _
      " -IconPath """ & args(3) & """"
If Len(args(1)) > 0 Then
    cmd = cmd & " -ConfigDir """ & args(1) & """"
End If

' 0 = hidden window, False = don't wait.
CreateObject("WScript.Shell").Run cmd, 0, False
