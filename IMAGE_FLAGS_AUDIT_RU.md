# Аудит image-related флагов GUI/env и тестов
## InfiniCrafterLocal v0.4.234 secondary_refit_noise_cleanup

**Дата:** 2026-07-29
**Статус:** read-only, без редактирования

---

## 1. Все текущие image-related флаги

### 1.1 Backend selection
| Флаг | Файл:строка | По умолчанию | Потребители |
|------|-------------|--------------|-------------|
| `INFINI_IMAGE_BACKEND` | `pipeline_visual_config.py:30` | `sdcpp` | `visual_sprite_generation.py`, `visual_delivery_gate.py`, `image_backend_pipeline.py`, `server.py`, `settings_schema.py` |
| `INFINI_A1111_URL` | `pipeline_visual_config.py:33` | `http://127.0.0.1:7860` | `image_backend_pipeline.py` |
| `INFINI_COMFYUI_URL` | `pipeline_visual_config.py:34` | `http://127.0.0.1:8188` | `image_backend_pipeline.py` |
| `INFINI_IMAGE_API_BASE_URL` | `pipeline_visual_config.py:137` | `https://api.openai.com/v1` | `image_backend_pipeline.py` |
| `INFINI_IMAGE_API_KEY` | `pipeline_visual_config.py:138` | `` | `image_backend_pipeline.py` |
| `INFINI_IMAGE_API_MODEL` | `pipeline_visual_config.py:139` | `gpt-image-1` | `image_backend_pipeline.py` |
| `INFINI_IMAGE_API_PATH` | `pipeline_visual_config.py:140` | `/images/generations` | `image_backend_pipeline.py` |
| `INFINI_IMAGE_API_SIZE` | `pipeline_visual_config.py:141` | `512x512` | `image_backend_pipeline.py` |
| `INFINI_IMAGE_API_TIMEOUT` | `pipeline_visual_config.py:142` | `240` | `image_backend_pipeline.py` |

### 1.2 sd.cpp backend
| Флаг | Файл:строка | По умолчанию | Потребители |
|------|-------------|--------------|-------------|
| `INFINI_SDCPP_MODEL` | `pipeline_visual_config.py:37` | `` | `sdcpp_backend.py`, `image_backend_pipeline.py` |
| `INFINI_SDCPP_VAE` | `pipeline_visual_config.py:40` | `` | `sdcpp_backend.py` |
| `INFINI_SDCPP_LLM` | `pipeline_visual_config.py:41` | `` | `sdcpp_backend.py` |
| `INFINI_SDCPP_LORA_DIR` | `pipeline_visual_config.py:42` | `` | `sdcpp_backend.py` |
| `INFINI_SDCPP_LORA_FILE` | `pipeline_visual_config.py:43` | `` | `sdcpp_backend.py` |
| `INFINI_SDCPP_LORA_WEIGHT` | `pipeline_visual_config.py:44` | `0.25` | `sdcpp_backend.py` |
| `INFINI_SDCPP_LORA_PROMPT_TAGS` | `pipeline_visual_config.py:45` | `` | `sdcpp_backend.py` |
| `INFINI_SDCPP_WIDTH` | `pipeline_visual_config.py:55` | `512` | `image_backend_pipeline.py` |
| `INFINI_SDCPP_HEIGHT` | `pipeline_visual_config.py:56` | `512` | `image_backend_pipeline.py` |
| `INFINI_SDCPP_STEPS` | `pipeline_visual_config.py:57` | `8` | `image_backend_pipeline.py` |
| `INFINI_SDCPP_CFG` | `pipeline_visual_config.py:58` | `1.0` | `image_backend_pipeline.py` |
| `INFINI_SDCPP_SAMPLER` | `pipeline_visual_config.py:59` | `euler` | `image_backend_pipeline.py` |
| `INFINI_SDCPP_SEED` | `pipeline_visual_config.py:60` | `-1` | `image_backend_pipeline.py` |
| `INFINI_ZIMAGE_PROMPT_CONTRACT` | `pipeline_visual_config.py:61` | `auto` | `sdcpp_backend.py`, `visual_prompt_contracts.py` |
| `INFINI_ZIMAGE_POSITIVE_ONLY` | `pipeline_visual_config.py:62` | `True` | `sdcpp_backend.py` |
| `INFINI_SDCPP_SERVER_URL` | `pipeline_visual_config.py:63` | `http://127.0.0.1:7861` | `sdcpp_service.py` |
| `INFINI_SDCPP_SERVER_AUTOSTART` | `pipeline_visual_config.py:66` | `False` | `sdcpp_service.py` |
| `INFINI_SDCPP_SERVER_EXE` | `pipeline_visual_config.py:67` | `` | `sdcpp_service.py` |
| `INFINI_SDCPP_SERVER_EXTRA_ARGS` | `pipeline_visual_config.py:72` | `` | `sdcpp_service.py` |
| `INFINI_SDCPP_TIMEOUT` | `pipeline_visual_config.py:74` | `240` | `image_backend_pipeline.py` |

