#nullable enable
using Terraria.Audio;

namespace InfiniCrafterLocal.Common.Audio;

/// <summary>
/// Disabled seam for a future externally supplied sound catalog.
///
/// A backend may use embeddings or any other expensive search internally, but the
/// result crossing into C# must already be an explicit catalog id/path/source. The
/// game runtime never receives prose, scans names, searches folders, or classifies
/// an item to choose audio. Until an explicit external resolver is implemented this
/// seam returns false and InfiniSoundLibrary falls back to vanilla SoundID.
/// </summary>
public static class InfiniFutureSoundCatalog
{
    public const string ContractVersion = "infini.external-sound-catalog.future-seam.v2";

    public static bool TryResolveOneShot(InfiniFutureSoundCatalogRequest request, out SoundStyle style)
    {
        style = default;
        _ = request;
        return false;
    }
}

public readonly struct InfiniFutureSoundCatalogRequest
{
    public string Role { get; }
    public string RuntimeFamily { get; }
    public string Effect { get; }
    public bool IsImpact { get; }
    public int OnHitCode { get; }
    public int EffectCode { get; }
    public string CatalogId { get; }
    public string CatalogPath { get; }
    public string CatalogSource { get; }

    private InfiniFutureSoundCatalogRequest(string role, string runtimeFamily, string effect, bool impact, int onHitCode, int effectCode, string catalogId, string catalogPath, string catalogSource)
    {
        Role = role;
        RuntimeFamily = runtimeFamily;
        Effect = effect;
        IsImpact = impact;
        OnHitCode = onHitCode;
        EffectCode = effectCode;
        CatalogId = catalogId;
        CatalogPath = catalogPath;
        CatalogSource = catalogSource;
    }

    public static InfiniFutureSoundCatalogRequest Use(string runtimeFamily, string effect, string catalogId = "", string catalogPath = "", string catalogSource = "")
        => new("use", runtimeFamily, effect, false, 0, 0, catalogId, catalogPath, catalogSource);

    public static InfiniFutureSoundCatalogRequest Impact(string effect, int onHitCode, int effectCode, string catalogId = "", string catalogPath = "", string catalogSource = "")
        => new("impact", "", effect, true, onHitCode, effectCode, catalogId, catalogPath, catalogSource);

    public static InfiniFutureSoundCatalogRequest VfxCue(string runtimeFamily, string effect, bool impact, string catalogId = "", string catalogPath = "", string catalogSource = "")
        => new("vfxCue", runtimeFamily, effect, impact, 0, 0, catalogId, catalogPath, catalogSource);
}
