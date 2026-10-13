"""Desktop UI composition. Shell, native components and task pages have separate owners.

Compatibility field/callback map (implemented in the page modules):
    self.row(codex_card, "Codex text model", "INFINI_CODEX_LLM_MODEL", ...)
    "INFINI_CODEX_VISUAL_REASONING" belongs to text author settings.
    "INFINI_CODEX_IMAGE_MODEL" belongs to the image page.
    self.refresh_codex_text_catalog refreshes the text-only account catalog.
    Нет live-каталога image-моделей: the image page explicitly warns about this.
    Качество и размер влияют на время генерации и расход квоты подписки.

The public SettingsGuiUiMixin import remains supported; it is no longer a form monolith.
"""
from infini_local.desktop.tk_compat import tk, ttk
from infini_local.desktop.settings_widgets import ToolTip, ScrollFrame
from infini_local.desktop.settings_gui_components import ForgeComponentsMixin
from infini_local.desktop.settings_gui_fields import SettingsFieldsMixin
from infini_local.desktop.settings_gui_shell import SettingsShellMixin
from infini_local.desktop.settings_page_operate import OperatePageMixin
from infini_local.desktop.settings_page_providers import ProvidersPageMixin
from infini_local.desktop.settings_page_images import ImagesPageMixin
from infini_local.desktop.settings_page_sprites import SpritesPageMixin
from infini_local.desktop.settings_page_configure import ConfigurePageMixin
from infini_local.desktop.settings_page_diagnostics import DiagnosticsPageMixin


class SettingsGuiUiMixin(SettingsShellMixin, ForgeComponentsMixin, SettingsFieldsMixin,
                         OperatePageMixin, ProvidersPageMixin, ImagesPageMixin,
                         SpritesPageMixin, ConfigurePageMixin, DiagnosticsPageMixin):
    # Keep monkeypatch-compatible tooltip seam for embedding/contract tests.
    def _attach_static_help(self, widget, text):
        ToolTip(widget, text)


__all__ = ["SettingsGuiUiMixin"]
