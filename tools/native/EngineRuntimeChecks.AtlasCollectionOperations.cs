#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void AtlasCollectionOperations()
 {
        WithPlayer((player, owner) => {
            int old = Terraria.Main.worldID;
            try {
                Terraria.Main.worldID = 21;
                foreach (string id in new[] { "a", "b" }) { owner.SetJournalFavorite(id, true); owner.SetJournalCollection(id, 4); }
                owner.SetJournalFavorite("a", true);
                Equal(true, owner.IsJournalFavorite("a"), "bulk assignment idempotent");
                owner.SetJournalFavorite("a", false); Equal(false, owner.IsJournalFavorite("a"), "exact selected removal");
                Equal(true, owner.IsJournalFavorite("b"), "unselected favorite untouched");
                Equal(4, owner.JournalCollection("b"), "collection assigned");
                Terraria.Main.worldID = 22; Equal(false, owner.IsJournalFavorite("b"), "world separation");
                Equal(0, owner.JournalCollection("b"), "collection world separation");
            } finally { Terraria.Main.worldID = old; }
        });
 }
}