### 1.3 Visual asset mode & generation gating
| Флаг | Файл:строка | По умолчанию | Потребители |
|------|-------------|--------------|-------------|
| `INFINI_VISUAL_ASSET_MODE` | `pipeline_visual_config.py:146` | `full` | `visual_sprite_generation.py:538`, `visual_asset_plan.py`, `settings_gui_trace_state.py` |
| `INFINI_VISUAL_DIRECTOR_LLM` | `pipeline_visual_config.py:152` | `True` | `server.py`, `visual_generation_pipeline.py` |
| `INFINI_VISUAL_DIRECTOR_MAX_TOKENS` | `vfx_manifest_config.py:15` | `1800` | `visual_generation_pipeline.py` |
| `INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES` | `pipeline_visual_config.py:149` | `True` | **ТОЛЬКО GUI** (settings_schema.py, settings_gui_image_args.py, settings_gui_trace_state.py) |
| `INFINI_VISUAL_GENERATE_IMPACT_IMAGES` | `pipeline_visual_config.py:148` | `False` | **ТОЛЬКО GUI** |
| `INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES` | `pipeline_visual_config.py:147` | `False` | **ТОЛЬКО GUI** |

### 1.4 Sprite postprocess
| Флаг | Файл:строка | По умолчанию | Потребители |
|------|-------------|--------------|-------------|
| `INFINI_BG_REMOVE_MODE` | `pipeline_visual_config.py:174` | `sprite_keyer` | `sprite_keyer.py` |
| `INFINI_SPRITE_KEYER_SPILL_RADIUS` | `pipeline_visual_config.py:180` | `3` | `sprite_keyer.py` |
| `INFINI_SPRITE_KEYER_RESIDUE_STEPS` | `pipeline_visual_config.py:181` | `8` | `sprite_keyer.py` |
| `INFINI_SPRITE_MASTER_CANVAS` | `pipeline_visual_config.py:190` | `256` | `sprite_postprocess.py` |
| `INFINI_SPRITE_DOWNSCALE_FILTER` | `pipeline_visual_config.py:192` | `box` | `sprite_postprocess.py` |
| `INFINI_SPRITE_CHROMA_DEFRINGE` | `pipeline_visual_config.py:193` | `True` | `sprite_postprocess.py` |
| `INFINI_SPRITE_PREMULTIPLIED_RESIZE` | `pipeline_visual_config.py:194` | `True` | `sprite_postprocess.py` |
| `INFINI_SPRITE_RETRIES` | `pipeline_visual_config.py:196` | `2` | `visual_sprite_generation.py` |
| `INFINI_SAVE_SPRITE_STAGES` | `pipeline_visual_config.py:183` | `False` | `sprite_postprocess.py` |

### 1.5 Visual policy / delivery gate
| Флаг | Файл:строка | По умолчанию | Потребители |
|------|-------------|--------------|-------------|
| `INFINI_VISUAL_STRICT_AI_AUTHORSHIP` | `pipeline_visual_config.py:206` | `True` | `visual_delivery_gate.py`, `visual_sprite_generation.py` |
| `INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK` | `pipeline_visual_config.py:207` | `False` | `visual_delivery_gate.py`, `visual_sprite_generation.py` |
| `INFINI_VISUAL_REQUIRE_ITEM_SPRITE` | `pipeline_visual_config.py:210` | `True` | `visual_delivery_gate.py` |
| `INFINI_VISUAL_REQUIRE_ZIMAGE_BACKEND` | `pipeline_visual_config.py:213` | `False` | `visual_delivery_gate.py` |

