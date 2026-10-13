from __future__ import annotations

from infini_local.desktop.tk_compat import ttk

class SpritesPageMixin:
    def _build_visual(self, parent):
        root = parent
        parent = self._card(root, "Прозрачность и края", "Сначала фон, затем чистые края. Неактивные параметры сохраняются.")
        self.row(parent, "Удалять фон", "INFINI_REMOVE_BG", values=["1", "0"])
        self.row(parent, "Способ удаления фона", "INFINI_BG_REMOVE_MODE", values=["sprite_keyer"], hint="Оставлен только sprite_keyer: Photoshop-like Magic Wand от краёв + refine/spill cleanup под Terraria sprites.")
        self.row(parent, "Фон изображения", "INFINI_BG_COLOR", values=["magenta", "transparent", "white", "black"], hint="transparent = модель запрашивается с alpha; локальный keyer не применяется. Chroma-цвет используется только при локальном удалении фона.")
        self.row(parent, "Допуск цвета фона", "INFINI_CHROMA_TOLERANCE", width=16, hint="Допуск key-color удаления. Если белое/серое уносит — не повышать; обычно 34.")
        self.row(parent, "Порог прозрачности", "INFINI_ALPHA_THRESHOLD", width=16, hint="Порог отсечения полупрозрачной альфы. Если края худеют — снизить до 20-24.")
        self.row(parent, "Радиус очистки края", "INFINI_SPRITE_KEYER_SPILL_RADIUS", width=16, hint="sprite_keyer: radius узкой refine-edge зоны для подавления magenta spill. Обычно 3.")
        self.row(parent, "Проходов очистки", "INFINI_SPRITE_KEYER_RESIDUE_STEPS", width=16, hint="sprite_keyer: сколько шагов проходить по connected magenta/dark-key residue от выбранного фона. Обычно 8.")
        self.row(parent, "Попыток генерации", "INFINI_SPRITE_RETRIES", width=16)
        self.row(parent, "Сохранять этапы PNG", "INFINI_SAVE_SPRITE_STAGES", values=["1", "0"], hint="1 = сохранять 00_raw / 10_bg_removed_fullres / 20_master_norm / 30_baked_final в cache\\sprites для дебага.")
        parent = self._card(root, "Размер и пиксельная палитра", "Финальное уменьшение изображения для игрового спрайта.")
        self.row(parent, "Промежуточный размер", "INFINI_SPRITE_MASTER_CANVAS", width=16, hint="Большой промежуточный RGBA-canvas перед финальным 32/48/64 bake. Нужен для master-first нормализации: вырезали фон, вписали объект в 256x256, потом уже уменьшили в 32/48/64.")
        resize_row = self.row(parent, "Фильтр уменьшения", "INFINI_SPRITE_DOWNSCALE_FILTER", values=["box", "bilinear", "bicubic", "lanczos"], hint="box — базовый фильтр; pipeline preset сохраняет выбранный фильтр. Reset BOX вернёт box и premultiplied=1.")
        reset_resize = ttk.Button(resize_row, text="Сбросить BOX", command=self.reset_sprite_resize)
        reset_resize.pack(side="left", padx=4)
        self.field_widgets["INFINI_SPRITE_DOWNSCALE_FILTER"].append(reset_resize)
        self.row(parent, "Уменьшение с альфой", "INFINI_SPRITE_PREMULTIPLIED_RESIZE", values=["1", "0"], hint="Убирает magenta bleed по краям при resize RGBA.")
        self.row(parent, "Очистка цветного ореола", "INFINI_SPRITE_CHROMA_DEFRINGE", values=["1", "0"], hint="Консервативно удаляет остатки magenta-key только на краях alpha.")
        self.row(parent, "Ограничивать палитру", "INFINI_PIXEL_POSTERIZE", values=["1", "0"])
        self.row(parent, "Количество цветов", "INFINI_MAX_COLORS", width=16)
        self.row(parent, "Только авторство модели", "INFINI_VISUAL_STRICT_AI_AUTHORSHIP", values=["1", "0"], hint="1 = код не рисует за нейронку, только валидирует/ретраит.")
        self.row(parent, "Программный резерв", "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK", values=["0", "1"])
        parent = self._card(root, "Авторство и эффекты", "Дополнительные параметры внешнего вида предмета.")
        self.row(parent, "Визуальный комплект", "INFINI_VISUAL_ASSET_MODE", values=["full", "projectile", "off"])
        self.row(parent, "Модель внешнего вида", "INFINI_VISUAL_DIRECTOR_LLM", values=["1", "0"])
        self.row(parent, "Бюджет описания образа", "INFINI_VISUAL_DIRECTOR_MAX_TOKENS", width=16, hint="Пусто = взять общий Max answer tokens. Если хочешь отдельно ограничить visual-kit шаг, задай число здесь.")
        self.row(parent, "Модель эффектов", "INFINI_VFX_LLM_DIRECTOR", values=["1", "0"])
