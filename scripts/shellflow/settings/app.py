"""The App class: the window plus one mixin per page."""
from .search import SearchMixin
from .pages.general import GeneralPage
from .pages.colors import ColorsMixin
from .pages.wallpaper import WallpaperMixin
from .pages.widgets import WidgetsMixin
from .pages.bar import BarMixin
from .pages.templates import TemplatesMixin
from .pages.edits import EditsMixin
from .pages.files import FilesMixin
from .pages.keybinds import KeybindsMixin
from .pages.backup import BackupMixin
from .pages.about import AboutMixin
from .pages.display import DisplayMixin
from .window import WindowBase


class App(SearchMixin, GeneralPage, ColorsMixin, WallpaperMixin, WidgetsMixin, BarMixin, TemplatesMixin, EditsMixin, FilesMixin, KeybindsMixin, BackupMixin, AboutMixin, DisplayMixin, WindowBase):
    """The settings window: the window itself (WindowBase) plus one mixin per page."""
