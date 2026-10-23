#nullable enable
using System;
using System.Reflection;
using Terraria;
using Terraria.ModLoader.IO;
using InfiniCrafterLocal.Common.Players;
internal static partial class EngineRuntimeChecks
{
    private static void ObjectivePlanning()
    {
        WithPlayer((player, owner) => {
            int world = Terraria.Main.worldID;
            owner.SetJournalObjective("a", 17, true); owner.SetJournalObjective("b", 4, false);
            var tag = new TagCompound();
            typeof(InfiniCraftPlayer).GetMethod("SaveObjectives", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(owner, new object[] { tag });
            owner.SetJournalObjective("a", 1, false);
            typeof(InfiniCraftPlayer).GetMethod("LoadObjectives", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(owner, new object[] { tag });
            Equal((17, true), owner.JournalObjective("a"), "quantity/storage persist together");
            Equal((4, false), owner.JournalObjective("b"), "independent objective preferences");
            try { Terraria.Main.worldID = world + 1; Equal((1, false), owner.JournalObjective("a"), "world fence on goal state"); }
            finally { Terraria.Main.worldID = world; }
            owner.SetJournalObjective("a", 2000, true); Equal(999, owner.JournalObjective("a").Quantity, "bounded goal quantity");
            owner.SetJournalObjective("b", -1, false); Equal(1, owner.JournalObjective("b").Quantity, "positive goal quantity");
        });
    }
}
