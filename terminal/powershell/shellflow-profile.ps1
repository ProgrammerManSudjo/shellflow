# >>> ShellFlow terminal >>>
# fzf colours follow your accent colour (read from the bar's colour files); zoxide, history prediction, and a yazi that cds on exit.
function Get-ShellFlowAccent {
    foreach ($f in "theme_colors.css", "yasb_colors.css") {
        $p = Join-Path $env:USERPROFILE ".config\yasb\$f"
        if (Test-Path $p) {
            $m = [regex]::Match((Get-Content $p -Raw), '--yasb-accent-light1-rgb:\s*(\d+),\s*(\d+),\s*(\d+)')
            if ($m.Success) { return ('#{0:x2}{1:x2}{2:x2}' -f [int]$m.Groups[1].Value, [int]$m.Groups[2].Value, [int]$m.Groups[3].Value) }
        }
    }
    return "#a6a6a6"
}
$accent = Get-ShellFlowAccent
$env:FZF_DEFAULT_COMMAND = 'fd --type f --hidden --exclude .git'
$env:FZF_DEFAULT_OPTS = "--height 40% --layout=reverse --border rounded --color=hl:$accent,hl+:$accent,pointer:$accent,prompt:$accent,marker:$accent,border:$accent"
$env:YAZI_FILE_ONE = Join-Path $env:USERPROFILE "scoop\apps\git\current\usr\bin\file.exe"
if (Get-Command zoxide -ErrorAction SilentlyContinue) { Invoke-Expression (& { (zoxide init powershell | Out-String) }) }
if (Get-Module -ListAvailable PSReadLine) { Set-PSReadLineOption -PredictionSource History }
function y { $tmp = New-TemporaryFile; yazi $args --cwd-file="$tmp"; $cwd = Get-Content $tmp; if ($cwd -and $cwd -ne $PWD.Path) { Set-Location -LiteralPath $cwd }; Remove-Item $tmp }
# <<< ShellFlow terminal <<<
