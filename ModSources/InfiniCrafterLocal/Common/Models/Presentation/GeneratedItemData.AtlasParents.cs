#nullable enable
using System;
using System.Linq;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

// Presentation-only evidence: the commutative recipe hash proves the parent
// multiset, never its original slot order. Never serialized into an item/save.
internal sealed record AtlasParentSet(string Id, string World, string RecipeKey, string[] Identities, string[] Names)
{
    internal bool Matches(GeneratedItemData data) => data.Id == Id && data.RecipeMeta.WorldScoped
        && data.RecipeMeta.WorldId == World && data.RecipeKey == RecipeKey
        && data.RecipeMeta.ParentIdentities is not { Length: > 2 }
        && (data.RecipeMeta.ParentIdentities is null || data.RecipeMeta.ParentIdentities.All(string.IsNullOrWhiteSpace));
}

public sealed partial class GeneratedItemData
{
    [JsonIgnore] internal AtlasParentSet? RecoveredAtlasParents { get; set; }
    [JsonIgnore] internal bool HasRecoveredAtlasParents => RecoveredAtlasParents?.Matches(this) == true;
    [JsonIgnore] internal string[] AtlasParentIdentities => HasRecoveredAtlasParents
        ? RecoveredAtlasParents!.Identities : RecipeMeta.ParentIdentities ?? Array.Empty<string>();
    internal string AtlasParentName(int slot) => HasRecoveredAtlasParents
        ? RecoveredAtlasParents!.Names[slot] : slot == 0 ? ParentA : ParentB;
}
