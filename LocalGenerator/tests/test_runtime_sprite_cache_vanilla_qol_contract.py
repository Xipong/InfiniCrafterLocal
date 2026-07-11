from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"
LOCAL = ROOT / "LocalGenerator"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runtime_sprite_cache_uses_vanilla_like_soft_limits():
    cache = read(MOD / "Common" / "Services" / "RuntimeSpriteCache.cs")
    config = read(MOD / "Common" / "Config" / "InfiniGameplayQolConfig.cs")
    assert "DefaultMaxCachedTextures = 512" in cache
    assert "MaxCachedTexturesHardLimit = 2048" in cache
    assert "DefaultMaxTextureDimensionPixels = 192" in cache
    assert "DefaultMaxTextureFileMegabytes = 8" in cache
    assert "RuntimeSpriteLimits" in cache
    assert "IsRuntimePngFileSizeAllowed" in cache
    assert "tex.Width > limits.MaxTextureDimensionPixels" in cache
    assert "tex.Height > limits.MaxTextureDimensionPixels" in cache
    assert "TrimTextureCacheIfNeeded(limits.MaxCachedTextures)" in cache
    assert "while (_textures.Count > maxCachedTextures)" in cache
    assert "texture.Dispose();" in cache
    assert "MaxMissingOrBadRecords = 256" in cache
    assert "TrimMissingOrBadCacheIfNeeded" in cache
    assert "[DefaultValue(512)]" in config
    assert "[Range(64, 2048)]" in config
    assert "RuntimeSpriteMaxDimensionPixels" in config
    assert "RuntimeSpriteMaxPngFileMegabytes" in config


def test_runtime_sprite_cache_has_in_game_ru_en_config_labels():
    en = read(MOD / "Localization" / "en-US_Mods.InfiniCrafterLocal.hjson")
    ru = read(MOD / "Localization" / "ru-RU_Mods.InfiniCrafterLocal.hjson")
    for text in (en, ru):
        assert "InfiniGameplayQolConfig" in text
        assert "RuntimeSpriteCacheMaxTextures" in text
        assert "RuntimeSpriteMaxDimensionPixels" in text
        assert "RuntimeSpriteMaxPngFileMegabytes" in text
    assert "Runtime sprite cache size" in en
    assert "Runtime sprite max side" in en
    assert "Runtime PNG file limit" in en
    assert "Размер кэша спрайтов" in ru
    assert "Максимальная сторона спрайта" in ru
    assert "Лимит PNG-файла" in ru
