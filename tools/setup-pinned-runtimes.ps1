#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$RepoRoot = (Get-Location).Path,
    [switch]$PlanOnly,
    [switch]$RunBootstrap
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function Read-ToolOutput([string]$Executable, [string[]]$ToolArguments) {
    $output = @(& $Executable @ToolArguments 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Tool failed: $Executable $($ToolArguments -join ' ')`n$($output -join "`n")" }
    return ($output -join "`n").Trim()
}
function Invoke-Checked([string]$Executable, [string[]]$ToolArguments) {
    & $Executable @ToolArguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Executable $($ToolArguments -join ' ')" }
}
function Require-Version([string]$Executable, [string]$Expected, [string]$Name) {
    $actual = Read-ToolOutput $Executable @('--version')
    $version = [regex]::Match($actual, '(?<![\d.])\d+\.\d+\.\d+[0-9A-Za-z.+-]*')
    if (-not $version.Success -or $version.Value -cne $Expected) {
        throw "$Name has the wrong version ($actual); expected $Expected. Existing files are preserved."
    }
}

try {
    $repo = (Resolve-Path -LiteralPath $RepoRoot).ProviderPath
    foreach ($relative in @('runtime-versions.json', '.node-version', '.python-version', 'package.json', 'bootstrap.cmd', 'tools/bootstrap.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $repo $relative) -PathType Leaf)) {
            throw "Not a Research Observatory project root: missing $relative. Pass the fork root as -RepoRoot."
        }
    }
    $contract = Get-Content -LiteralPath (Join-Path $repo 'runtime-versions.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $package = Get-Content -LiteralPath (Join-Path $repo 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $nodePin = [string]$contract.runtimes.node.version
    $pythonPin = [string]$contract.runtimes.python.version
    $pnpmPin = [string]$contract.package_managers.pnpm.version
    $uvPin = [string]$contract.package_managers.uv.version
    if ($nodePin -ne '24.19.0' -or $pythonPin -ne '3.14.6' -or $pnpmPin -ne '11.20.0' -or $uvPin -ne '0.12.2') {
        throw 'This helper supports only the reviewed Node24.19.0/Python3.14.6/pnpm11.20.0/uv0.12.2 contract; it will not change project pins.'
    }
    if ((Get-Content -LiteralPath (Join-Path $repo '.node-version') -Raw).Trim() -ne $nodePin -or
        (Get-Content -LiteralPath (Join-Path $repo '.python-version') -Raw).Trim() -ne $pythonPin -or
        $package.packageManager -ne "pnpm@$pnpmPin") { throw 'Project runtime declarations disagree; no installation was attempted.' }
    $architecture = $env:PROCESSOR_ARCHITECTURE
    if ($env:PROCESSOR_ARCHITEW6432) { $architecture = $env:PROCESSOR_ARCHITEW6432 }
    if ($env:OS -ne 'Windows_NT' -or $architecture -ne 'AMD64') { throw 'This helper supports Windows x64 only.' }
    $local = Join-Path $repo '.local'
    $toolchains = Join-Path $local 'toolchains'
    $downloads = Join-Path $local 'downloads'
    $nodeRoot = Join-Path $toolchains "node-v$nodePin-win-x64"
    $nodeExe = Join-Path $nodeRoot 'node.exe'
    $corepack = Join-Path $nodeRoot 'corepack.cmd'
    $venv = Join-Path $repo '.venv'
    $pythonExe = Join-Path $venv 'Scripts/python.exe'
    $pythonStore = Join-Path $toolchains 'python'
    $corepackHome = Join-Path $toolchains 'corepack'
    foreach ($path in @($repo, $local, $toolchains, $downloads, $nodeRoot, $venv, $pythonStore, $corepackHome)) {
        if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing a redirected setup directory: $path. Existing files are preserved."
        }
    }
    if ($PlanOnly) {
        Write-Host "PLAN ONLY: repository $repo"
        Write-Host "Require existing uv $uvPin; preserve/validate existing local Node and .venv."
        Write-Host "Install SHA256-verified Node $nodePin into .local/toolchains if absent."
        Write-Host "Install Python $pythonPin with uv (local store, no bin/registry registration); create .venv only if absent."
        Write-Host "Prepare pnpm $pnpmPin using local Corepack and process-local COREPACK_HOME."
        Write-Host "Existing bootstrap runs only with -RunBootstrap: $RunBootstrap"
        exit 0
    }
    $uv = (Get-Command uv.exe -CommandType Application -ErrorAction Stop).Source
    Require-Version $uv $uvPin 'uv'
    # Reject incompatible or incomplete existing installations before any download.
    if (Test-Path -LiteralPath $nodeRoot) {
        if (-not (Test-Path -LiteralPath $nodeExe -PathType Leaf) -or -not (Test-Path -LiteralPath $corepack -PathType Leaf)) {
            throw 'Existing local Node directory is incomplete; preserved. Move it aside deliberately before rerunning.'
        }
        Require-Version $nodeExe $nodePin 'Existing local Node'
    }
    if (Test-Path -LiteralPath $venv) {
        if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) { throw 'Existing .venv is incomplete; preserved. Move it aside deliberately before rerunning.' }
        Require-Version $pythonExe $pythonPin 'Existing .venv Python'
    }
    $oldPath = $env:PATH
    $oldCorepack = $env:COREPACK_HOME
    $oldPythonStore = $env:UV_PYTHON_INSTALL_DIR
    $oldVenvClear = $env:UV_VENV_CLEAR
    $oldTls = [Net.ServicePointManager]::SecurityProtocol
    Push-Location -LiteralPath $repo
    try {
        if (-not (Test-Path -LiteralPath $nodeRoot)) {
            New-Item -ItemType Directory -Path $toolchains -Force | Out-Null
            New-Item -ItemType Directory -Path $downloads -Force | Out-Null
            $archive = Join-Path $downloads "node-v$nodePin-win-x64.zip"
            $expected = '57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73'
            if (-not (Test-Path -LiteralPath $archive)) {
                [Net.ServicePointManager]::SecurityProtocol = $oldTls -bor [Net.SecurityProtocolType]::Tls12
                Invoke-WebRequest -UseBasicParsing -Uri "https://nodejs.org/download/release/v$nodePin/node-v$nodePin-win-x64.zip" -OutFile $archive
            }
            if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
                throw 'Node archive checksum differs. Archive preserved; no extraction or execution occurred.'
            }
            Expand-Archive -LiteralPath $archive -DestinationPath $toolchains
        }
        Require-Version $nodeExe $nodePin 'Local Node'
        if (-not (Test-Path -LiteralPath $corepack -PathType Leaf)) { throw 'The verified Node installation has no corepack.cmd.' }
        $env:PATH = "$nodeRoot;$oldPath"
        $env:COREPACK_HOME = $corepackHome
        $env:UV_PYTHON_INSTALL_DIR = $pythonStore
        $env:UV_VENV_CLEAR = '0'
        if (-not (Test-Path -LiteralPath $venv)) {
            Invoke-Checked $uv @('python', 'install', '--no-bin', '--no-registry', '--install-dir', $pythonStore, $pythonPin)
            $managedPython = Read-ToolOutput $uv @('python', 'find', '--managed-python', $pythonPin)
            Require-Version $managedPython $pythonPin 'Managed Python'
            if (Test-Path -LiteralPath $venv) { throw '.venv appeared during setup; preserved. Rerun to validate it.' }
            Invoke-Checked $uv @('venv', '--python', $managedPython, $venv)
        }
        Require-Version $pythonExe $pythonPin 'Local Python'
        Invoke-Checked $corepack @('prepare', "pnpm@$pnpmPin", '--activate')
        $actualPnpm = Read-ToolOutput $corepack @('pnpm', '--version')
        if ($actualPnpm -ne $pnpmPin) { throw "pnpm $actualPnpm was selected; expected $pnpmPin." }
        Write-Host "Pinned runtime prerequisites ready: Node $nodePin; Python $pythonPin; pnpm $pnpmPin."
        if ($RunBootstrap) {
            Invoke-Checked (Join-Path $repo 'bootstrap.cmd') @()
        } else {
            Write-Host 'Next, run .\bootstrap.cmd from the fork root to install locked dependencies and run the existing smoke gate.'
        }
    } finally {
        Pop-Location
        $env:PATH = $oldPath
        $env:COREPACK_HOME = $oldCorepack
        $env:UV_PYTHON_INSTALL_DIR = $oldPythonStore
        $env:UV_VENV_CLEAR = $oldVenvClear
        [Net.ServicePointManager]::SecurityProtocol = $oldTls
    }
    exit 0
} catch {
    [Console]::Error.WriteLine("ERROR: " + $_.Exception.Message)
    exit 1
}
