# Start Smart Shopper Option A: full local E2E (Telegram -> Kafka -> agents -> Telegram)
# Usage:
#   .\scripts\start_e2e_local.ps1
#   .\scripts\start_e2e_local.ps1 -LaunchAll
#   .\scripts\start_e2e_local.ps1 -LaunchAll -SkipInfra

param(
    [switch]$LaunchAll,
    [switch]$SkipInfra
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Test-EnvKey {
    param([string]$Name)
    $line = Get-Content .env | Where-Object { $_ -match "^\s*$Name=" } | Select-Object -First 1
    if (-not $line) { return $false }
    $value = ($line -split "=", 2)[1].Trim().Trim('"')
    return [bool]$value
}

if (-not (Test-Path .env)) {
    Write-Host "Missing .env - run: copy .env.example .env" -ForegroundColor Red
    exit 1
}

$missing = @()
if (-not (Test-EnvKey "TELEGRAM_BOT_TOKEN")) { $missing += "TELEGRAM_BOT_TOKEN" }
if (-not (Test-EnvKey "KAFKA_BOOTSTRAP_SERVERS")) { $missing += "KAFKA_BOOTSTRAP_SERVERS" }
if ($missing.Count -gt 0) {
    Write-Host "Set these in .env before E2E:" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

if (-not $SkipInfra) {
    Write-Host ""
    Write-Host "=== Starting infrastructure: Kafka, Redis, MongoDB ===" -ForegroundColor Cyan
    docker compose up -d kafka redis mongodb
    Write-Host "Waiting 20s for containers to start..."
    Start-Sleep -Seconds 20
    docker compose ps
    Write-Host "Infrastructure started." -ForegroundColor Green
}

$services = @(
    @{ Name = "NER";          Module = "models.ner.grpc_server";             Port = 8001; Required = $true },
    @{ Name = "Orchestrator"; Module = "agents.orchestrator.service";            Port = 8002; Required = $true },
    @{ Name = "Scraper";      Module = "agents.webscraping.agent";               Port = 8003; Required = $true },
    @{ Name = "Decision";     Module = "agents.decision.service";                Port = 8004; Required = $true },
    @{ Name = "Generator";    Module = "agents.agent_generator.agent";           Port = 8005; Required = $true },
    @{ Name = "Governance";   Module = "agents.governance.agent";                Port = 8006; Required = $false },
    @{ Name = "Ambient";      Module = "agents.ambient_scheduler.scheduler";     Port = 8007; Required = $false },
    @{ Name = "Telegram";     Module = "gateway.telegram_proxy";                 Port = 8008; Required = $true }
)

function Start-ServiceWindow {
    param([hashtable]$Service)

    $command = "Set-Location '$Root'; " +
               "`$env:METRICS_PORT='$($Service.Port)'; " +
               "`$env:PYTHONIOENCODING='utf-8'; " +
               "Write-Host '=== $($Service.Name) METRICS_PORT=$($Service.Port) ===' -ForegroundColor Cyan; " +
               "python -m $($Service.Module)"

    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-Command", $command)
}

Write-Host ""
Write-Host "=== Option A services ===" -ForegroundColor Cyan
foreach ($svc in $services) {
    $tag = if ($svc.Required) { "required" } else { "optional" }
    Write-Host ("  [{0}] METRICS_PORT={1}  python -m {2}" -f $tag, $svc.Port, $svc.Module)
}

if ($LaunchAll) {
    Write-Host ""
    Write-Host "Launching service windows. Wait 60-90s for NER model load..." -ForegroundColor Cyan
    Start-ServiceWindow -Service $services[0]
    Start-Sleep -Seconds 20
    for ($i = 1; $i -lt $services.Count; $i++) {
        Start-ServiceWindow -Service $services[$i]
        Start-Sleep -Seconds 1
    }
    Write-Host ""
    Write-Host "All windows opened. Message your bot on Telegram when NER is ready." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Open one terminal per service, or re-run with:" -ForegroundColor Yellow
    Write-Host "  .\scripts\start_e2e_local.ps1 -LaunchAll" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Test on Telegram ===" -ForegroundColor DarkGray
Write-Host "1. Open https://t.me/Dalil_Souqbot" -ForegroundColor DarkGray
Write-Host "2. Send: Bghit Samsung phone b 3000 dh" -ForegroundColor DarkGray
Write-Host "3. Final product list arrives in 15-60s" -ForegroundColor DarkGray
Write-Host ""
Write-Host "=== Quick check without Telegram ===" -ForegroundColor DarkGray
Write-Host "  python -m scripts.smoke_kafka_flow" -ForegroundColor DarkGray
Write-Host ""
