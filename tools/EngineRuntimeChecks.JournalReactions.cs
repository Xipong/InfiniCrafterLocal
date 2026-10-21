using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void InputLocalConditionsStayIndependent()
    {
        var player = new Player { statLife = 50, statMana = 10, wet = true };
        var gameplay = new GameplaySpec { UseConditions = new[] {
            new RuntimeUseConditionSpec { Input = RuntimeInputKind.PrimaryUse, UseConditionMode = "not_wet" },
            new RuntimeUseConditionSpec { Input = RuntimeInputKind.AlternateUse, UseConditionMode = "life_above", UseConditionMinLife = 50 } } };
        Equal("Cannot be used while wet", GeneratedItem.UseBlockedReason(player, gameplay, RuntimeInputKind.PrimaryUse), "primary reads its own gate");
        Equal("", GeneratedItem.UseBlockedReason(player, gameplay, RuntimeInputKind.AlternateUse), "alternate ignores primary wet gate and threshold is inclusive");
        player.statLife = 49; player.wet = false;
        Equal("", GeneratedItem.UseBlockedReason(player, gameplay, RuntimeInputKind.PrimaryUse), "primary ignores alternate life gate");
        Equal("Requires 50 life", GeneratedItem.UseBlockedReason(player, gameplay, RuntimeInputKind.AlternateUse), "alternate checks its own threshold");
        var invalid = new RuntimeUseConditionSpec { Input = RuntimeInputKind.Hold, UseConditionMode = "not_wet" };
        bool refused = false; try { invalid.Validate(); } catch (InvalidDataException) { refused = true; }
        Equal(true, refused, "passive condition rejected before execution");
    }

    private static void RecipeJournalKeepsWorldIdentityAndFavorites()
    {
        GeneratedItemData Entry(string id, string world, string name)
        {
            var data = GeneratedItemData.Placeholder(); data.Id = id; data.Name = name;
            data.RecipeMeta.WorldId = world; data.RecipeMeta.WorldScoped = true; return data;
        }
        var a = Entry("a", "17", "Copper branch"); var b = Entry("b", "17", "Wooden blade");
        b.ParentA = "Copper branch"; b.RecipeMeta.ParentIdentities = new[] { "generated:a", "item:Terraria:Wood:9" };
        var foreign = Entry("other", "18", "Secret recipe");
        var records = new[] { b, foreign, a };
        Equal(2, RecipeJournalView.Entries(records, "17", "", _ => false, false).Length, "foreign world discoveries hidden");
        Equal("b", RecipeJournalView.Entries(records, "17", "wooden", _ => false, false).Single().Id, "case insensitive name search");
        Equal("b", RecipeJournalView.Entries(records, "17", "", id => id == "b", true).Single().Id, "favorite filter");
        Equal("a", RecipeJournalView.Parent(b, 0, records)!.Id, "history follows exact generated parent identity");
        b.RecipeMeta.ParentIdentities[0] = "generated:missing";
        Equal(true, RecipeJournalView.Parent(b, 0, records) is null, "matching name cannot invent a parent link");
        // Effective UI-space sizes include small displays and high UI-scale settings.
        foreach (int width in new[] { 0, 160, 240, 320, 400, 640, 700, 792, 1024, 1280, 1920 })
        foreach (int height in new[] { 0, 120, 240, 360, 480, 600, 720, 1080 })
        {
            var layout = RecipeJournalView.Bounds(width, height);
            Equal(true, new Rectangle(0, 0, width, height).Contains(layout.Book), "book fits viewport");
            Equal(true, layout.Book.Contains(layout.List) && layout.Book.Contains(layout.Detail), "both pages stay inside book");
            Equal(false, layout.List.Intersects(layout.Detail), "list and detail do not overlap");
            Equal(true, layout.List.Width >= 0 && layout.List.Height >= 0 && layout.Detail.Width >= 0 && layout.Detail.Height >= 0, "page extents never negative");
            Equal(true, layout.Rows >= 0 && layout.Rows * 52 <= layout.List.Height, "only complete list rows are drawn");
            Equal(true, layout.Columns >= 0 && layout.Columns * 52 <= layout.List.Width, "only complete grid columns are drawn");
            Equal(true, layout.Book.Width <= 920 && layout.Book.Height <= 560, "recipe browser remains bounded on large screens");
        }
        var narrowBook = RecipeJournalView.Bounds(640, 600);
        Equal(true, narrowBook.Detail.Height >= 160 && narrowBook.Rows >= 1, "compact book retains readable details and a selectable recipe");
        var shortBook = RecipeJournalView.Bounds(640, 360);
        Equal(true, shortBook.Rows >= 1 && shortBook.Detail.Height >= 52, "short compact viewport keeps selection reachable");
        var wideBook = RecipeJournalView.Bounds(1280, 720);
        Equal(true, wideBook.Detail.Width > wideBook.List.Width && wideBook.Detail.Y == wideBook.List.Y, "wide browser keeps a larger recipe detail pane");
        Equal(7, wideBook.Columns, "wide grid offers seven inventory columns");
        Equal(true, wideBook.Detail.Width >= 320, "wide detail keeps usable ingredient space");
        Equal(true, narrowBook.Columns >= 1 && narrowBook.Rows <= 2, "compact grid leaves room for detail");
        WithPlayer((player, _) => {
            var owner = player.GetModPlayer<InfiniCraftPlayer>();
            owner.ToggleJournalFavorite("favorite");
            var tag = new TagCompound(); owner.SaveData(tag);
            owner.ToggleJournalFavorite("favorite"); Equal(false, owner.IsJournalFavorite("favorite"), "favorite explicitly removed");
            owner.LoadData(tag); Equal(true, owner.IsJournalFavorite("favorite"), "favorite restored through native player save");
        });
    }

    private static void EquipmentReactionsUseFunctionalHooksAndSharedCooldown()
    {
        foreach (var role in SwarmRoles)
        foreach (int delay in new[] { 2 })
        {
            using var actors = new SwarmRuntimeScope(role.Mode, role.Local);
            WithPlayer((player, _) => {
                player.active = true; player.dead = false; player.statLife = 100; player.whoAmI = 0; player.direction = 1;
                Terraria.Main.player[0] = player;
                var generated = PeriodicEquipmentItem();
                var data = generated.Data; data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString(); data.RecipeMeta.WorldScoped = true;
                var action = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!.Events.Single();
                action.Event = RuntimeEventKind.OnHurt; action.ReactionCooldownTicks = 6; action.PeriodTicks = 0; action.DelayTicks = delay;
                var owner = player.GetModPlayer<InfiniCraftPlayer>();
                bool authority = role.Mode == NetmodeID.SinglePlayer || role.Mode == NetmodeID.MultiplayerClient && role.Local == 0;
                MaterialClock(100);
                owner.ResetEffects(); ItemLoader.UpdateInventory(generated.Item, player); ItemLoader.UpdateVanity(generated.Item, player);
                owner.PostHurt(new Player.HurtInfo { Damage = 10 }); Equal(0, PendingActions(), "inventory and vanity cannot react");
                ItemLoader.UpdateAccessory(generated.Item, player, false);
                owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                Equal(authority ? 1 : 0, PendingActions(), role.Name + " accepted action reaches delayed scheduler once");
                // Same definition in another functional slot cannot bypass its timer.
                var copy = AttachItem(new GeneratedItem(), new Item { type = ItemID.CopperShortsword, stack = 1 }, data);
                ItemLoader.UpdateAccessory(copy.Item, player, false);
                owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                Equal(authority ? 1 : 0, PendingActions(), "copy shares cooldown");
                MaterialClock(106); owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                Equal(authority ? 2 : 0, PendingActions(), "reaction becomes available at exact interval");
                owner.ResetEffects(); MaterialClock(120); owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                Equal(authority ? 2 : 0, PendingActions(), "unequipping stops reactions");
                RuntimeDelayedActionScheduler.Clear();
                if (role.Mode == NetmodeID.SinglePlayer)
                {
                    action.Event = RuntimeEventKind.OnEnemyKill;
                    ItemLoader.UpdateAccessory(generated.Item, player, false);
                    var victim = new NPC { type = NPCID.Zombie, whoAmI = 0, realLife = -1,
                        lastInteraction = 0, friendly = true, life = 0, lifeMax = 100 };
                    var deaths = new GeneratedEquipmentKillGlobalNPC();
                    deaths.OnKill(victim); Equal(0, PendingActions(), "friendly NPC does not produce kill reaction");
                    victim.friendly = false;
                    deaths.OnKill(victim); Equal(1, PendingActions(), "actual NPC death producer reaches credited owner's reaction");
                    deaths.OnKill(victim); Equal(1, PendingActions(), "duplicate death notification cannot bypass cooldown");
                    RuntimeDelayedActionScheduler.Clear();
                }
            });
        }
    }
}
