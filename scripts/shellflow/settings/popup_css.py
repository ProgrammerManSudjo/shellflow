"""CSS for the popups of the catalog widgets."""

# the popups of the catalog widgets, in your theme: black, rounded, accent buttons, light text. __FONT__ = the menu font
NOTES_CSS = """.notes-menu {
    background-color: #000000;
    border: none;
    border-radius: 20px;
    min-width: 380px;
    max-width: 380px;
}
.notes-menu .notes-header {
    background-color: transparent;
    padding: 6px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.notes-menu .notes-header .header-title {
    font-family: __FONT__;
    font-size: 15px;
    font-weight: 700;
    color: var(--yasb-accent-light2);
}
.notes-menu .notes-header .float-button,
.notes-menu .notes-header .close-button {
    background-color: transparent;
    border: none;
    color: var(--yasb-accent-light2);
    font-family: __ICONFONT__;
    font-size: 15px;
    padding: 4px 6px;
    border-radius: 8px;
}
.notes-menu .notes-header .float-button:hover,
.notes-menu .notes-header .close-button:hover {
    background-color: rgba(255, 255, 255, 0.10);
}
.notes-menu .note-input {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--yasb-accent-dark1);
    border-radius: 14px;
    padding: 10px;
    margin: 8px 12px 4px 12px;
    min-height: 110px;
    color: #ffffff;
    font-family: __FONT__;
    font-size: 13px;
}
.notes-menu .note-input:focus {
    border: 1px solid var(--yasb-accent-light1);
}
.notes-menu .input-copy-button {
    color: var(--yasb-accent-light2);
    background: transparent;
    border: none;
    font-family: __ICONFONT__;
    font-size: 14px;
    padding: 2px 4px;
    border-radius: 6px;
}
.notes-menu .input-copy-button:hover {
    background-color: rgba(255, 255, 255, 0.10);
}
.notes-menu .add-button,
.notes-menu .cancel-button {
    background-color: var(--yasb-accent-light1);
    color: var(--yasb-accent-dark3);
    border: none;
    border-radius: 14px;
    padding: 8px 16px;
    margin: 4px 12px;
    font-family: __FONT__;
    font-size: 13px;
    font-weight: 600;
}
.notes-menu .add-button:hover,
.notes-menu .cancel-button:hover {
    background-color: var(--yasb-accent-light2);
}
.notes-menu .scroll-area {
    background: transparent;
    border: none;
    border-radius: 0;
}
.notes-menu .note-item {
    background-color: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 0.10);
}
.notes-menu .note-item:hover {
    background-color: rgba(255, 255, 255, 0.06);
}
.notes-menu .note-item .title {
    font-family: __FONT__;
    font-size: 13px;
    color: #ffffff;
}
.notes-menu .note-item .date {
    font-family: __FONT__;
    font-size: 11px;
    color: rgba(255, 255, 255, 0.45);
}
.notes-menu .empty-list {
    font-family: __FONT__;
    font-size: 15px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.35);
    padding: 12px 0 18px 0;
}
.notes-menu .copy-button,
.notes-menu .delete-button {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 4px 8px;
    color: var(--yasb-accent-light2);
    font-family: __ICONFONT__;
    font-size: 14px;
}
.notes-menu .delete-button {
    color: #ff7a8a;
}
.notes-menu .copy-button:hover,
.notes-menu .delete-button:hover {
    background-color: rgba(255, 255, 255, 0.10);
}"""


