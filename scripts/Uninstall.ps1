<#
.SYNOPSIS
    Refuses native cleanup until physical ownership and local acceptance are admitted.
.DESCRIPTION
    Use the preview-first SharedWorkspace.py entry. The fixture removal API preserves
    A routing and the official Claude package; native removal is not qualified yet.
    Legacy name-derived deletion/registry restoration is deliberately disabled.
#>
[CmdletBinding()]
param(
    [string[]]$Profile,
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'ClaudeProfiles'),
    [switch]$RemoveData,
    [switch]$KeepRouting
)
$ErrorActionPreference = 'Stop'
throw 'NATIVE_REMOVE_NOT_ADMITTED: no data, shortcut, registry or package changes were made.'
