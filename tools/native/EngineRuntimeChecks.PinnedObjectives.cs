#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void PinnedObjectives()
 {
        WithPlayer((player, owner) => {
            int world = Terraria.Main.worldID;
            try {
                Terraria.Main.worldID = 101;
                Equal(true, owner.ToggleJournalPin("a"), "pin first goal"); owner.ToggleJournalPin("b"); owner.ToggleJournalPin("c");
                Equal(false, owner.ToggleJournalPin("d"), "three goals bounded");
                var tag = new Terraria.ModLoader.IO.TagCompound(); owner.SaveData(tag);
                owner.LoadData(tag); Equal(true, owner.IsJournalPinned("a"), "pin survives save");
                Terraria.Main.worldID = 102; Equal(false, owner.IsJournalPinned("a"), "world-local goals");
                Equal(true, owner.ToggleJournalPin("d"), "another world has separate slots");
            } finally { Terraria.Main.worldID = world; }
        });
 }
}
