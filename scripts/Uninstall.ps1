<#
.SYNOPSIS
    Explicit receipt-owned removal candidate (IMPLEMENTED_NOT_TESTED).
.DESCRIPTION
    Use the preview-first SharedWorkspace.py entry. The native candidate preserves
    A routing and the official Claude package; native removal is not qualified yet.
    Legacy name-derived deletion/registry restoration is deliberately disabled.
#>
[CmdletBinding()]
param(
    [string[]]$Profile,
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'ClaudeProfiles'),
    [switch]$RemoveData,
    [switch]$KeepRouting,
    [switch]$Native,
    [switch]$Rollback,
    [switch]$Approved,
    [switch]$WritersClosed,
    [switch]$ApproveProtocol,
    [string]$PythonExecutable = 'python'
)
$ErrorActionPreference = 'Stop'
if ($Native) {
    if (-not $Approved -or -not $WritersClosed -or $Profile -or $KeepRouting -or ($Rollback -and $RemoveData) -or ($ApproveProtocol -and -not $Rollback)) {
        throw 'NATIVE_APPROVAL_AND_EXPLICIT_B_OPERATION_REQUIRED'
    }
    $python = Get-Command $PythonExecutable -CommandType Application -ErrorAction Stop
    if ($python.Source -like '*\Microsoft\WindowsApps\*') { throw 'PYTHON_RUNTIME_REQUIRED' }
    $entry = Join-Path $PSScriptRoot 'SharedWorkspace.py'
    $action = if ($Rollback) { 'native-rollback' } else { 'native-remove-b' }
    $arguments = @('-B', $entry, $action, '--install-dir', $InstallDir, '--approved', '--writers-closed')
    if ($RemoveData) { $arguments += '--delete-owned-b-data' }
    if ($ApproveProtocol) { $arguments += '--approve-protocol' }
    & $python.Source @arguments
    if ($LASTEXITCODE -ne 0) { throw 'NATIVE_WORKSPACE_OPERATION_REFUSED' }
    return
}
throw 'NATIVE_REMOVE_NOT_ADMITTED: no data, shortcut, registry or package changes were made.'
