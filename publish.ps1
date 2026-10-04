<#
  Run this ONCE from this folder to put the repo on GitHub:   .\publish.ps1
  It asks for your GitHub username, fills it into install.ps1 / README.md / LICENSE, makes the git repo, and (with the GitHub CLI) creates
  the repository and pushes it. Without the GitHub CLI it prints the three commands to run by hand.
#>
$ErrorActionPreference = "Stop"
$user = Read-Host "Your GitHub username"
$repo = Read-Host "Repository name [shellflow-dotfiles]"
if ([string]::IsNullOrWhiteSpace($repo)) { $repo = "shellflow-dotfiles" }
$name = Read-Host "Your name for the LICENSE (the copyright line) [$user]"
if ([string]::IsNullOrWhiteSpace($name)) { $name = $user }

foreach ($f in "install.ps1", "install-all.ps1", "README.md", "LICENSE") {
    $t = Get-Content $f -Raw
    $t = $t.Replace("YOUR-NAME/shellflow-dotfiles", "$user/$repo").Replace("YOUR-NAME", $user).Replace("YOUR NAME", $name)
    Set-Content $f $t -Encoding UTF8
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Host "Install git first:  scoop install git" -ForegroundColor Red; return }
if (-not (Test-Path .git)) { git init -b main }
git add .
git commit -m "ShellFlow dotfiles" 2>$null

if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh auth status 2>$null
    if ($LASTEXITCODE -ne 0) { gh auth login }
    gh repo create "$user/$repo" --public --source . --remote origin --push --description "YASB + komorebi + ShellFlow: a bar and a settings window that follow your accent colour"
} else {
    Write-Host ""
    Write-Host "No GitHub CLI (scoop install gh, then run this again), or do it by hand:" -ForegroundColor Yellow
    Write-Host "  1. On github.com create a NEW EMPTY repository named $repo (public, no README, no licence)."
    Write-Host "  2. git remote add origin https://github.com/$user/$repo.git"
    Write-Host "  3. git push -u origin main"
}
Write-Host ""
Write-Host "Install line for other people:" -ForegroundColor Green
Write-Host "  irm https://raw.githubusercontent.com/$user/$repo/main/install.ps1 | iex"
Write-Host "Install everything without asking (they must read it first):" -ForegroundColor Green
Write-Host "  irm https://raw.githubusercontent.com/$user/$repo/main/install-all.ps1 | iex"
