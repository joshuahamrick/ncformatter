# One-shot deps for layout PDF + PNG (run from repo root).
# Word path: pip install pywin32, then Word COM is used on Windows when "layout PDF" is checked.
# LibreOffice path: install from https://www.libreoffice.org/ (optional fallback on Windows; primary on Linux servers).

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

Write-Host "Installing Python deps from requirements.txt ..."
python -m pip install -r requirements.txt

if (($PSVersionTable.PSVersion.Major -ge 6 -and $IsWindows) -or $env:OS -match "Windows") {
    if (-not (Get-Command soffice -ErrorAction SilentlyContinue)) {
        $lo = "${env:ProgramFiles}\LibreOffice\program\soffice.exe"
        if (Test-Path $lo) {
            Write-Host "LibreOffice found at $lo (no PATH change needed; process-doc resolves it)."
        } else {
            Write-Host "Tip: install LibreOffice for PDF fallback, or rely on Word + pywin32."
        }
    }
}

Write-Host "Done. In the UI, check 'layout PDF' when uploading a .docx. Vercel Linux still needs LibreOffice in the image or an external converter unless you use a Windows worker."
