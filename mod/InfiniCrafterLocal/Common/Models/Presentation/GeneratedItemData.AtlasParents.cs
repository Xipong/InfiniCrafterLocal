#nullable enable
using System;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

public sealed partial class GeneratedItemData
{
    [JsonIgnore] internal string[] AtlasParentIdentities => RecipeMeta.ParentIdentities ?? Array.Empty<string>();
    internal string AtlasParentName(int slot) => slot == 0 ? ParentA : ParentB;
}
