-- ShellFlow starter config for Neovim: small on purpose, add your own plugins.
vim.g.mapleader = " "
local o = vim.opt
o.number, o.relativenumber, o.termguicolors, o.cursorline, o.undofile = true, true, true, true, true
o.expandtab, o.shiftwidth, o.tabstop, o.scrolloff, o.signcolumn = true, 2, 2, 6, "yes"
o.ignorecase, o.smartcase, o.splitright, o.splitbelow, o.clipboard = true, true, true, true, "unnamedplus"

-- The "yasb" colour scheme is written by ShellFlow (Templates > Neovim) and follows your accent colour; a plain dark one until then.
if not pcall(vim.cmd.colorscheme, "yasb") then vim.cmd.colorscheme("habamax") end

vim.keymap.set("n", "<leader>w", "<cmd>w<cr>", { desc = "Save" })
vim.keymap.set("n", "<leader>q", "<cmd>q<cr>", { desc = "Quit" })
vim.keymap.set("n", "<Esc>", "<cmd>nohlsearch<cr>")
