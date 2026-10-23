#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void DiscoveryHistory()
 {
        WithPlayer((player, owner) => {
            owner.VisitJournalRecipe("a"); owner.VisitJournalRecipe("b"); long before = owner.JournalLastVisited("b");
            owner.VisitJournalRecipe("a"); Equal(true, owner.JournalLastVisited("a") > before, "revisit moves to front");
            var tag = new Terraria.ModLoader.IO.TagCompound(); owner.SaveData(tag); owner.LoadData(tag);
            Equal(true, owner.JournalLastVisited("a") > owner.JournalLastVisited("b"), "order survives save");
            owner.VisitJournalRecipe("c"); Equal(true, owner.JournalLastVisited("c") > owner.JournalLastVisited("a"), "sequence continues after load");
            Equal(0L, owner.JournalLastVisited("unknown"), "unvisited remains distinct");
        });
 }
}
