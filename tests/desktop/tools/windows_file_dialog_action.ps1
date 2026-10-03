param(
    [Parameter(Mandatory = $true)][ValidateSet('select', 'cancel')][string] $Action,
    [Parameter(Mandatory = $true)][long] $OwnerHwnd,
    [Parameter(Mandatory = $true)][int] $OwnerPid,
    [Parameter(Mandatory = $true)][ValidateRange(1000, 15000)][int] $TimeoutMilliseconds,
    [Parameter(Mandatory = $true)][string] $FixtureRoot
)

$ErrorActionPreference = 'Stop'
Add-Type -ErrorAction Stop -Path (Join-Path $PSScriptRoot 'WindowsFileDialogUia.cs') -ReferencedAssemblies @(
    'UIAutomationClient', 'UIAutomationTypes', 'System.Web.Extensions', 'System'
)
[WindowsFileDialogUia]::Act($Action, $OwnerHwnd, $OwnerPid, $TimeoutMilliseconds, $FixtureRoot)
