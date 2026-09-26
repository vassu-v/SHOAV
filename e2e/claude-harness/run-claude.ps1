<#
  Run Claude Code non-interactively with ONLY the auto-browser MCP (no built-in tools).
  Everything is passed as flags for this one run; no global or project settings are written.

  .\run-claude.ps1 -Prompt "open example.com and tell me the heading"
  .\run-claude.ps1 -PromptFile .\task-youtube.txt
#>
param(
  [string]$Prompt = "",
  [string]$PromptFile = "",
  [string]$Model = "sonnet",
  [int]$MaxTurns = 40
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($PromptFile) { $Prompt = Get-Content -Raw -Path $PromptFile }
if (-not $Prompt) { throw "Give -Prompt or -PromptFile" }

$log = Join-Path $PSScriptRoot "last-run.jsonl"
$system = "You control a web browser only through the auto-browser MCP tools. You have no other tools. " +
          "When a tool result contains a boxed live-view banner, print it to the user verbatim in a code block before continuing."

# Windows PowerShell 5.1 drops a bare "" argument, so pass it as a literal pair of quotes.
$Prompt | claude -p `
  --model $Model `
  --tools '""' `
  --mcp-config .mcp.json --strict-mcp-config `
  --allowedTools "mcp__auto-browser" `
  --append-system-prompt $system `
  --disable-slash-commands `
  --no-session-persistence `
  --max-turns $MaxTurns `
  --output-format stream-json --verbose |
  Tee-Object -FilePath $log |
  python .\format_stream.py
