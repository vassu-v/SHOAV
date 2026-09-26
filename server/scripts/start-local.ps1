<#
.SYNOPSIS
  Run the Auto Browser controller natively on Windows (no Docker), visible Chromium.

.EXAMPLE
  .\scripts\start-local.ps1                       # foreground on :18500
  .\scripts\start-local.ps1 -Port 8100 -Background
  .\scripts\start-local.ps1 -Status -Port 8100
  .\scripts\start-local.ps1 -Stop -Port 8100
#>
param(
  [int]$Port = 18500,
  [string]$DataDir = "",
  [string]$AllowedHosts = "*",
  [string]$LiveUiBaseUrl = "http://127.0.0.1:3200",
  [ValidateSet("off", "observe", "enforce")]
  [string]$Guard = "off",
  [switch]$Headless,
  [switch]$Background,
  [switch]$Status,
  [switch]$Stop
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $DataDir) { $DataDir = Join-Path $root ".local-data\$Port" }
$pidFile = Join-Path $DataDir "controller.pid"
$health = "http://127.0.0.1:$Port/healthz"

function Test-Controller {
  try { (Invoke-RestMethod -Uri $health -TimeoutSec 2).status -eq "ok" } catch { $false }
}

if ($Status) {
  if (Test-Controller) { "up    http://127.0.0.1:$Port/mcp" } else { "down  port $Port" }
  return
}

if ($Stop) {
  if (-not (Test-Path $pidFile)) { "no pid file for port $Port ($pidFile); nothing stopped"; return }
  $procId = [int](Get-Content $pidFile)
  taskkill /PID $procId /T /F | Out-Null
  Remove-Item $pidFile -ErrorAction SilentlyContinue
  "stopped controller pid $procId (port $Port)"
  return
}

if (Test-Controller) { "already running on port ${Port}: http://127.0.0.1:$Port/mcp"; return }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
  throw "Port $Port is in use by something that is not a healthy controller. Pick another with -Port."
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$d = $DataDir
$envMap = @{
  ARTIFACT_ROOT = "$d\artifacts"; UPLOAD_ROOT = "$d\uploads"; AUTH_ROOT = "$d\auth"
  APPROVAL_ROOT = "$d\approvals"; AUDIT_ROOT = "$d\audit"; WITNESS_ROOT = "$d\witness"
  SESSION_STORE_ROOT = "$d\sessions"; JOB_STORE_ROOT = "$d\jobs"; HARNESS_ROOT = "$d\harness"
  MEMORY_ROOT = "$d\memory"; STATE_DB_PATH = "$d\state.db"
  MCP_SESSION_STORE_PATH = "$d\mcp\sessions.json"; CRON_STORE_PATH = "$d\crons.json"
  # Points at a file that never exists so the controller launches Chromium itself.
  BROWSER_WS_ENDPOINT_FILE = "$d\no-browser-node.txt"
  API_BIND_SCOPE = "loopback"; OCR_ENABLED = "false"
  ALLOWED_HOSTS = $AllowedHosts
  HEADLESS = $(if ($Headless) { "true" } else { "false" })
  LIVE_UI_BASE_URL = $LiveUiBaseUrl
  SHOAV_GUARD_MODE = $Guard
  # Antigravity/Gemini clients reject dots in tool names; calls accept either spelling.
  MCP_TOOL_NAME_STYLE = "underscore"
}

$controllerDir = Join-Path $root "controller"
$log = Join-Path $d "controller.log"
$argList = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")

if (-not $Background) {
  foreach ($k in $envMap.Keys) { Set-Item -Path "Env:$k" -Value $envMap[$k] }
  Set-Location $controllerDir
  python @argList
  return
}

# Background: env vars are inherited from this process only for the child.
$saved = @{}
foreach ($k in $envMap.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); Set-Item -Path "Env:$k" -Value $envMap[$k] }
try {
  $p = Start-Process -FilePath "python" -ArgumentList $argList -WorkingDirectory $controllerDir `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" -WindowStyle Hidden -PassThru
} finally {
  foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
}
Set-Content -Path $pidFile -Value $p.Id

for ($i = 0; $i -lt 40; $i++) {
  if (Test-Controller) { "up  http://127.0.0.1:$Port/mcp  (pid $($p.Id), log $log)"; return }
  if ($p.HasExited) { throw "controller exited early; see $log.err" }
  Start-Sleep -Milliseconds 500
}
throw "controller did not become healthy within 20s; see $log.err"
