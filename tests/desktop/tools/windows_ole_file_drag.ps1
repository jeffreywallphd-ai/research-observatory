param(
    [Parameter(Mandatory = $true)][string] $RequestJson
)

$ErrorActionPreference = 'Stop'
[Console]::Error.WriteLine('ole-wrapper-start')
$request = Get-Content -LiteralPath $RequestJson -Raw | ConvertFrom-Json
if ($null -eq $request.sourcePaths -or $request.sourcePaths.Count -lt 1 -or $request.sourcePaths.Count -gt 4) {
    throw 'drag-request-invalid'
}
$paths = [string[]] $request.sourcePaths
foreach ($path in $paths) {
    if (-not [System.IO.Path]::IsPathRooted($path) -or -not (Test-Path -LiteralPath $path)) {
        throw 'drag-source-unavailable'
    }
}
Add-Type -Path (Join-Path $PSScriptRoot 'WindowsOleFileDrag.cs') -ReferencedAssemblies @(
    'System.Windows.Forms', 'System.Drawing', 'System'
)
[Console]::Error.WriteLine('ole-wrapper-compiled')
[WindowsOleFileDrag]::Run(
    $paths,
    [int] $request.targetX,
    [int] $request.targetY,
    [long] $request.expectedRootHwnd,
    [int] $request.timeoutMilliseconds
)