### 1.6 VFX Director
| Флаг | Файл:строка | По умолчанию | Потребители |
|------|-------------|--------------|-------------|
| `INFINI_VFX_LLM_DIRECTOR` | `vfx_manifest_config.py:13` | `True` | `vfx_manifest.py`, `server.py` |
| `INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS` | `vfx_manifest_config.py:15` | `1800` | `vfx_manifest.py` |
| `INFINI_VFX_LLM_DIRECTOR_TEMPERATURE` | `vfx_manifest_config.py:16` | `0.34` | `vfx_manifest.py` |
| `INFINI_VFX_LLM_REPAIR_TEMPERATURE` | `vfx_manifest_config.py:17` | `0.12` | `vfx_manifest.py` |
| `INFINI_VFX_LLM_DIRECTOR_TIMEOUT` | `vfx_manifest_config.py:18` | `75` | `vfx_manifest.py` |
| `INFINI_VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS` | `vfx_manifest_config.py:19` | `1` | `vfx_manifest.py` |
| `INFINI_VFX_LLM_DIRECTOR_MAX_SLOTS` | `vfx_manifest_config.py:14` | `5` | `vfx_manifest.py` |
| `INFINI_VFX_EMERGENCY_MAX_PARTICLES_PER_TICK` | `vfx_manifest_config.py:22` | `240` | `server.py` |
| `INFINI_VFX_EMERGENCY_MAX_PARTICLES_TOTAL` | `vfx_manifest_config.py:23` | `9000` | `server.py` |
| `INFINI_VFX_EMERGENCY_MAX_DRAW_CALLS` | `vfx_manifest_config.py:24` | `420` | `server.py` |

### 1.7 Concurrency
| Флаг | Файл:строка | По умолчанию | Потребители |
|------|-------------|--------------|-------------|
| `INFINI_COMBINE_CONCURRENCY` | `combine_endpoint.py:17` | `1` | `combine_endpoint.py:18` (COMBINE_SEMAPHORE) |
| `INFINI_MULTIDEV_CONCURRENCY` | `combine_endpoint.py:19` | `3` | `combine_endpoint.py:20` (MULTIDEV_SEMAPHORE) |
| `INFINI_COMBINE_BUSY_WAIT_SECONDS` | `combine_endpoint.py:25` | `0` | `combine_endpoint.py:166,192` |

---

## 2. Три мёртвых role-флага на удаление

### Флаг 1: `INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES`
- **Определение:** `pipeline_visual_config.py:149`
- **GUI:** `settings_gui_image_args.py:268`, `settings_schema.py:99,289,505,625`
- **Trace state:** `settings_gui_trace_state.py:308`
- **Проблема:** Не используется в `visual_sprite_generation.py` для гейтинга генерации. Фактический гейтинг делается через `assetMode` (baked_sprite/no_asset/reuse_item_icon/runtime_geometry) и `VISUAL_ASSET_MODE`. Флаг только включает/выключает GUI row.

### Флаг 2: `INFINI_VISUAL_GENERATE_IMPACT_IMAGES`
- **Определение:** `pipeline_visual_config.py:148`
- **GUI:** `settings_gui_image_args.py:269`, `settings_schema.py:100,290,506,626`
- **Trace state:** `settings_gui_trace_state.py:309`
- **Проблема:** Та же — нет production consumers в генерации.

### Флаг 3: `INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES`
- **Определение:** `pipeline_visual_config.py:147`
- **GUI:** `settings_gui_image_args.py:270`, `settings_schema.py:101,291,507,627`
- **Trace state:** `settings_gui_trace_state.py:310`
- **Проблема:** Та же — нет production consumers в генерации.

**Доказательство отсутствия потребителей в генерации:**
```
visual_sprite_generation.py:538:
    if VISUAL_ASSET_MODE not in {"full", "projectile", "all", "visualpack", "assetpack"}:
        entity_visual["spriteStatus"] = "skipped_disabled_by_settings"
```
Гейтинг использует `VISUAL_ASSET_MODE`, а не три role-флага.

**Файлы для редактирования при удалении:**
1. `infini_local/pipelines/pipeline_visual_config.py` — строки 147-149 (определения) и 294-296 (__all__)
2. `infini_local/desktop/settings_schema.py` — строки 99-101 (FIELD_ORDER), 289-291 (DEFAULTS), 505-507 (HELP), 625-627 (PRESETS)
3. `infini_local/desktop/settings_gui_image_args.py` — строки 268-270 (GUI rows)
4. `infini_local/desktop/settings_gui_trace_state.py` — строки 308-310 (enable/disable logic)
5. `config.env` — строки 72-74
6. `config.example.env` — строки (закомментированные)

---

## 3. Флаги с реальными production consumers

