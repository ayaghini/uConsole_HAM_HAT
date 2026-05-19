param(
    [Parameter(Mandatory = $true)]
    [string]$ToolPath,

    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [Parameter(Mandatory = $false)]
    [int]$DeviceCount = 2,

    [Parameter(Mandatory = $false)]
    [string]$SerialMode = "GUID",

    [Parameter(Mandatory = $false)]
    [string]$LogDir = ".\logs"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ToolPath)) {
    throw "cp210xsmt not found: $ToolPath"
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Configuration file not found: $ConfigPath"
}

if ($DeviceCount -lt 1) {
    throw "DeviceCount must be >= 1"
}

if ($SerialMode -notin @("GUID", "LIST")) {
    throw "SerialMode must be GUID or LIST"
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $LogDir "cp2102n-program-$ts.log"

Write-Host "Starting CP2102N program/verify run..."
Write-Host "Tool: $ToolPath"
Write-Host "Config: $ConfigPath"
Write-Host "Expected devices: $DeviceCount"
Write-Host "Log: $logPath"

$args = @(
    "--device-count", "$DeviceCount",
    "--set-and-verify-config", "$ConfigPath"
)

if ($SerialMode -eq "GUID") {
    $args += @("--serial-nums", "GUID")
} else {
    throw "LIST mode is not implemented in this script yet."
}

"=== $(Get-Date -Format s) START ===" | Out-File -FilePath $logPath -Encoding utf8
"Command: `"$ToolPath`" $($args -join ' ')" | Out-File -FilePath $logPath -Append -Encoding utf8

$output = & $ToolPath @args 2>&1
$exitCode = $LASTEXITCODE

$output | Out-File -FilePath $logPath -Append -Encoding utf8
"ExitCode: $exitCode" | Out-File -FilePath $logPath -Append -Encoding utf8
"=== $(Get-Date -Format s) END ===" | Out-File -FilePath $logPath -Append -Encoding utf8

if ($exitCode -ne 0) {
    Write-Error "Programming failed. See log: $logPath"
    exit $exitCode
}

Write-Host "Programming completed successfully. See log: $logPath"
exit 0
