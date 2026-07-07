#nullable enable
using Terraria.Audio;

namespace InfiniCrafterLocal.Common.Audio;

/// <summary>
/// Disabled seam for a future embedding-selected generated sound catalog.
///
/// Intended future flow:
/// Python/backend owns the expensive audio embedding search over a large
/// user-provided catalog (for example 10k named sounds). It compares an authored
/// textual sound query against embedded sound names/metadata, then writes an
/// explicit selected catalog id/path into GeneratedItemData. C# should only play
/// that explicit concrete asset/id selection after normal asset safety checks.
///
/// This class deliberately does not keyword-classify profiles, scan folders, run
/// embeddings, or guess a sound from a huge library at runtime; it must not classify
/// the catalog on the client. Until explicit
/// catalog selections exist in JSON, it always returns false and InfiniSoundLibrary
/// falls back to vanilla SoundID.
/// </summary>
public static class InfiniFutureSoundCatalog
{
    public const string ContractVersion = "infini.embedding-sound-catalog.future-seam.v1";

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
    public string QueryText { get; }
    public string RuntimeFamily { get; }
    public string Effect { get; }
    public bool IsImpact { get; }
    public int OnHitCode { get; }
    public int EffectCode { get; }
    public string CatalogId { get; }
    public string CatalogPath { get; }
    public string CatalogSource { get; }

    private InfiniFutureSoundCatalogRequest(string role, string queryText, string runtimeFamily, string effect, bool impact, int onHitCode, int effectCode, string catalogId, string catalogPath, string catalogSource)
    {
        Role = role;
        QueryText = queryText;
        RuntimeFamily = runtimeFamily;
        Effect = effect;
        IsImpact = impact;
        OnHitCode = onHitCode;
        EffectCode = effectCode;
        CatalogId = catalogId;
        CatalogPath = catalogPath;
        CatalogSource = catalogSource;
    }

    public static InfiniFutureSoundCatalogRequest Use(string queryText, string runtimeFamily, string effect, string catalogId = "", string catalogPath = "", string catalogSource = "")
        => new("use", queryText, runtimeFamily, effect, impact: false, onHitCode: 0, effectCode: 0, catalogId, catalogPath, catalogSource);

    public static InfiniFutureSoundCatalogRequest Impact(string queryText, string effect, int onHitCode, int effectCode, string catalogId = "", string catalogPath = "", string catalogSource = "")
        => new("impact", queryText, runtimeFamily: "", effect, impact: true, onHitCode, effectCode, catalogId, catalogPath, catalogSource);

    public static InfiniFutureSoundCatalogRequest VfxCue(string queryText, string runtimeFamily, string effect, bool impact, string catalogId = "", string catalogPath = "", string catalogSource = "")
        => new("vfxCue", queryText, runtimeFamily, effect, impact, onHitCode: 0, effectCode: 0, catalogId, catalogPath, catalogSource);
}