### Критические (без них генерация ломается):
| Флаг | Consumer | Файл:строка |
|------|----------|-------------|
| `IMAGE_BACKEND` | выбор backend | `visual_sprite_generation.py:354`, `image_backend_pipeline.py` |
| `VISUAL_ASSET_MODE` | гейтинг генерации | `visual_sprite_generation.py:538` |
| `VISUAL_STRICT_AI_AUTHORSHIP` | политика авторства | `visual_delivery_gate.py:47`, `visual_sprite_generation.py:259` |
| `VISUAL_ALLOW_PROCEDURAL_FALLBACK` | procedural fallback | `visual_delivery_gate.py:47`, `visual_sprite_generation.py:476` |
| `VISUAL_REQUIRE_ITEM_SPRITE` | delivery gate | `visual_delivery_gate.py:67` |
| `SPRITE_RETRIES` | retry logic | `visual_sprite_generation.py:364` |

### Важные (влияют на качество/скорость):
| Флаг | Consumer | Файл:строка |
|------|----------|-------------|
| `SDCPP_MODEL/VAE/LLM` | sd.cpp config | `sdcpp_backend.py`, `image_backend_pipeline.py` |
| `SDCPP_SERVER_EXTRA_ARGS` | GPU profiles | `sdcpp_service.py` |
| `ZIMAGE_PROMPT_CONTRACT` | prompt contract | `sdcpp_backend.py`, `visual_prompt_contracts.py` |
| `SPRITE_MASTER_CANVAS` | master-first processing | `sprite_postprocess.py` |
| `SPRITE_DOWNSCALE_FILTER` | downscale quality | `sprite_postprocess.py` |
| `BG_REMOVE_MODE` | bg removal mode | `sprite_keyer.py` |

### Concurrency (shared-GPU):
| Флаг | Consumer | Файл:строка |
|------|----------|-------------|
| `COMBINE_CONCURRENCY` | combine semaphore | `combine_endpoint.py:17-18` |
| `MULTIDEV_CONCURRENCY` | multidev semaphore | `combine_endpoint.py:19-20` |
| `COMBINE_BUSY_WAIT_SECONDS` | busy-wait timeout | `combine_endpoint.py:166,192` |

---

## 4. Предлагаемые новые контроли

### 4.1 Shared-GPU concurrency для image generation

**Проблема:** Сейчас `COMBINE_SEMAPHORE` контролирует concurrency на уровне /combine endpoint, но не на уровне image backend calls. Если несколько LLM profiles генерируют изображения одновременно, sd.cpp server может получить перегрузку.

**Предложение:** `INFINI_IMAGE_GENERATION_CONCURRENCY` (default: 1, range: 1-4)
- `threading.BoundedSemaphore` в `visual_sprite_generation.py`
- Гейтит вызовы `generate_visual_asset()` и `generate_sprite()`
- Consumer: `visual_sprite_generation.py:339` (generate_visual_asset) и `:133` (maybe_generate_sprite)

**Файлы для редактирования:**
- `infini_local/pipelines/pipeline_visual_config.py` — добавить env var
- `infini_local/pipelines/visual_sprite_generation.py` — добавить semaphore acquire/release
- `infini_local/desktop/settings_schema.py` — добавить в FIELD_ORDER и DEFAULTS
- `infini_local/desktop/settings_gui_image_args.py` — добавить GUI row

### 4.2 Item/equipment/entity/VFX image generation controls

**Проблема:** Сейчас нет отдельного контроля для генерации VFX images vs item sprites. VFX uses `VFX_LLM_DIRECTOR` but image generation for VFX entities goes through the same `generate_visual_asset()` path.

**Предложение:** `INFINI_VFX_IMAGE_GENERATION` (default: True)
- Отдельный флаг для генерации изображений для VFX entities (projectile/impact/child/field)
- Consumer: `visual_sprite_generation.py:534-537` (гейтинг по assetMode)

**Файлы для редактирования:**
- `infini_local/pipelines/pipeline_visual_config.py` — добавить env var
- `infini_local/pipelines/visual_sprite_generation.py` — добавить проверку
- `infini_local/desktop/settings_schema.py` — добавить в FIELD_ORDER
- `infini_local/desktop/settings_gui_image_args.py` — добавить GUI row

### 4.3 Equipment sprite separate control

**Проблема:** Нет отдельного контроля для equipment/accessory sprites vs weapon sprites.

**Предложение:** `INFINI_EQUIPMENT_SPRITE_CANVAS` (default: 32, range: 16-64)
- Отдельный canvas size для equipment sprites
- Consumer: `visual_sprite_generation.py:339` (canvas parameter)

**Файлы для редактирования:**
- `infini_local/pipelines/pipeline_visual_config.py` — добавить env var
- `infini_local/pipelines/visual_sprite_generation.py` — использовать для equipment entities
- `infini_local/desktop/settings_schema.py` — добавить в FIELD_ORDER

---

## 5. Test matrix (behavior-focused)

