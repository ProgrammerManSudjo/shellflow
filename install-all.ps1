<#
  INSTALL EVERYTHING, WITHOUT ASKING.

  *** DANGEROUS. ALWAYS READ SCRIPTS YOU FIND ONLINE BEFORE YOU RUN THEM. ***
  This script (and the one it starts) installs software and changes files in your user profile without asking you anything:
  scoop, git, komorebi, whkd, YASB, a font, Python, ShellFlow, a starter config, wallpapers, terminal tools and their configs,
  a block in your PowerShell profile, and it opens the Windhawk download page. Files you already have are NOT replaced.
  If you want to choose each step, use install.ps1 instead. Read both files first: they are plain text, a few hundred lines.

    irm https://raw.githubusercontent.com/YOUR-NAME/shellflow-dotfiles/main/install-all.ps1 | iex     (only after you have read it)
  or from a clone:   .\install-all.ps1
#>

$InstallUrl = "https://raw.githubusercontent.com/YOUR-NAME/shellflow-dotfiles/main/install.ps1"

Write-Host ""
Write-Host "  ============================ WARNING ============================" -ForegroundColor Red
Write-Host "  This installs EVERYTHING without asking, and changes your user profile." -ForegroundColor Red
Write-Host "  Never run a script from the internet that you have not read." -ForegroundColor Red
Write-Host "  Read it first:  $InstallUrl" -ForegroundColor Red
Write-Host "  ==================================================================" -ForegroundColor Red
Write-Host ""
Write-Host "  komorebi and whkd are free for personal use only (Komorebi License); work use needs a paid licence." -ForegroundColor Yellow
Write-Host ""
$answer = Read-Host "  Type  I HAVE READ THE SCRIPTS  to continue (anything else stops)"
if ($answer -ne "I HAVE READ THE SCRIPTS") { Write-Host "Stopped. Nothing was changed." -ForegroundColor Yellow; return }

$env:SHELLFLOW_ALL = "1"
try {
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "install.ps1"))) { & (Join-Path $PSScriptRoot "install.ps1") }
    else { Invoke-RestMethod -Uri $InstallUrl | Invoke-Expression }
} finally { Remove-Item Env:\SHELLFLOW_ALL -ErrorAction SilentlyContinue }
