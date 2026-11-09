using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.UI;
using Terraria;
using Terraria.GameInput;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void AtlasFocusAndOverlayResumeStayScoped()
    {
        bool block = Terraria.Main.blockInput, writing = PlayerInput.WritingText, chat = Terraria.Main.drawingPlayerChat;
        var system = new RecipeJournalUISystem();
        try
        {
            system.OnWorldUnload();
            Terraria.Main.drawingPlayerChat = false;
            Terraria.Main.blockInput = PlayerInput.WritingText = true;
            RecipeJournalUISystem.SetSearchFocus(false);
            Equal(true, Terraria.Main.blockInput && PlayerInput.WritingText, "unfocused atlas cannot clear external text owner");
            RecipeJournalUISystem.SetSearchFocus(true);
            system.OnWorldUnload();
            Equal(true, Terraria.Main.blockInput && PlayerInput.WritingText, "atlas refuses to acquire existing text owner");
            Terraria.Main.blockInput = PlayerInput.WritingText = false;
            RecipeJournalUISystem.SetSearchFocus(true);
            Equal(true, Terraria.Main.blockInput && PlayerInput.WritingText, "search reserves text input");
            Equal(false, RecipeJournalUISystem.CanResumeInput(true, true, false), "overlay suspends atlas");
            Equal(false, Terraria.Main.blockInput || PlayerInput.WritingText, "overlay releases owned focus");
            Equal(false, RecipeJournalUISystem.CanResumeInput(false, true, false), "held left mouse cannot click through overlay");
            Equal(false, RecipeJournalUISystem.CanResumeInput(false, false, true), "held right mouse cannot resume either");
            Equal(true, RecipeJournalUISystem.CanResumeInput(false, false, false), "released buttons resume atlas");
            Equal(false, Terraria.Main.blockInput || PlayerInput.WritingText, "browsing does not reserve gameplay keyboard");
            RecipeJournalUISystem.CanResumeInput(true, true, false);
            system.OnWorldUnload();
            Equal(true, RecipeJournalUISystem.CanResumeInput(false, true, false), "new world does not inherit suspended mouse gate");
            RecipeJournalUISystem.SetSearchFocus(true);
            system.Unload();
            Equal(false, Terraria.Main.blockInput || PlayerInput.WritingText, "mod unload releases search focus");
        }
        finally
        {
            system.OnWorldUnload();
            Terraria.Main.blockInput = block; PlayerInput.WritingText = writing; Terraria.Main.drawingPlayerChat = chat;
        }
    }

    private static void DeferredRefundLoadIsolatesMalformedRows()
    {
        using var itemPoolState = new NativeItemPoolState();
        using var serializer = WithPersistenceBoolSerializer();
        WithPlayer((player, owner) =>
        {
            owner.Initialize();
            string clientId = Guid.NewGuid().ToString("N");
            var bad = new TagCompound { ["mod"] = "Terraria", ["id"] = "not-an-item-id" };
            bool rejected = false;
            try { ItemIO.Load(bad); } catch { rejected = true; }
            Equal(true, rejected, "fixture actually fails native item deserialization");
            owner.LoadData(new TagCompound
            {
                ["infiniStationEscrowClientId"] = clientId,
                ["infiniDeferredCraftRefundsV1"] = new List<TagCompound>
                {
                    ItemIO.Save(new Item(ItemID.Wood, 3)), bad,
                    ItemIO.Save(new Item(ItemID.StoneBlock, 7))
                }
            });
            var saved = new TagCompound(); owner.SaveData(saved);
            var rows = saved.GetList<TagCompound>("infiniDeferredCraftRefundsV1");
            Equal(2, rows.Count, "valid refunds on both sides of corrupt row survive");
            Equal(3, ItemIO.Load(rows[0]).stack, "first refund quantity preserved");
            Equal(ItemID.StoneBlock, ItemIO.Load(rows[1]).type, "later refund identity preserved");
            Equal(7, ItemIO.Load(rows[1]).stack, "later refund quantity preserved");
            Equal(clientId, saved.GetString("infiniStationEscrowClientId"), "escrow identity loads despite corrupt row");
        });
    }
}