### 5.1 Существующие тесты по image-related functionality

| Тест | Файл | Что проверяет |
|------|------|---------------|
| `test_settings_gui_contract_coarse_contract` | `tests/test_settings_gui_contract.py` | GUI schema completeness, field reachability |
| `test_visual_soul_contract_coarse_contract` | `tests/test_visual_soul_contract.py` | PNG metrics debug-only, C# doesn't execute PNG-derived presentation |
| `test_low_level_visual_vfx_contract` | `tests/test_low_level_visual_vfx_contract.py` | Visual roles, assetMode gating, VFX entity/event pairs |
| `test_live20_no_image_harness` | `tests/test_live20_no_image_harness.py` | No-image fixture hydration, delivery gate |
| `test_runtime_sprite_cache_vanilla_qol_contract` | `tests/test_runtime_sprite_cache_vanilla_qol_contract.py` | C# runtime sprite cache limits |
| `test_flux_hybrid_profile_contract` | `tests/test_flux_hybrid_profile_contract.py` | FLUX.2 Klein profile, ROCm environment scoping |

### 5.2 Матрица тестового покрытия для image flags

| Флаг | Тест | Статус |
|------|------|--------|
| `IMAGE_BACKEND` | `test_live20_no_image_harness` | Покрыт (no-image fixture) |
| `VISUAL_ASSET_MODE` | `test_low_level_visual_vfx_contract` | Покрыт (assetMode gating) |
| `VISUAL_STRICT_AI_AUTHORSHIP` | Нет прямого теста | **Не покрыт** |
| `VISUAL_ALLOW_PROCEDURAL_FALLBACK` | Нет прямого теста | **Не покрыт** |
| `VISUAL_REQUIRE_ITEM_SPRITE` | `test_low_level_visual_vfx_contract` | Покрыт (must use baked_sprite) |
| `SPRITE_RETRIES` | Нет прямого теста | **Не покрыт** |
| `SDCPP_*` | `test_flux_hybrid_profile_contract` | Покрыт (profile) |
| `VFX_LLM_DIRECTOR_*` | `test_low_level_visual_vfx_contract` | Покрыт (VFX entity/event) |
| `COMBINE_CONCURRENCY` | `tests/test_240_python_runtime_bugfixes.py` | Покрыт (semaphore tests) |
| `MULTIDEV_CONCURRENCY` | `tests/test_multidev_craft_contract.py` | Покрыт (multidev semaphore) |

### 5.3 Рекомендуемые новые тесты

1. **`test_visual_strict_ai_authorship_blocks_procedural`** — проверить что при `VISUAL_STRICT_AI_AUTHORSHIP=1` procedural fallback блокируется
2. **`test_sprite_retries_on_validation_failure`** — проверить retry logic при failed validation
3. **`test_image_generation_concurrency_semaphore`** — проверить новый semaphore для image generation
4. **`test_vfx_image_generation_toggle`** — проверить отдельный VFX image flag
5. **`test_role_flags_removed_from_gui`** — проверить что три мёртвых role-флага удалены из GUI и schema

---

## 6. Сводка

### Удалить (3 мёртвых флага):
1. `INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES`
2. `INFINI_VISUAL_GENERATE_IMPACT_IMAGES`
3. `INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES`

### Добавить (3 новых флага):
1. `INFINI_IMAGE_GENERATION_CONCURRENCY` — shared-GPU concurrency для image backend calls
2. `INFINI_VFX_IMAGE_GENERATION` — отдельный контроль для VFX entity images
3. `INFINI_EQUIPMENT_SPRITE_CANVAS` — отдельный canvas size для equipment sprites

### Критические потребители (не трогать):
- `IMAGE_BACKEND` — `visual_sprite_generation.py`, `image_backend_pipeline.py`
- `VISUAL_ASSET_MODE` — `visual_sprite_generation.py:538`
- `VISUAL_STRICT_AI_AUTHORSHIP` — `visual_delivery_gate.py`
- `COMBINE_CONCURRENCY` / `MULTIDEV_CONCURRENCY` — `combine_endpoint.py`

### Файлы для редактирования:
- `infini_local/pipelines/pipeline_visual_config.py`
- `infini_local/pipelines/visual_sprite_generation.py`
- `infini_local/pipelines/visual_delivery_gate.py`
- `infini_local/desktop/settings_schema.py`
- `infini_local/desktop/settings_gui_image_args.py`
- `infini_local/desktop/settings_gui_trace_state.py`
- `infini_local/services/combine_endpoint.py` (для image generation semaphore)
- `config.env` / `config.example.env`
