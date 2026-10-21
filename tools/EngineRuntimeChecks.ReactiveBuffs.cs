using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItem ReactiveUtilityItem(int delay = 0, int? exhaustion = null)
    {
        var generated = PeriodicEquipmentItem();
        var data = generated.Data;
        data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString(); data.RecipeMeta.WorldScoped = true;
        var body = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!;
        body.Events = new[] { new RuntimeEventActionSpec {
            Id = "reaction_utility", Event = RuntimeEventKind.OnHurt,
            Action = "apply_generated_buff_on_event", ActionCode = RuntimeEventActionCode.ApplyGeneratedBuff,
            EffectGroupId = "escape", ReactionCooldownTicks = 6, DelayTicks = delay } };
        data.RuntimeProgram.EffectGroups = new[] { new RuntimeItemEffectGroupSpec {
            Id = "escape", GeneratedBuff = new GeneratedBuffSpec {
                DurationTicks = 60, MovementSpeed = .25f, JumpBoost = 1f, ExhaustionTicks = exhaustion } } };
        data.RuntimeProgram.NormalizeAndValidate();
        return generated;
    }

    private static void ReactiveUtilityBuffUsesEquipmentAuthorityAndCooldown()
    {
        // Local prediction/aggregation does not need packet interception. The
        // separate canonical-server roundtrip check covers server confirmation.
        foreach (var role in SwarmRoles.Where(role => role.Mode != NetmodeID.Server))
        {
            using var actors = new SwarmRuntimeScope(role.Mode, role.Local);
            WithPlayer((player, _) => {
                player.active = true; player.dead = false; player.statLife = 100; player.whoAmI = 0;
                Terraria.Main.player[0] = player;
                var generated = ReactiveUtilityItem();
                var owner = player.GetModPlayer<InfiniCraftPlayer>();
                bool authority = role.Mode == NetmodeID.SinglePlayer
                    || role.Mode == NetmodeID.MultiplayerClient && role.Local == 0;
                MaterialClock(100); owner.ResetEffects();
                ItemLoader.UpdateInventory(generated.Item, player); ItemLoader.UpdateVanity(generated.Item, player);
                owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                Equal(0, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "inventory and vanity cannot apply reactive buff");
                ItemLoader.UpdateAccessory(generated.Item, player, false);
                owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                Equal(authority ? 1 : 0, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, role.Name + " exact local owner applies real utility entry");
                if (authority)
                {
                    Equal(.25f, owner.CaptureGeneratedUtilityBuffPresentation().Current.MovementSpeed, "authored movement bonus reaches aggregate");
                    ExhaustionBuffTick(owner);
                    var copy = AttachItem(new GeneratedItem(), new Item { type = ItemID.CopperShortsword, stack = 1 }, generated.Data);
                    ItemLoader.UpdateAccessory(copy.Item, player, false);
                    MaterialClock(101); owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                    Equal(59, ExhaustionBuffTicks(owner), "same definition copy cannot refresh before reaction cooldown");
                    MaterialClock(106); owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                    Equal(60, ExhaustionBuffTicks(owner), "exact cooldown boundary refreshes utility duration");
                    Equal(1, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "equal utility refresh never stacks strength");
                    ExhaustionBuffTick(owner); owner.ResetEffects(); MaterialClock(112);
                    owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                    Equal(59, ExhaustionBuffTicks(owner), "unequipped item cannot refresh utility");
                }
                RuntimeDelayedActionScheduler.Clear();
            });
        }
        using var local = new SwarmRuntimeScope();
        WithPlayer((player, _) => {
            player.active = true; player.dead = false; player.statLife = 100; player.whoAmI = 0;
            Terraria.Main.player[0] = player;
            var generated = ReactiveUtilityItem(delay: 2, exhaustion: 120);
            var owner = player.GetModPlayer<InfiniCraftPlayer>();
            MaterialClock(200); owner.ResetEffects(); ItemLoader.UpdateAccessory(generated.Item, player, false);
            owner.PostHurt(new Player.HurtInfo { Damage = 10 });
            Equal(0, ExhaustionBuffTicks(owner), "delayed reaction does not apply early");
            Equal(1, PendingActions(), "real delayed scheduler owns pending buff action");
            MaterialClock(202); RuntimeDelayedActionScheduler.Update();
            Equal(60, ExhaustionBuffTicks(owner), "due action applies real utility group");
            Equal(1, ExhaustionRows(owner).Count, "existing source-scoped exhaustion is reserved");
            ExhaustionBuffTick(owner); MaterialClock(206); owner.PostHurt(new Player.HurtInfo { Damage = 10 });
            MaterialClock(208); RuntimeDelayedActionScheduler.Update();
            Equal(59, ExhaustionBuffTicks(owner), "item exhaustion prevents refresh even after reaction cooldown");
            Equal(0, PendingActions(), "refused exhausted action retires without repeated refresh");
            RuntimeDelayedActionScheduler.Clear();
        });
    }

    private static void ReactiveUtilityBuffDtoKeepsExactGroupOwnership()
    {
        using var actors = new SwarmRuntimeScope();
        var generated = ReactiveUtilityItem();
        var runtime = generated.Data.RuntimeProgram;
        string wire = generated.Data.ToNetworkJson();
        var round = GeneratedItemData.FromJson(wire)
            ?? throw new InvalidOperationException("reactive utility roundtrip refused: " + ContractJsonDiagnostics.LastError);
        Equal("escape", round.RuntimeProgram.TryGetEntity(round.RuntimeProgram.ItemEntityId)!.Events.Single().EffectGroupId, "persisted exact group survives strict reader");
        var action = runtime.TryGetEntity(runtime.ItemEntityId)!.Events.Single();
        void Refused(Action mutate, string reason)
        {
            mutate(); bool refused = false;
            try { runtime.NormalizeAndValidate(); } catch (InvalidDataException) { refused = true; }
            Equal(true, refused, reason);
        }
        Refused(() => action.EffectGroupId = "missing", "missing group refuses"); action.EffectGroupId = "escape";
        Refused(() => runtime.EffectGroups![0].HealLife = 1, "healing cannot hide inside generated-buff reaction"); runtime.EffectGroups![0].HealLife = 0;
        Refused(() => action.ActionCode = RuntimeEventActionCode.DamageArea, "group field cannot attach to unrelated opcode");
    }
}