CONTROL_CENTER_CSS = """.control-center-menu {
    background-color: #000000;
    border: none;
    border-radius: 20px;
    min-width: 400px;
    color: #ffffff;
}
.control-center-menu .section {
    background: transparent;
    margin: 0;
    padding: 14px 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.10);
}
.control-center-menu .section.system-controls {
    padding: 14px 16px 6px 16px;
}
.control-center-menu .section.sliders {
    padding: 14px 16px;
}
.control-center-menu .section.media,
.control-center-menu .section.power,
.control-center-menu .section.system-controls {
    border-bottom: 1px solid rgba(255, 255, 255, 0);
}
.control-center-menu .section.system-controls .button,
.control-center-menu .section.quick-actions .button .icon,
.control-center-menu .section.sliders .slider .icon,
.control-center-menu .section.sliders .slider .source-selector,
.control-center-menu .section.power .plan-name .icon,
.control-center-menu .section.power .mode-name .icon,
.control-center-menu .section.media .button {
    font-family: "Segoe Fluent Icons";
    font-weight: 400;
}
.control-center-menu .section.system-controls .button {
    background-color: rgba(255, 255, 255, 0.08);
    color: var(--yasb-accent-light2);
    border-radius: 16px;
    min-height: 32px;
    max-height: 32px;
    min-width: 32px;
    max-width: 32px;
    font-size: 14px;
}
.control-center-menu .section.system-controls .button:hover {
    background-color: rgba(255, 255, 255, 0.18);
}
.control-center-menu .section.quick-actions .button {
    margin: 0 4px;
}
.control-center-menu .section.quick-actions .button .icon {
    font-size: 17px;
    background-color: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    min-height: 50px;
    color: var(--yasb-accent-light2);
}
.control-center-menu .section.quick-actions .button .icon:hover {
    background-color: rgba(255, 255, 255, 0.12);
}
.control-center-menu .section.quick-actions .button.active .icon {
    background-color: var(--yasb-accent-light1);
    border: 1px solid var(--yasb-accent-light1);
    color: var(--yasb-accent-dark3);
}
.control-center-menu .section.quick-actions .button .title {
    font-family: __FONT__;
    font-size: 11px;
    font-weight: 600;
    margin: 4px 0 8px 0;
    padding: 0;
    color: #ffffff;
}
.control-center-menu .section.sliders .slider {
    background: transparent;
    border: none;
    min-height: 34px;
    margin: 0 4px;
}
.control-center-menu .section.sliders .slider .icon {
    font-size: 16px;
    min-width: 36px;
    color: var(--yasb-accent-light2);
}
.control-center-menu .section.sliders .slider .value {
    font-family: __FONT__;
    min-width: 42px;
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
}
.control-center-menu .section.sliders .slider .source-selector {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.65);
    width: 24px;
    height: 24px;
    border-radius: 8px;
    background-color: rgba(255, 255, 255, 0);
    margin-left: 4px;
}
.control-center-menu .section.sliders .slider .source-selector:hover {
    background-color: rgba(255, 255, 255, 0.12);
}
.control-center-menu .section.power .plan-name,
.control-center-menu .section.power .mode-name {
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    min-height: 38px;
    margin: 0 4px;
    padding: 6px 12px;
}
.control-center-menu .section.power .plan-name:hover,
.control-center-menu .section.power .mode-name:hover {
    background: rgba(255, 255, 255, 0.12);
}
.control-center-menu .section.power .plan-name .title,
.control-center-menu .section.power .mode-name .title {
    font-family: __FONT__;
    font-size: 11px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.60);
}
.control-center-menu .section.power .plan-name .subtext,
.control-center-menu .section.power .mode-name .subtext {
    font-family: __FONT__;
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
}
.control-center-menu .section.power .plan-name .icon,
.control-center-menu .section.power .mode-name .icon {
    color: rgba(255, 255, 255, 0.60);
    font-size: 14px;
}
.control-center-menu .section.media {
    background-color: rgba(255, 255, 255, 0.04);
    padding: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.10);
}
.control-center-menu .section.media .title {
    font-family: __FONT__;
    font-size: 13px;
    font-weight: 600;
    color: #ffffff;
}
.control-center-menu .section.media .subtext {
    font-family: __FONT__;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.55);
}
.control-center-menu .section.media .button {
    font-size: 14px;
    color: var(--yasb-accent-light2);
    background-color: rgba(255, 255, 255, 0);
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
    border-radius: 10px;
    margin: 0 0 0 4px;
}
.control-center-menu .section.media .button:hover {
    background-color: rgba(255, 255, 255, 0.10);
}
.control-center-menu .context-menu {
    background-color: #111111;
    padding: 4px 0;
    font-family: __FONT__;
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
}
.control-center-menu .context-menu::item {
    background-color: transparent;
    padding: 6px 12px;
    margin: 2px 6px;
    border-radius: 8px;
    min-width: 100px;
}
.control-center-menu .context-menu::item:selected {
    background-color: rgba(255, 255, 255, 0.12);
}"""


WHKD_CSS = """.whkd-popup {
    background-color: #000000;
    border: none;
    border-radius: 20px;
}
.whkd-popup .edit-config-button {
    background-color: var(--yasb-accent-light1);
    color: var(--yasb-accent-dark3);
    padding: 4px 12px 6px 12px;
    font-family: __FONT__;
    font-size: 13px;
    font-weight: 600;
    border-radius: 12px;
}
.whkd-popup .keybind-button {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
    padding: 4px 10px 6px 10px;
    font-size: 13px;
    font-weight: 600;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
}
.whkd-popup .keybind-button.special {
    background-color: rgba(255, 255, 255, 0.14);
}
.whkd-popup .keybind-row:hover {
    background-color: rgba(255, 255, 255, 0.06);
    border-radius: 10px;
}
.whkd-popup .plus-separator {
    border: none;
    color: rgba(255, 255, 255, 0.5);
    background-color: transparent;
}
.whkd-popup .filter-input {
    padding: 0 10px 2px 10px;
    font-family: __FONT__;
    font-size: 13px;
    border: 1px solid var(--yasb-accent-dark1);
    border-radius: 12px;
    color: #ffffff;
    background-color: rgba(255, 255, 255, 0.06);
    min-height: 32px;
}
.whkd-popup .filter-input:focus {
    border: 1px solid var(--yasb-accent-light1);
}
.whkd-popup .keybind-command {
    font-family: __FONT__;
    font-size: 13px;
    color: #ffffff;
}
.whkd-popup .keybind-header {
    font-family: __FONT__;
    font-size: 15px;
    font-weight: 600;
    color: var(--yasb-accent-light2);
    padding: 8px 0;
    margin-top: 16px;
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 12px;
}"""


POPUP_CSS = {"notes": NOTES_CSS, "control_center": CONTROL_CENTER_CSS, "whkd": WHKD_CSS}
