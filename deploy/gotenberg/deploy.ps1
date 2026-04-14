# Deploy Gotenberg to Fly.io (requires flyctl: https://fly.io/docs/hands-on/install-flyctl/)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command fly -ErrorAction SilentlyContinue)) {
    Write-Error "Fly CLI not found. Install: winget install --id=fly.io.superfly"
}
fly deploy
