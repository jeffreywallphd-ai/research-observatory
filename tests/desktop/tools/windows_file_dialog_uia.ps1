param(
    [Parameter(Mandatory = $true)][long] $OwnerHwnd,
    [Parameter(Mandatory = $true)][int] $OwnerPid,
    [Parameter(Mandatory = $true)][int] $TimeoutMilliseconds
)

$ErrorActionPreference = 'Stop'
Add-Type -ErrorAction Stop -Path (Join-Path $PSScriptRoot 'WindowsFileDialogUia.cs') -ReferencedAssemblies @(
    'UIAutomationClient', 'UIAutomationTypes', 'System.Web.Extensions', 'System'
)
[WindowsFileDialogUia]::Inspect($OwnerHwnd, $OwnerPid, $TimeoutMilliseconds)
