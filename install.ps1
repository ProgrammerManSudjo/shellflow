<#
  ShellFlow installer: scoop + komorebi + whkd + YASB, then (if you say yes) ShellFlow, your dotfiles, wallpapers and terminal tools.
  EVERY step asks yes or no first. Nothing from komorebi or whkd is bundled: they come from their official scoop packages.

  Run it (as a NORMAL user, not as administrator):
    irm https://raw.githubusercontent.com/ProgrammerManSudjo/shellflow/main/install.ps1 | iex
  or from a clone:   .\install.ps1
  Unattended (every question takes its default answer):   $env:SHELLFLOW_YES = "1"; .\install.ps1
  Everything without asking: see install-all.ps1 (read the warning in it first).

  ALWAYS READ A SCRIPT BEFORE YOU RUN IT, especially one you found online and run with  irm ... | iex.
  This one is plain text: open it and read it first.
#>

# ---- set by publish.ps1 (or edit them by hand) ------------------------------------------------------
$ZipUrl        = "https://github.com/ProgrammerManSudjo/shellflow/archive/refs/heads/main.zip"
$WallpapersUrl = ""   # optional: a wallpapers.zip attached to a GitHub Release, for collections too big for git
$WindhawkUrl   = "https://github.com/ramensoftware/windhawk/releases"   # the Windhawk (2.0 alpha) download page
# -------------------------------------------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$Yes = ($env:SHELLFLOW_YES -eq "1")
$All = ($env:SHELLFLOW_ALL -eq "1")     # set by install-all.ps1: yes to everything, except replacing files you already have
function Say($t, $c = "Cyan") { Write-Host $t -ForegroundColor $c }
function Ask($q, $default = $true, $replacesYourFile = $false) {
    if ($All) { Say "  $q -> yes (install everything)" DarkGray; return (-not $replacesYourFile) }
    if ($Yes) { return $default }
    $hint = if ($default) { "[Y/n]" } else { "[y/N]" }
    $a = Read-Host "$q $hint"
    if ([string]::IsNullOrWhiteSpace($a)) { return $default }
    return $a.Trim().ToLower().StartsWith("y")
}
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine") }
function Have($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Stop-Here($why) { Say $why Yellow; Say "Stopped. Run the installer again any time." Yellow }

$me = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if ($me.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Say "Run this as a normal user (scoop installs into your own profile, and refuses to run elevated)." Red
    return
}
$UserHome = $env:USERPROFILE          # every directory below is built from the signed-in user's profile
Say "ShellFlow installer for $env:USERNAME ($UserHome)" Green
Say "Every step asks first; answer n to skip it. (Read scripts from the internet before you run them.)" Green

# ---- 1. scripts and scoop ------------------------------------------------------------------------
if (-not (Ask "Allow PowerShell scripts for your user (Set-ExecutionPolicy RemoteSigned, CurrentUser only)? scoop needs this." $true)) { Stop-Here "Scripts stay blocked, so scoop cannot be installed."; return }
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force

if (-not (Have scoop)) {
    if (-not (Ask "Install scoop (a package manager that installs into your user folder, no administrator needed)?" $true)) { Stop-Here "Everything else is installed with scoop."; return }
    Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
    Refresh-Path
}
if (Ask "Install git and add the scoop buckets 'extras' and 'nerd-fonts' (they hold komorebi, YASB and the font)?" $true) {
    if (-not (Have git)) { scoop install git; Refresh-Path }
    scoop bucket add extras 2>$null
    scoop bucket add nerd-fonts 2>$null
}

# ---- 2. komorebi, whkd, YASB, font (the official packages) ---------------------------------------
Say ""
Say "komorebi and whkd: their licence (Komorebi License) allows PERSONAL use only; using them at work needs a paid licence:" Yellow
Say "https://lgug2z.com/software/komorebi" Yellow
if (Ask "Install komorebi (tiling window manager) and whkd (hotkeys)?" $true) { scoop install extras/komorebi extras/whkd }
if (Ask "Install YASB (the status bar)?" $true) { scoop install extras/yasb }
if (Ask "Install the JetBrainsMono Nerd Font (the bar's icons need it)?" $true) {
    try { scoop install nerd-fonts/JetBrainsMono-NF } catch { Say "The font did not install: scoop install nerd-fonts/JetBrainsMono-NF" Yellow }
}
Refresh-Path

# ---- 3. where the dotfiles are: next to this script (a clone), or downloaded ---------------------
$src = $null
function Get-Source {
    if ($script:src) { return $script:src }
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "shellflow\theme.py"))) { $script:src = $PSScriptRoot; return $script:src }
    Say "Downloading the dotfiles..."
    $tmp = Join-Path $env:TEMP ("shellflow-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    Invoke-WebRequest -Uri $ZipUrl -OutFile "$tmp\pack.zip" -UseBasicParsing
    Expand-Archive "$tmp\pack.zip" -DestinationPath $tmp -Force
    $script:src = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName
    return $script:src
}

