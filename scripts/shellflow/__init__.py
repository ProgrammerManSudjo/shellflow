"""ShellFlow: Material You colours for the YASB bar and the apps around it, and a settings window.

  core        paths, the .env, logging (standard library only)
  early       the "starting" window and one-copy-at-a-time (standard library only)
  colors      colour schemes, the seed colour, the palette, applying a scheme
  themes/     one module per app theme (Discord, Zed, Obsidian, VS Code, Neovim, terminals, browsers, Yazi, File Pilot, Helium, Windhawk, ...)
  system/     Windows calls, sounds, the background helper, the picker, the doctor, the Home menu entry
  settings/   the settings window: config editing, styles, keybinds, drawing, and one module per page (pages/)
  cli         the command line (theme.py <command>)
  api         everything above under one name, for the settings window
"""
