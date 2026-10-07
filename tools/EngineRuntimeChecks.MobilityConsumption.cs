using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.Utilities;

internal static partial class EngineRuntimeChecks
{
    private const BindingFlags MobilityConsumptionFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

    // Uses only pre-fix public gameplay APIs, so this exact candidate compiles for RED.
    private static void NativePureMobilityConsumptionFollowsUseOutcome()
    {
        using var scope = new MobilityConsumptionNativeScope();
        var failures = new List<string>();
        foreach (string reason in new[] { "cooldown-after-admission", "spawn-after-admission", "successful-recall", "successful-reusable-recall" })
        {
            try
            {
                WithPlayer((player, generated) =>
                {
                    PrepareMobilityConsumptionPlayer(player);
                    bool blink = reason.Contains("blink", StringComparison.Ordinal);
                    var host = MobilityConsumptionHost(MobilityConsumptionFixture(blink ? "blink_to_cursor" : "recall_home", reason == "successful-reusable-recall" ? 0 : 1));
                    player.inventory[0] = host.Item;
                    Equal(true, host.CanUseItem(player), reason + " admission");
                    Vector2 before = player.position;
                    if (reason == "cooldown-after-admission") Equal(true, generated.TryReserveGeneratedMobilityCooldown(30), "intervening mobility uses shared cooldown");
                    if (reason == "spawn-after-admission") player.SpawnX = player.SpawnY = Terraria.Main.spawnTileX = Terraria.Main.spawnTileY = 0;
                    scope.RunNativeSuffix(player);
                    bool successful = reason.StartsWith("successful-", StringComparison.Ordinal);
                    Equal(successful && host.Data.RuntimeProgram.Bindings[0].UsePolicy.StackCost == 1 ? 0 : 1, host.Item.stack, reason + " actual native stack debit");
                    Equal(1, host.UseCalls, reason + " one completed use attempt");
                    Equal(1, player.ItemUsesThisAnimation, reason + " one native itemTime start");
                    Equal(true, player.itemTime > 0, reason + " no zero-time retry loop");
                    if (successful)
                    {
                        Vector2 expected = blink ? new Vector2(1728f - player.width / 2f, 1600f - player.height / 2f)
                            : new Vector2(100 * 16f + 8f - player.width / 2f, 110 * 16f - player.height);
                        Equal(expected, player.position, reason + " actual native Teleport position");
                        Equal(1f, player.teleportTime, reason + " native Teleport completion, not swallowed failure");
                        Equal(60, generated.GeneratedMobilityCooldownTicks, reason + " successful cooldown");
                    }
                    else
                    {
                        Equal(before, player.position, reason + " refused effect did not teleport");
                        Equal(reason == "cooldown-after-admission" ? 30 : 0, generated.GeneratedMobilityCooldownTicks, reason + " no new cooldown on refusal");
                        Equal(true, generated.LastGeneratedMobilityFailureMessage.Length > 0, reason + " real refusal reason");
                    }
                    if (host.ConsumeCalls > 0) Equal("use,consume", string.Join(",", host.Trace), reason + " actual native hook order");
                });
            }
            catch (Exception error) { failures.Add(reason + ": " + error); }
        }
        foreach (string fence in new[] { "consume-before-use", "consume-once", "failure-after-success" })
        {
            try
            {
                WithPlayer((player, generated) =>
                {
                    PrepareMobilityConsumptionPlayer(player);
                    var data = MobilityConsumptionFixture("recall_home", 1);
                    var host = MobilityConsumptionHost(data);
                    player.inventory[0] = host.Item;
                    Equal(true, host.CanUseItem(player), fence + " admission");
                    if (fence != "consume-before-use")
                    {
                        player.ApplyItemTime(host.Item); // REAL native UseItem dispatch and timing.
                        Equal(1f, player.teleportTime, fence + " real successful native teleport");
                    }
                    if (fence == "consume-once") Equal(true, ItemLoader.ConsumeItem(host.Item, player), fence + " first debit authorized");
                    if (fence == "failure-after-success")
                    {
                        // Calling the real hook again while cooldown is active replaces the success with refusal.
                        Equal(true, host.UseItem(player) == true, "refused pure attempt still completes native timing policy");
                    }
                    Equal(false, ItemLoader.ConsumeItem(host.Item, player), fence + " no borrowed/replayed successful outcome");
                    Equal(1, host.Item.stack, fence + " gate does not mutate stack itself");
                });
            }
            catch (Exception error) { failures.Add(fence + ": " + error); }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void NativeMixedMobilityRefusalPreservesOtherEffectsOnce()
    {
        using var scope = new MobilityConsumptionNativeScope();
        var failures = new List<string>();
        foreach (string companion in new[] { "heal-life", "heal-mana", "native-buff", "extra-buff", "generated-buff", "all" })
        {
            try
            {
                WithPlayer((player, generated) =>
                {
                    PrepareMobilityConsumptionPlayer(player);
                    var data = MobilityConsumptionFixture("recall_home", 1);
                    bool life = companion is "heal-life" or "all", mana = companion is "heal-mana" or "all";
                    bool native = companion is "native-buff" or "all", extra = companion is "extra-buff" or "all";
                    bool utility = companion is "generated-buff" or "all";
                    data.Gameplay.HealLife = life ? 7 : 0;
                    data.Gameplay.HealMana = mana ? 5 : 0;
                    data.Gameplay.BuffCode = native ? BuffID.Ironskin : 0;
                    data.Gameplay.BuffTime = native ? 60 : 0;
                    data.Gameplay.ExtraBuffs = extra ? new[] { new BuffEntrySpec { BuffCode = BuffID.Swiftness, BuffTime = 60 } } : Array.Empty<BuffEntrySpec>();
                    data.Gameplay.GeneratedBuff = utility ? new GeneratedBuffSpec { DurationTicks = 60, MovementSpeed = .25f } : new GeneratedBuffSpec();
                    var host = MobilityConsumptionHost(data);
                    player.inventory[0] = host.Item;
                    Equal(true, host.CanUseItem(player), companion + " mixed admission");
                    Equal(true, generated.TryReserveGeneratedMobilityCooldown(30), companion + " post-admission refusal trigger");
                    Vector2 before = player.position;
                    scope.RunNativeSuffix(player);
                    Equal(before, player.position, companion + " refused mobility did not move player");
                    Equal(30, generated.GeneratedMobilityCooldownTicks, companion + " no second cooldown");
                    Equal(57 + (life ? 7 : 0), player.statLife, companion + " real native healing exactly once");
                    Equal(20 + (mana ? 5 : 0), player.statMana, companion + " real native mana exactly once");
                    Equal(native, player.HasBuff(BuffID.Ironskin), companion + " independent native buff retained");
                    Equal(extra, player.HasBuff(BuffID.Swiftness), companion + " independent extra buff retained");
                    generated.PostUpdateEquips();
                    Equal(utility ? 1.25f : 1f, player.moveSpeed, companion + " actual generated buff player hook retained");
                    Equal(1, host.UseCalls, companion + " no false-return native retry duplicates");
                    Equal("use,consume", string.Join(",", host.Trace), companion + " real native hooks, not assumed order");
                    // Native applies timing again for its heal/mana block and
                    // separately for buffType; that counter is not a UseItem count.
                    Equal(1 + (life || mana ? 1 : 0) + (native ? 1 : 0), player.ItemUsesThisAnimation,
                        companion + " native timing follows retained effect lanes");
                    Equal(0, host.Item.stack, companion + " successful companion keeps authored stack cost");
                });
            }
            catch (Exception error) { failures.Add(companion + ": " + error); }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static GeneratedItemData MobilityConsumptionFixture(string mode, int stackCost)
    {
        var data = GeneratedItemData.Placeholder();
        data.Gameplay.Damage = 0;
        data.Gameplay.UseStyleName = "hold_up";
        data.Gameplay.UseStyle = ItemUseStyleID.HoldUp;
        data.Gameplay.UseTime = data.Gameplay.UseAnimation = 20;
        data.Gameplay.MobilityMode = mode;
        data.Gameplay.MobilityRangeTiles = mode == "blink_to_cursor" ? 120 : 0;
        data.Gameplay.MobilityCooldownTicks = 60;
        data.Gameplay.MobilitySafeTileOnly = true;
        data.RuntimeProgram.ItemUse.Configured = true;
        data.RuntimeProgram.ItemUse.UseStyle = "hold_up";
        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
            Id = "mobility", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec { StackCost = stackCost, ContactDamage = false,
                Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.ApplyItemEffects, TargetId = data.RuntimeProgram.ItemEntityId } } } };
        return data;
    }

    private static MobilityConsumptionProbeItem MobilityConsumptionHost(GeneratedItemData data)
    {
        var item = new Item();
        item.SetDefaults(ItemID.CopperShortsword); // Real defaults: avoid unrelated shell mount/fishing/hair fields.
        item.stack = 1;
        var host = new MobilityConsumptionProbeItem();
        typeof(ModType<Item>).GetProperty("Entity", MobilityConsumptionFlags)!.SetValue(host, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, host);
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(host, data);
        host.SetDefaults();
        Equal(true, ReferenceEquals(data, host.Data), "fixture projection keeps supplied definition");
        return host;
    }

    private static void PrepareMobilityConsumptionPlayer(Player player)
    {
        Terraria.Main.myPlayer = player.whoAmI = 1;
        Terraria.Main.player[1] = player;
        player.active = true;
        player.SpawnX = 100; player.SpawnY = 110;
        player.Center = new Vector2(1600f, 1600f);
        player.statLife = 57; player.statLifeMax2 = 100;
        player.statMana = 20; player.statManaMax2 = 100;
        player.moveSpeed = player.pickSpeed = 1f;
        player.selectedItem = 0;
        player.itemAnimation = player.itemAnimationMax = 20;
        player.itemTime = player.itemTimeMax = 0;
        typeof(Player).GetProperty(nameof(Player.ItemUsesThisAnimation), MobilityConsumptionFlags)!.SetValue(player, 0);
        Terraria.Main.spawnTileX = 100; Terraria.Main.spawnTileY = 110;
        Terraria.Main.mouseX = Terraria.Main.mouseY = 0;
        Terraria.Main.screenPosition = new Vector2(1728f, 1600f);
    }

    private sealed class MobilityConsumptionProbeItem : GeneratedItem
    {
        internal int UseCalls, ConsumeCalls;
        internal readonly List<string> Trace = new();
        public override bool? UseItem(Player player) { UseCalls++; Trace.Add("use"); return base.UseItem(player); }
        public override bool ConsumeItem(Player player) { ConsumeCalls++; Trace.Add("consume"); return base.ConsumeItem(player); }
    }

    private sealed class MobilityConsumptionNativeScope : IDisposable
    {
        private readonly SwarmRuntimeScope actors = new(myPlayer: 1);
        private readonly Dust[] dust = Terraria.Main.dust;
        private readonly UnifiedRandom random = Terraria.Main.rand;
        private readonly int mouseX = Terraria.Main.mouseX, mouseY = Terraria.Main.mouseY;
        private readonly int spawnX = Terraria.Main.spawnTileX, spawnY = Terraria.Main.spawnTileY;
        private readonly Vector2 screen = Terraria.Main.screenPosition;
        private readonly FieldInfo positionsField = typeof(PressurePlateHelper).GetField("PlayerLastPosition", MobilityConsumptionFlags)!;
        private readonly object? positions;
        private readonly List<IDisposable> hooks = new();
        private readonly MethodInfo native = typeof(Player).GetMethod("ItemCheck_Inner", MobilityConsumptionFlags)!;
        internal MobilityConsumptionNativeScope()
        {
            positions = positionsField.GetValue(null);
            try
            {
                Terraria.Main.dust = new Dust[6001];
                for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust();
                Terraria.Main.rand = new UnifiedRandom(7);
                positionsField.SetValue(null, new Vector2[255]);
                MaterialClock(2000);
                // Skip only unrelated camera/biome presentation, not the actual native teleport.
                hooks.Add(new Hook(typeof(Player).GetMethod(nameof(Player.Teleport))!,
                    (Action<Action<Player, Vector2, int, int>, Player, Vector2, int, int>)((orig, p, target, style, info) => {
                        int local = Terraria.Main.myPlayer;
                        Terraria.Main.myPlayer = 0;
                        try { orig(p, target, style, info); }
                        finally { Terraria.Main.myPlayer = local; }
                    })));
                hooks.Add(new Hook(typeof(Player).GetMethod(nameof(Player.HealEffect))!, (Action<Player, int, bool>)((p, amount, broadcast) => { })));
                hooks.Add(new Hook(typeof(Player).GetMethod(nameof(Player.ManaEffect))!, (Action<Player, int>)((p, amount) => { })));
                hooks.Add(new ILHook(native, il => {
                    // Execute the ORIGINAL native generic-use tail, including UseItem,
                    // ApplyItemTime, ApplyLifeAndOrMana, AddBuff, ConsumeItem and stack--.
                    // The native prefix/world-owner path is outside this CPU seam.
                    if (il.Body.Variables.Count < 2 || il.Body.Variables[1].VariableType.FullName != typeof(Item).FullName)
                    {
                        var variables = new List<string>();
                        foreach (var variable in il.Body.Variables) variables.Add(variable.Index + ":" + variable.VariableType.FullName);
                        throw new InvalidOperationException("native ItemCheck item-local shape changed: " + string.Join(",", variables));
                    }
                    // The installed optimized native body uses SkipLocalsInit.
                    // This suffix-only fixture bypasses prefix initialization, so
                    // initialize otherwise unused locals rather than read undefined data.
                    il.Body.InitLocals = true;
                    var c = new ILCursor(il);
                    if (!c.TryGotoNext(MoveType.After, i => i.MatchCall<Player>("ItemCheck_OwnerOnlyCode")))
                        throw new InvalidOperationException("native generic-use tail boundary missing");
                    var tail = c.MarkLabel();
                    c.Goto(0);
                    c.Emit(OpCodes.Ldarg_0);
                    c.EmitDelegate<Func<Player, Item>>(p => p.HeldItem);
                    c.Emit(OpCodes.Stloc, il.Body.Variables[1]);
                    c.Emit(OpCodes.Br, tail);
                }));
            }
            catch { Dispose(); throw; }
        }
        internal void RunNativeSuffix(Player player)
        {
            try { native.Invoke(player, null); }
            catch (TargetInvocationException error) when (error.InnerException is not null) { throw error.InnerException; }
        }
        public void Dispose()
        {
            for (int i = hooks.Count - 1; i >= 0; i--) hooks[i].Dispose();
            hooks.Clear();
            positionsField.SetValue(null, positions);
            Terraria.Main.dust = dust; Terraria.Main.rand = random;
            Terraria.Main.mouseX = mouseX; Terraria.Main.mouseY = mouseY;
            Terraria.Main.spawnTileX = spawnX; Terraria.Main.spawnTileY = spawnY;
            Terraria.Main.screenPosition = screen;
            actors.Dispose();
        }
    }
}