# ---- 4. ShellFlow and the starter config ----------------------------------------------------------
Say ""
$yasb    = Join-Path $UserHome ".config\yasb"
$scripts = Join-Path $yasb "scripts"
if (Ask "Install ShellFlow (the settings window and colour scripts, needs Python) into $yasb ?" $true) {
    $src = Get-Source
    if (-not (Have python)) { if (Ask "ShellFlow needs Python. Install it with scoop?" $true) { scoop install python; Refresh-Path } }
    if (Have python) { python -m pip install --upgrade --quiet pillow materialyoucolor }
    New-Item -ItemType Directory -Force -Path $scripts | Out-Null
    Copy-Item "$src\shellflow\*.py" $scripts -Force
    Say "ShellFlow scripts: $scripts"

    if (Ask "Install the starter YASB config (config.yaml, styles.css, .env: one bar, app themes and sounds off)?" $true) {
        foreach ($f in "config.yaml", "styles.css", ".env") {
            $dest = Join-Path $yasb $f
            $from = Join-Path $src "defaults\yasb\$f"
            if (-not (Test-Path $from)) { continue }
            if ((Test-Path $dest) -and -not (Ask "  $f already exists. Back it up (as $f.before-shellflow) and replace it?" $false $true)) { Say "  Kept your $f"; continue }
            if (Test-Path $dest) { Copy-Item $dest "$dest.before-shellflow" -Force }
            Copy-Item $from $dest -Force
        }
        $cfg = Join-Path $yasb "config.yaml"
        (Get-Content $cfg -Raw).Replace("__USERPROFILE__", $UserHome.Replace("\", "/")) | Set-Content $cfg -Encoding UTF8
    }
    if ((Have komorebic) -and -not (Test-Path "$UserHome\komorebi.json") -and (Ask "Create komorebi's own example config (komorebic quickstart: komorebi.json, applications.json, whkdrc)?" $true)) {
        try { komorebic quickstart } catch { Say "komorebic quickstart failed: run it yourself later." Yellow }
    }
    if ((Have python) -and (Ask "Add the ShellFlow entry to the Home menu and write the plain Windows-accent colours?" $true)) {
        python "$scripts\theme.py" install-menu
        python "$scripts\theme.py" windows
    }
}

# ---- 5. wallpapers ---------------------------------------------------------------------------------
Say ""
$walls = Join-Path $UserHome "Pictures\Wallpapers"
if (Ask "Copy the bundled wallpapers to $walls ?" $true) {
    $src = Get-Source
    $from = Join-Path $src "wallpapers"
    $images = @(Get-ChildItem $from -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -match '\.(png|jpe?g|webp|bmp)$' })
    if ($images.Count -eq 0 -and $WallpapersUrl) {
        Say "Downloading the wallpapers..."
        $wtmp = Join-Path $env:TEMP ("wallpapers-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $wtmp | Out-Null
        Invoke-WebRequest -Uri $WallpapersUrl -OutFile "$wtmp\w.zip" -UseBasicParsing
        Expand-Archive "$wtmp\w.zip" -DestinationPath $wtmp -Force
        $from = $wtmp
        $images = @(Get-ChildItem $from -File -Recurse | Where-Object { $_.Extension -match '\.(png|jpe?g|webp|bmp)$' })
    }
    if ($images.Count -gt 0) {
        New-Item -ItemType Directory -Force -Path $walls | Out-Null
        $images | ForEach-Object { Copy-Item $_.FullName $walls -Force }
        Say "$($images.Count) wallpapers copied to $walls"
    } else { Say "No wallpapers are bundled in this download." Yellow }
}

# ---- 6. terminal tools --------------------------------------------------------------------------------
Say ""
if (Ask "Install the terminal tools (yazi, neovim, fzf, ripgrep, fd, bat, zoxide and what yazi uses for previews)?" $false) {
    scoop install yazi neovim fzf ripgrep fd bat zoxide jq 7zip poppler ffmpeg
    Refresh-Path
}
$nv = Join-Path $env:LOCALAPPDATA "nvim"
if (Ask "Install the starter Neovim config into $nv ?" $false) {
    $src = Get-Source
    if (-not (Test-Path "$nv\init.lua") -or (Ask "  You already have an init.lua. Back it up and replace it?" $false $true)) {
        New-Item -ItemType Directory -Force -Path $nv | Out-Null
        if (Test-Path "$nv\init.lua") { Copy-Item "$nv\init.lua" "$nv\init.lua.before-shellflow" -Force }
        Copy-Item "$src\terminal\nvim\*" $nv -Recurse -Force
    } else { Say "  Kept your Neovim config." }
}
$yz = Join-Path $env:APPDATA "yazi\config"
if (Ask "Install the starter Yazi config into $yz ?" $false) {
    $src = Get-Source
    if (-not (Test-Path "$yz\yazi.toml") -or (Ask "  You already have a yazi.toml. Back it up and replace it?" $false $true)) {
        New-Item -ItemType Directory -Force -Path $yz | Out-Null
        if (Test-Path "$yz\yazi.toml") { Copy-Item "$yz\yazi.toml" "$yz\yazi.toml.before-shellflow" -Force }
        Copy-Item "$src\terminal\yazi\*" $yz -Recurse -Force
    } else { Say "  Kept your Yazi config." }
}
$profileFile = $PROFILE.CurrentUserAllHosts
if (Ask "Add the ShellFlow block (fzf colours that follow your accent, zoxide, a 'y' command for yazi) to your PowerShell profile ($profileFile)?" $false) {
    $src = Get-Source
    New-Item -ItemType Directory -Force -Path (Split-Path $profileFile) | Out-Null
    $old = if (Test-Path $profileFile) { Get-Content $profileFile -Raw } else { "" }
    if ($old -notmatch "ShellFlow terminal") { Add-Content $profileFile ("`r`n" + (Get-Content "$src\terminal\powershell\shellflow-profile.ps1" -Raw)) } else { Say "  Your profile already has the block." }
}

# ---- 7. Windhawk (optional, for the taskbar styling) ----------------------------------------------------
Say ""
if (Ask "Open the Windhawk download page ($WindhawkUrl) so you can install it? (optional: only for the taskbar styling)" $false) { Start-Process $WindhawkUrl }

# ---- 8. start ----------------------------------------------------------------------------------------------
Say ""
if (((Have komorebic) -or (Have yasb)) -and (Ask "Start komorebi and YASB now?" $true)) {
    if (Have komorebic) { try { komorebic start --whkd } catch { Say "komorebi did not start: run  komorebic start --whkd" Yellow } }
    if (Have yasb) { try { Start-Process yasb } catch { Say "YASB did not start: run  yasb" Yellow } }
}
Say ""
Say "Done. Open ShellFlow from the Home button on the bar (the ShellFlow entry)." Green
Say "App themes (Discord, Zed, ...) and sounds are OFF; the bar follows your Windows accent colour. Switch things on in ShellFlow > Templates." Green

# ---- 9. projects worth a look (only links: ShellFlow can write colour themes for these once they are installed) -----------
Say ""
Say "Check out these awesome projects as well! (ShellFlow > Templates can give them your accent colours once you have them.)" Green
$links = @(
    @("Equicord (Discord client mod)",          "https://github.com/Equicord/Equicord"),
    @("midnight (the Discord theme)",           "https://github.com/refact0r/midnight-discord"),
    @("File Pilot (file manager)",              "https://filepilot.tech"),
    @("Helium (Chromium browser)",              "https://github.com/imputnet/helium"),
    @("Zen Browser (Firefox-based browser)",    "https://zen-browser.app"),
    @("Windhawk (Windows mods, taskbar styling)", $WindhawkUrl),
    @("Rainmeter (desktop widgets and clocks)", "https://www.rainmeter.net"),
    @("Zed (editor)",                           "https://zed.dev"),
    @("Obsidian (notes)",                       "https://obsidian.md"),
    @("Yazi (terminal file manager)",           "https://yazi-rs.github.io"),
    @("Tacky Borders (window borders)",         "https://github.com/lukeyou05/tacky-borders"),
    @("OBS Studio (recording and streaming)",   "https://obsproject.com")
)
foreach ($l in $links) { Write-Host ("  {0,-44} {1}" -f $l[0], $l[1]) -ForegroundColor Cyan }
Say ""

