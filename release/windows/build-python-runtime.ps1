param(
    [Parameter(Mandatory = $false)]
    [string]$EnvironmentPrefix = "",

    [Parameter(Mandatory = $false)]
    [string]$OutputArchive = "",

    [Parameter(Mandatory = $false)]
    [string]$InventoryOutput = ""
)

$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $EnvironmentPrefix) {
    $EnvironmentPrefix = $env:CONDA_PREFIX
}
if (-not $OutputArchive) {
    $OutputArchive = Join-Path $repositoryRoot "dist\runtime\RASP5-python-3.6.13-windows-x86_64.zip"
}
if (-not $InventoryOutput) {
    $InventoryOutput = Join-Path $repositoryRoot "release\PYTHON_RUNTIME_PACKAGES.csv"
}

$condaPack = Get-Command conda-pack -ErrorAction SilentlyContinue
if (-not $condaPack) {
    throw "conda-pack is not installed. Install it in a separate build environment; do not modify the validated RASP runtime in place."
}
if (-not $EnvironmentPrefix -or -not (Test-Path -LiteralPath $EnvironmentPrefix -PathType Container)) {
    throw "Environment prefix does not exist. Activate the validated RASP environment or pass -EnvironmentPrefix explicitly: $EnvironmentPrefix"
}

$runtimePython = Join-Path $EnvironmentPrefix "python.exe"
if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
    throw "Environment prefix has no python.exe: $EnvironmentPrefix"
}

& $runtimePython `
    (Join-Path $repositoryRoot "tools\build_python_runtime_inventory.py") `
    --prefix $EnvironmentPrefix `
    --output $InventoryOutput
if ($LASTEXITCODE -ne 0) {
    throw "Python runtime inventory failed with exit code $LASTEXITCODE"
}

$output = [System.IO.Path]::GetFullPath($OutputArchive)
$parent = Split-Path -Parent $output
New-Item -ItemType Directory -Force -Path $parent | Out-Null

& $condaPack.Source `
    -p $EnvironmentPrefix `
    -o $output `
    --format zip `
    --force `
    --exclude "**/__pycache__/**" `
    --exclude "*.pyc" `
    --exclude "*.pyo"
if ($LASTEXITCODE -ne 0) {
    throw "conda-pack failed with exit code $LASTEXITCODE"
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $output).Hash
$hashPath = "$output.sha256"
Set-Content -LiteralPath $hashPath -Encoding ASCII -Value "$hash  $([System.IO.Path]::GetFileName($output))"

Write-Host "Python runtime archive created: $output"
Write-Host "SHA256: $hashPath"
Write-Host "Package inventory: $([System.IO.Path]::GetFullPath($InventoryOutput))"
