using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItem ReactionPresentationItem()
    {
        var item = PeriodicEquipmentItem();
        item.Data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString();
        item.Data.RecipeMeta.WorldScoped = true;
        item.Data.Name = "Copper reaction charm";
        item.Data.Visual.SpritePath = "reaction-charm.png";
        var action = item.Data.RuntimeProgram.TryGetEntity(item.Data.RuntimeProgram.ItemEntityId)!.Events.Single();
        action.Id = "hurt_reaction"; action.Event = RuntimeEventKind.OnHurt;
        action.ReactionCooldownTicks = 121; action.PeriodTicks = 0; action.DelayTicks = 2;
        return item;
    }

    private static void ReactionCooldownPresentationKeepsFunctionalIdentityAndTimers()
    {
        using var actors = new SwarmRuntimeScope();
        WithForgePresentationLanguages(locale => WithPlayer((player, owner) =>
        {
            player.active = true; player.dead = false; player.statLife = 100; player.whoAmI = 0;
            Terraria.Main.player[0] = player; MaterialClock(100);
            var generated = ReactionPresentationItem();
            RuntimeEntitySpec body = generated.Data.RuntimeProgram.TryGetEntity(generated.Data.RuntimeProgram.ItemEntityId)!;
            var kill = System.Text.Json.JsonSerializer.Deserialize<RuntimeEventActionSpec>(System.Text.Json.JsonSerializer.Serialize(body.Events[0]))!;
            kill.Id = "kill_reaction"; kill.Event = RuntimeEventKind.OnEnemyKill; kill.ReactionCooldownTicks = 181;
            body.Events = new[] { body.Events[0], kill };
            ItemLoader.UpdateInventory(generated.Item, player); ItemLoader.UpdateVanity(generated.Item, player);
            owner.PostHurt(new Player.HurtInfo { Damage = 10 });
            Equal(0, owner.CaptureGeneratedReactionCooldowns().Count, "inventory and vanity cannot advertise active equipment cooldowns");
            ItemLoader.UpdateAccessory(generated.Item, player, false);
            var copy = AttachItem(new GeneratedItem(), new Item { type = ItemID.CopperShortsword, stack = 1 }, generated.Data);
            ItemLoader.UpdateAccessory(copy.Item, player, false);
            owner.PostHurt(new Player.HurtInfo { Damage = 10 });
            owner.RunEquipmentReaction(RuntimeEventKind.OnEnemyKill, player.Center);
            var snapshot = owner.CaptureGeneratedReactionCooldowns();
            Equal(2, snapshot.Count, "copy deduplicated per exact item/action; independent hurt and kill timers retained");
            Equal(121, snapshot.Single(r => r.Event == RuntimeEventKind.OnHurt).RemainingTicks, "hurt countdown exact");
            Equal(181, snapshot.Single(r => r.Event == RuntimeEventKind.OnEnemyKill).RemainingTicks, "kill countdown independent");
            var timers = (Dictionary<(string, string), (uint, int)>)typeof(InfiniCraftPlayer).GetField("_reactionCooldowns", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(owner)!;
            var before = timers.ToArray();
            var rows = GeneratedReactionCooldownStatusView.Build(snapshot, Language.ActiveCulture.CultureInfo);
            Equal(2, rows.Count, "each action gets a row");
            Equal(true, rows.All(r => r.SpritePath == "reaction-charm.png" && r.Label.Contains("Copper reaction charm")
                && !r.Label.Contains("Mods.InfiniCrafterLocal.") && !r.Tooltip.Contains("Mods.InfiniCrafterLocal.")), "actual sprite and localized source labels");
            Equal(true, rows.Single(r => r.ActionId == "hurt_reaction").Label.Contains(locale == "ru-RU" ? "получении урона" : "taking damage"), "hurt trigger visible");
            Equal(true, rows.Single(r => r.ActionId == "kill_reaction").Label.Contains(locale == "ru-RU" ? "убийстве врага" : "enemy kill"), "kill trigger visible");
            Equal(true, rows.Single(r => r.ActionId == "hurt_reaction").Tooltip.Contains("3"), "positive fractional seconds round up in tooltip");
            generated.Data.Name = "[i:1]\n" + new string('x', 200);
            var safe = GeneratedReactionCooldownStatusView.Build(owner.CaptureGeneratedReactionCooldowns(), Language.ActiveCulture.CultureInfo).First();
            Equal(false, safe.Label.Contains('[') || safe.Label.Any(char.IsControl), "untrusted name cannot inject HUD tags or extra lines");
            Equal("Copper reaction charm", snapshot[0].ItemName, "snapshot detached from mutable definition");
            MaterialClock(161);
            Equal(60, owner.CaptureGeneratedReactionCooldowns().Single(r => r.Event == RuntimeEventKind.OnHurt).RemainingTicks, "world clock read yields exact remaining time");
            owner.ResetEffects();
            Equal(0, owner.CaptureGeneratedReactionCooldowns().Count, "unequipped items hidden");
            ItemLoader.UpdateVanity(generated.Item, player);
            Equal(0, owner.CaptureGeneratedReactionCooldowns().Count, "vanity still hidden despite retained timer");
            ItemLoader.UpdateAccessory(generated.Item, player, false);
            Equal(60, owner.CaptureGeneratedReactionCooldowns().Single(r => r.Event == RuntimeEventKind.OnHurt).RemainingTicks, "reequip does not reset cooldown");
            player.dead = true; Equal(0, owner.CaptureGeneratedReactionCooldowns().Count, "dead player has no functional status rows"); player.dead = false;
            generated.Data.RecipeMeta.WorldId += "-foreign";
            Equal(0, owner.CaptureGeneratedReactionCooldowns().Count, "foreign-world definitions hidden");
            generated.Data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString();
            MaterialClock(280);
            Equal(1, owner.CaptureGeneratedReactionCooldowns().Single().RemainingTicks, "expired hurt omitted; last kill tick retained");
            MaterialClock(281); Equal(0, owner.CaptureGeneratedReactionCooldowns().Count, "exact expiry has no row");
            Equal(true, before.SequenceEqual(timers.ToArray()), "capture and localization never prune, advance or create owner timers");
            RuntimeDelayedActionScheduler.Clear();
        }));
    }

    private static void ReactionCooldownPresentationReachesActualHudWithFittedSprite()
    {
        using var state = new NativeActorState();
        using var peers = new ReviewPeers();
        using var cache = new RuntimeSpriteCache();
        var spriteProperty = typeof(InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
        object? oldSprites = spriteProperty.GetValue(null);
        var texture = CpuTexture(96, 48);
        bool oldMenu = Terraria.Main.gameMenu, oldHide = Terraria.Main.hideUI, oldInventory = Terraria.Main.playerInventory;
        bool oldOptions = Terraria.Main.ingameOptionsWindow, oldFancy = Terraria.Main.inFancyUI, oldMap = Terraria.Main.mapFullscreen;
        int oldPage = Terraria.Main.EquipPage, oldWidth = Terraria.Main.screenWidth, oldHeight = Terraria.Main.screenHeight;
        int oldMouseX = Terraria.Main.mouseX, oldMouseY = Terraria.Main.mouseY;
        var paints = new List<(Texture2D Texture, Vector2 Position, float Scale)>();
        var times = new List<string>();
        var tooltips = new List<string>();
        var ui = typeof(GeneratedUtilityBuffUISystem);
        MethodInfo draw = ui.GetMethod("DrawStatuses", BindingFlags.Static | BindingFlags.NonPublic)!;
        MethodInfo status = ui.GetMethod("DrawStatus", BindingFlags.Static | BindingFlags.NonPublic)!;
        using var readSprite = new Hook(typeof(RuntimeSpriteCache).GetMethod("TryGet", new[] { typeof(string) })!,
            (RuntimeSpriteCache _, string path) => path == "reaction-charm.png" ? texture : null);
        using var drawBoundary = new ILHook(status, il =>
        {
            var cursor = new ILCursor(il);
            while (cursor.TryGotoNext(i => i.Operand is MethodReference m &&
                ((m.DeclaringType.FullName == typeof(SpriteBatch).FullName && m.Name == "Draw")
                || (m.DeclaringType.FullName == typeof(Utils).FullName && m.Name == "DrawBorderString")
                || (m.DeclaringType.FullName == typeof(Terraria.Main).FullName && m.Name == "MouseText"))))
            {
                var call = (MethodReference)cursor.Next!.Operand;
                PresentationExhaustionStoreCall(il, cursor, call, locals =>
                {
                    if (call.Name == "Draw")
                    {
                        cursor.Emit(OpCodes.Ldloc, locals[1]); cursor.Emit(OpCodes.Ldloc, locals[2]); cursor.Emit(OpCodes.Ldloc, locals[7]);
                        cursor.EmitDelegate<Action<Texture2D, Vector2, float>>((image, at, scale) => paints.Add((image, at, scale)));
                    }
                    else if (call.Name == "DrawBorderString")
                    { cursor.Emit(OpCodes.Ldloc, locals[1]); cursor.EmitDelegate<Action<string>>(text => times.Add(text)); }
                    else
                    { cursor.Emit(OpCodes.Ldloc, locals[1]); cursor.EmitDelegate<Action<string>>(text => tooltips.Add(text)); }
                });
            }
        });
        try
        {
            spriteProperty.SetValue(null, cache);
            Terraria.Main.gameMenu = Terraria.Main.hideUI = Terraria.Main.ingameOptionsWindow = Terraria.Main.inFancyUI = Terraria.Main.mapFullscreen = false;
            Terraria.Main.screenWidth = 1280; Terraria.Main.screenHeight = 800;
            WithForgePresentationLanguages(locale => WithPlayer((player, owner) =>
            {
                player.active = true; player.dead = false; player.statLife = 100; player.whoAmI = 0; player.itemAnimation = 0;
                Terraria.Main.player[0] = player; MaterialClock(100); Terraria.Main.dedServ = true;
                var generated = ReactionPresentationItem();
                ItemLoader.UpdateAccessory(generated.Item, player, false); owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                Terraria.Main.dedServ = false;
                int[] buffs = (int[])player.buffType.Clone();
                foreach (bool inventory in new[] { false, true })
                {
                    Terraria.Main.playerInventory = inventory; Terraria.Main.EquipPage = 2;
                    Terraria.Main.mouseX = Terraria.Main.mouseY = -100;
                    paints.Clear(); times.Clear(); tooltips.Clear(); draw.Invoke(null, null);
                    Equal(1, paints.Count, "real HUD and equipment-page consumer draws one action row");
                    Equal(true, ReferenceEquals(texture, paints[0].Texture), "accepted item's actual sprite reaches renderer");
                    Equal(1f / 3f, paints[0].Scale, "96x48 item is fitted proportionally into 32x32 slot");
                    Equal(1, times.Count, "own remaining countdown reaches native text draw");
                    var point = GeneratedUtilityBuffStatusView.IconPosition(0, inventory, 1280, 800,
                        inventory ? (int)typeof(Terraria.Main).GetField("mH", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)! : 0, Terraria.Main.mapStyle);
                    Terraria.Main.mouseX = point.X + 2; Terraria.Main.mouseY = point.Y + 2;
                    draw.Invoke(null, null);
                    Equal(true, tooltips.Any(t => t.Contains("Copper reaction charm") && t.Contains("3")), "real hover receives item, trigger and ceil countdown");
                }
                Equal(true, buffs.SequenceEqual(player.buffType), "HUD creates no gameplay buff slots");
                owner.ResetEffects(); paints.Clear(); draw.Invoke(null, null);
                Equal(0, paints.Count, "actual HUD immediately hides unequipped source");
                RuntimeDelayedActionScheduler.Clear();
            }));
        }
        finally
        {
            spriteProperty.SetValue(null, oldSprites);
            Terraria.Main.gameMenu = oldMenu; Terraria.Main.hideUI = oldHide; Terraria.Main.playerInventory = oldInventory;
            Terraria.Main.ingameOptionsWindow = oldOptions; Terraria.Main.inFancyUI = oldFancy; Terraria.Main.mapFullscreen = oldMap;
            Terraria.Main.EquipPage = oldPage; Terraria.Main.screenWidth = oldWidth; Terraria.Main.screenHeight = oldHeight;
            Terraria.Main.mouseX = oldMouseX; Terraria.Main.mouseY = oldMouseY;
        }
    }
}
