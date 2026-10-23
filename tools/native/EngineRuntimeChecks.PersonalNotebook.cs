#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void PersonalNotebook()
 {
        WithPlayer((player, owner) => {
            int old = Terraria.Main.worldID;
            try { Terraria.Main.worldID = 7;
                owner.SetJournalNote("a", "line1\nline2"); owner.SetJournalCollection("a", 3);
                var tag = new Terraria.ModLoader.IO.TagCompound(); owner.SaveData(tag); owner.LoadData(tag);
                Equal("line1 line2", owner.JournalNote("a"), "saved sanitized local note");
                Equal(3, owner.JournalCollection("a"), "collection persists");
                owner.SetJournalNote("a", new string('x', 300)); Equal(240, owner.JournalNote("a").Length, "bounded metadata");
                Terraria.Main.worldID = 8; Equal("", owner.JournalNote("a"), "world fence");
            } finally { Terraria.Main.worldID = old; }
        });
 }
}
