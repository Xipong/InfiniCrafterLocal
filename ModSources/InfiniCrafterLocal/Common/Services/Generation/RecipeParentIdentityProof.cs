#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.Services;

// A historical world-local recipe key binds the exact unordered parent pair.
// Captions only narrow candidates. They prove neither identity nor historical
// slot order. This owner never creates or changes gameplay content.
internal static class RecipeParentIdentityProof
{
    internal const int MaxTargets = 2048, MaxCandidates = 16, MaxPairsPerTarget = 64, MaxHashChecks = 4096;
    internal const string IdentityVersion = "recipe_v4_25_no_item_family_routing";

    internal sealed class Candidates
    {
        private readonly Dictionary<string, HashSet<string>> _byCaption = new(StringComparer.Ordinal);
        private readonly HashSet<string> _overflow = new(StringComparer.Ordinal);
        private readonly Dictionary<string, string> _names = new(StringComparer.Ordinal);

        internal Candidates(IEnumerable<GeneratedItemData> targets)
        {
            foreach (var data in targets)
                foreach (string caption in new[] { data.ParentA, data.ParentB })
                    if (!string.IsNullOrWhiteSpace(caption)) _byCaption.TryAdd(caption, new(StringComparer.Ordinal));
        }

        internal void Add(string caption, string identity)
        {
            if (!_byCaption.TryGetValue(caption, out var identities) || _overflow.Contains(caption) || !SafeHashPart(identity)) return;
            _names.TryAdd(identity, caption);
            identities.Add(identity);
            if (identities.Count <= MaxCandidates) return;
            identities.Clear(); _overflow.Add(caption); // Never select the first subset of an ambiguous caption.
        }

        internal string[] Get(string caption) => _byCaption.TryGetValue(caption, out var values) && !_overflow.Contains(caption)
            ? values.OrderBy(value => value, StringComparer.Ordinal).ToArray() : Array.Empty<string>();
        internal string Name(string identity) => _names[identity];
    }

    internal static bool Missing(GeneratedItemData data) => data.RecipeMeta.ParentIdentities is not { Length: > 2 }
        && (data.RecipeMeta.ParentIdentities is not { Length: 2 } current || current.Any(string.IsNullOrWhiteSpace));

    private static bool SafeHashPart(string value) => !string.IsNullOrEmpty(value) && value.Length <= 1024
        && value.All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-' or ':' or '/' or '.');

    internal static string? Key(string first, string second, string world)
    {
        // This restricted legacy grammar has byte-identical JSON in Python and
        // C#. Refuse other characters rather than guessing at encoder differences.
        if (!SafeHashPart(first) || !SafeHashPart(second) || !SafeHashPart(world)) return null;
        if (string.CompareOrdinal(first, second) > 0) (first, second) = (second, first);
        string encoded = "[\"" + first + "\", \"" + second + "\"]\0\"world:" + world + "\"\0\"" + IdentityVersion + "\"\0";
        return "r_" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(encoded))).ToLowerInvariant()[..24];
    }

    internal static string[]? Resolve(GeneratedItemData data, string world, Candidates candidates, ref int remainingChecks)
        => ResolveSet(data, world, candidates, ref remainingChecks) is { } pair ? Ordered(data, pair) : null;

    internal static string[]? Ordered(GeneratedItemData data, string[] pair)
    {
        if (pair[0] == pair[1]) return pair;
        string[] current = data.RecipeMeta.ParentIdentities ?? Array.Empty<string>();
        for (int slot = 0; slot < Math.Min(2, current.Length); slot++)
        {
            if (string.IsNullOrWhiteSpace(current[slot])) continue;
            if (!pair.Contains(current[slot], StringComparer.Ordinal)) return null;
            string other = pair[0] == current[slot] ? pair[1] : pair[0];
            return slot == 0 ? new[] { current[slot], other } : new[] { other, current[slot] };
        }
        return null; // Mutable captions cannot certify the historical slot order.
    }

    internal static string[]? ResolveSet(GeneratedItemData data, string world, Candidates candidates, ref int remainingChecks)
    {
        if (!data.RecipeMeta.WorldScoped || data.RecipeMeta.WorldId != world || !Missing(data)
            || data.RecipeKey.Length != 26 || !data.RecipeKey.StartsWith("r_", StringComparison.Ordinal)) return null;
        string[] first = candidates.Get(data.ParentA), second = candidates.Get(data.ParentB);
        int required = first.Length * second.Length;
        if (required == 0 || required > MaxPairsPerTarget || required > remainingChecks) return null;
        // Reserve the whole search before beginning. A partial search is never proof of uniqueness.
        remainingChecks -= required;
        string[]? match = null;
        string[] current = data.RecipeMeta.ParentIdentities ?? Array.Empty<string>();
        foreach (string a in first)
        foreach (string b in second)
        {
            if (current.Any(value => !string.IsNullOrWhiteSpace(value) && value != a && value != b)) continue;
            if (Key(a, b, world) != data.RecipeKey) continue;
            string[] pair = string.CompareOrdinal(a, b) <= 0 ? new[] { a, b } : new[] { b, a };
            if (match is not null && !match.SequenceEqual(pair)) return null;
            match = pair; // Reversed enumeration is the same unordered proof.
        }
        return match;
    }
}
