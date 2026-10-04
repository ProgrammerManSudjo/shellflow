# ShellFlow dotfiles

A bar (YASB), a tiling window manager (komorebi + whkd) and ShellFlow, a settings window that makes everything follow your accent colour.

## Install

In PowerShell, as a normal user (not administrator):

```powershell
irm https://raw.githubusercontent.com/ProgrammerManSudjo/shellflow/main/install.ps1 | iex
```

**Every step asks yes or no first**: allowing scripts, scoop, git and the buckets, komorebi + whkd, YASB, the font, ShellFlow, the starter
config (and, if you already have one, whether to replace it), komorebi's example config, the wallpapers, the terminal tools, each
terminal config, the Windhawk download page, and starting everything. Nothing is installed without a yes.
It works in the signed-in user's profile (`%USERPROFILE%\.config\yasb`, komorebi's own files).

## Install everything without asking (dangerous)

```powershell
irm https://raw.githubusercontent.com/ProgrammerManSudjo/shellflow/main/install-all.ps1 | iex
```

> **Disclaimer: always read scripts you find online before you run them.** `install-all.ps1` installs everything without asking
> (scoop, komorebi, whkd, YASB, a font, Python, ShellFlow, the config, wallpapers, the terminal tools and their configs, a block in your
> PowerShell profile) and changes your user profile. It makes you type `I HAVE READ THE SCRIPTS` before it starts, and it never
> replaces a config file you already have. Both scripts are plain text: [install-all.ps1](install-all.ps1), [install.ps1](install.ps1).
> komorebi and whkd are free for personal use only (Komorebi License).

## What is in this repo

| Folder | What | Goes to |
| --- | --- | --- |
| `shellflow/` | `theme.py`, `settings.py` | `%USERPROFILE%\.config\yasb\scripts` |
| `defaults/yasb/` | starter `config.yaml`, `styles.css`, `.env` | `%USERPROFILE%\.config\yasb` |
| `wallpapers/` | your images (png, jpg, webp, bmp) | `%USERPROFILE%\Pictures\Wallpapers` |
| `terminal/` | Neovim, Yazi and PowerShell (fzf, zoxide) configs | `%LOCALAPPDATA%\nvim`, `%APPDATA%\yazi\config`, your PowerShell profile |

komorebi and whkd are **not** in this repo: their licence forbids redistribution and any commercial use. They are installed by scoop,
and the installer tells people the licence terms.

## What it does not install

ShellFlow can write colour themes for Discord (midnight, through Equicord, Vencord or BetterDiscord), File Pilot, Helium, Zen, Zed, Obsidian,
Yazi, OBS and more, but the installer does **not** install those programs: it only prints their links at the end. Install the ones you want
yourself, then switch them on in ShellFlow > Templates:

| Project | Link |
| --- | --- |
| Equicord (Discord client mod) | https://github.com/Equicord/Equicord |
| midnight (Discord theme) | https://github.com/refact0r/midnight-discord |
| File Pilot | https://filepilot.tech |
| Helium | https://github.com/imputnet/helium |
| Zen Browser | https://zen-browser.app |
| Windhawk | https://github.com/ramensoftware/windhawk/releases |
| Rainmeter | https://www.rainmeter.net |
| Zed | https://zed.dev |
| Obsidian | https://obsidian.md |
| Yazi | https://yazi-rs.github.io |
| Tacky Borders | https://github.com/lukeyou05/tacky-borders |
| OBS Studio | https://obsproject.com |

## Defaults

App themes (Discord, Zed, ...) are off (`YASB_APPS=none`), sounds are off, the background helper is off. The bar follows the Windows accent
colour. Everything is switched on in ShellFlow (Home button, "ShellFlow" entry).

## Putting this on GitHub

1. Add your wallpapers to `wallpapers/` (see the note in that folder: a few dozen are fine; for a big collection use a Release asset).
2. In PowerShell, in this folder, run `.\publish.ps1`. It asks for your GitHub username, fills it into the files, creates the repo and pushes it
   (it uses the GitHub CLI: `scoop install gh`; without it, it prints the three commands for doing it by hand).
3. It prints the install line for other people: `irm https://raw.githubusercontent.com/<you>/shellflow-dotfiles/main/install.ps1 | iex`.
4. Big wallpaper collection: zip the images as `wallpapers.zip`, create a Release (`gh release create v1 wallpapers.zip`), and set
   `$WallpapersUrl` in `install.ps1` to `https://github.com/<you>/shellflow-dotfiles/releases/latest/download/wallpapers.zip`.
   (Do not use Git LFS for them: GitHub's zip and raw downloads give LFS files as small pointer files, not the images.)
5. When ShellFlow changes, copy the new `theme.py` and `settings.py` into `shellflow/`, then `git add . && git commit -m "update" && git push`.
6. Test it in a Windows virtual machine **with a standard (non-administrator) user** before sharing the link. (Windows Sandbox does not work for this: its account is an administrator, and scoop and the installer refuse to run elevated.) To test a change before pushing, run `.\install.ps1` from the folder: it uses the local files.

