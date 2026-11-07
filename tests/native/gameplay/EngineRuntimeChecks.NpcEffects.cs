using System;
using System.IO;
using System.Text.Json;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ComposableNpcEffectAdmission()
    {
        var action = JsonSerializer.Deserialize<RuntimeEventActionSpec>("""
            {"Id":"decay","Event":"on_hit","Action":"apply_npc_effect_on_event","ActionCode":11,
             "DurationTicks":120,"NpcEffect":{"LifeRegenPenalty":3,"DefenseDelta":-4,"ContactDamageMultiplier":0.7,"VelocityRetentionPerTick":0.9}}
            """);
        action!.NormalizeAndValidate();
        Equal(120, action.DurationTicks, "timed primitive admitted without native BuffID");
    }

    private static void ComposableNpcEffectExecutesWithoutStatMutation()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
        var npc = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, life = 100,
            defense = 20, damage = 30, velocity = new Microsoft.Xna.Framework.Vector2(10, 0) };
        var hook = new RuntimeHitNpcGeneration(); hook.OnSpawn(npc, owner.GetSource_Misc("check"));
        var action = JsonSerializer.Deserialize<RuntimeEventActionSpec>("""
            {"Id":"decay","Event":"on_hit","Action":"apply_npc_effect_on_event","ActionCode":11,
             "DurationTicks":120,"NpcEffect":{"LifeRegenPenalty":3,"DefenseDelta":-4,"ContactDamageMultiplier":0.7,"VelocityRetentionPerTick":0.9}}
            """)!;
        var data = GeneratedItemData.Placeholder();
        var entity = Entity();
        RuntimeProgramExecutor.ExecuteAction(data, entity, action, owner, owner.GetSource_Misc("check"),
            Microsoft.Xna.Framework.Vector2.Zero, Microsoft.Xna.Framework.Vector2.UnitX, npc, 10, 0, new RuntimeSpawnBudget(0));
        int displayDamage = 0; hook.UpdateLifeRegen(npc, ref displayDamage);
        Equal(-3, npc.lifeRegen, "engine regeneration receives half-HP-per-second resolution");
        hook.PostAI(npc);
        Equal(9f, npc.velocity.X, "post AI velocity damping executes");
        var hit = new NPC.HitModifiers(); hook.ModifyIncomingHit(npc, ref hit);
        Equal(-4f, hit.Defense.Flat, "defense modifier reaches native hit consumer");
        Equal(20, npc.defense, "base defense never mutated");
        var hurt = new Player.HurtModifiers(); hook.ModifyHitPlayer(npc, owner, ref hurt);
        Equal(.7f, hurt.SourceDamage.Multiplicative, "contact-only damage multiplier");
        Equal(30, npc.damage, "base contact damage never mutated");
        var outgoing = new NPC.HitModifiers(); hook.ModifyHitNPC(npc, new NPC(), ref outgoing);
        Equal(.7f, outgoing.SourceDamage.Multiplicative, "contact weakening also reaches friendly NPC combat");
    }

    private static RuntimeEventActionSpec NpcEffectAction(int duration = 120, int delay = 0, float chance = 1f)
        => new() { Id = "decay", Event = "on_hit", Action = "apply_npc_effect_on_event", ActionCode = 11,
            DurationTicks = duration, DelayTicks = delay, NpcEffect = new() { LifeRegenPenalty = 3,
                DefenseDelta = -4, ContactDamageMultiplier = .7f, VelocityRetentionPerTick = .9f, Chance = chance } };

    private static void ComposableNpcEffectOwnerReceipt()
    {
        using var state = new NativeActorState();
        var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
        var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, life = 100 };
        Terraria.Main.netMode = NetmodeID.Server;
        var hook = new RuntimeHitNpcGeneration(); hook.OnSpawn(target, owner.GetSource_Misc("check"));
        var entity = Entity(); entity.Id = "bolt"; entity.Kind = RuntimeEntityKind.FreeProjectile;
        entity.Events = new[] { NpcEffectAction() };
        var data = GeneratedItemData.Placeholder(); data.Id = "npc_effect_item";
        InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
        data.RuntimeProgram.Entities = new[] { entity };
        var sender = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = 0, identity = 72, active = true };
        var generated = Attach(sender);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(sender, generated);
        generated.Configure(data, entity, 0, 0, Microsoft.Xna.Framework.Vector2.UnitX);
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
        using var wire = new MemoryStream();
        using (var writer = new BinaryWriter(wire, System.Text.Encoding.UTF8, true))
            Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, sender, target, false), "numeric effects use bounded existing receipt");
        Terraria.Main.myPlayer = 1;
        using (var writer = new BinaryWriter(new MemoryStream()))
            Equal(false, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, sender, target, false), "remote cannot send numeric effects");
        Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, active = false };
        var receiver = Terraria.Main.projectile[1] = new Projectile { whoAmI = 1, owner = 0, identity = 72, active = true };
        var receiving = Attach(receiver); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(receiver, receiving);
        receiving.Configure(data, entity, 0, 0, Microsoft.Xna.Framework.Vector2.UnitX);
        Terraria.Main.netMode = NetmodeID.Server;
        void Receive(int senderId) { wire.Position = 0; RuntimeHitPullBridge.HandlePacket(new BinaryReader(wire, System.Text.Encoding.UTF8, true), senderId); }
        Receive(1);
        int damage = 0; hook.UpdateLifeRegen(target, ref damage);
        Equal(0, target.lifeRegen, "wrong sender refused");
        Receive(0); hook.UpdateLifeRegen(target, ref damage);
        Equal(-3, target.lifeRegen, "server dispatch actually executes numeric effect");
        // Reset native consumer output each tick as Terraria does; receipt replay must
        // not refresh an existing timer or allocate a second record.
        MaterialClock(Terraria.Main.GameUpdateCount + 120);
        Receive(0); target.lifeRegen = 0; hook.UpdateLifeRegen(target, ref damage);
        Equal(0, target.lifeRegen, "duplicate cannot refresh expired effect");
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
        using var stale = new MemoryStream();
        RuntimeHitPullBridge.TryWriteProjectileReceipt(new BinaryWriter(stale), sender, target, false);
        Terraria.Main.netMode = NetmodeID.Server;
        hook.OnSpawn(target, owner.GetSource_Misc("same-object-replacement"));
        stale.Position = 0; RuntimeHitPullBridge.HandlePacket(new BinaryReader(stale), 0);
        Equal(0, RuntimeNpcEffects.GetTotals(target).Count, "receipt cannot target a reused NPC incarnation");
        Terraria.Main.netMode = NetmodeID.MultiplayerClient;
        using var next = new MemoryStream(); RuntimeHitPullBridge.TryWriteProjectileReceipt(new BinaryWriter(next), sender, target, false);
        byte[] invalid = next.ToArray(); invalid[^1] = 128; // action index 15 is absent from exact server definition
        Terraria.Main.netMode = NetmodeID.Server;
        RuntimeHitPullBridge.HandlePacket(new BinaryReader(new MemoryStream(invalid)), 0);
        Equal(0, RuntimeNpcEffects.GetTotals(target).Count, "foreign effect-mask bit rejected");
        next.Position = 0; RuntimeHitPullBridge.HandlePacket(new BinaryReader(next), 0);
        Equal(1, RuntimeNpcEffects.GetTotals(target).Count, "invalid mask did not consume valid sequence");
    }

    private static void SignedGeneratedBuffConsumersAndPresentation()
    {
        using var state = new NativeActorState(); Terraria.Main.netMode = NetmodeID.SinglePlayer;
        WithPlayer((player, generated) =>
        {
            player.active = true; player.statDefense = new Player.DefenseStat(); player.statDefense += 200;
            var buff = new GeneratedBuffSpec { DurationTicks = 120, MiningSpeedMultiplier = .5f,
                MovementSpeed = -.8f, JumpBoost = -8, ManaRegen = -100, LifeRegen = -100,
                Combat = new() { DefensePoints = -100, AttackSpeedPercent = -80,
                    CritChancePoints = -100, DamagePercent = -90, DamageClass = "generic" } };
            Equal(true, generated.ApplyGeneratedUtilityBuff(buff), "negative buff admitted by live player owner");
            typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetMethod("ApplyGeneratedUtilityBuffEffects",
                System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!.Invoke(generated, null);
            Equal(-8f, player.jumpSpeedBoost, "negative jump reaches native player");
            Equal(-100, player.manaRegenBonus, "negative mana reaches native player");
            Equal(-100, player.lifeRegen, "negative life reaches native player");
            Equal(100, (int)player.statDefense, "negative defense reduces existing native defense");
            var snapshot = generated.CaptureGeneratedUtilityBuffPresentation();
            var rows = InfiniCrafterLocal.Common.UI.GeneratedUtilityBuffStatusView.Build(snapshot, System.Globalization.CultureInfo.InvariantCulture);
            Equal(9, rows.Count, "all eight signed stats plus mining slowdown remain visible");
            foreach (var row in rows) Equal(false, row.Tooltip.Contains("+-"), "signs never become plus-minus");
        });
    }

    private static void SignedGeneratedBuffOrderIndependentAggregation()
    {
        using var state = new NativeActorState(); Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var positive = new GeneratedBuffSpec { DurationTicks = 120, JumpBoost = 8, ManaRegen = 120, LifeRegen = 120 };
        var negative = new GeneratedBuffSpec { DurationTicks = 120, JumpBoost = -8, ManaRegen = -100, LifeRegen = -100 };
        foreach (bool reverse in new[] { false, true })
            WithPlayer((player, generated) =>
            {
                player.active = true;
                generated.ApplyGeneratedUtilityBuff(reverse ? negative : positive);
                generated.ApplyGeneratedUtilityBuff(reverse ? positive : negative);
                var totals = generated.CaptureGeneratedUtilityBuffPresentation().Current;
                Equal(0f, totals.JumpBoost, "signed jump cancellation independent of arrival order");
                Equal(20, totals.ManaRegen, "signed mana sum clamps only after aggregation");
                Equal(20, totals.LifeRegen, "signed life sum clamps only after aggregation");
            });
    }

    private static void SignedGeneratedBuffCompiledWireAndBinaryReplay()
    {
        using var state = new NativeActorState(); Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var authored = GeneratedItemData.Placeholder();
        authored.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 120, MiningSpeedMultiplier = .5f,
            MovementSpeed = -.8f, JumpBoost = -8, ManaRegen = -100, LifeRegen = -100,
            Combat = new() { DefensePoints = -100, AttackSpeedPercent = -80,
                CritChancePoints = -100, DamagePercent = -90, DamageClass = "generic" } };
        string? path = Environment.GetEnvironmentVariable("INFINI_SIGNED_BUFF_WIRE");
        var data = GeneratedItemData.FromJson(path is null ? authored.ToJson() : File.ReadAllText(path))
            ?? throw new Exception("signed compiled fixture refused by strict GeneratedItemData reader: " + ContractJsonDiagnostics.LastError);
        GeneratedBuffSpec buff = (data.RuntimeProgram.EffectGroups ?? Array.Empty<RuntimeItemEffectGroupSpec>())
            .Select(x => x.GeneratedBuff).Append(data.Gameplay.GeneratedBuff).FirstOrDefault(x => x is not null
                && (x.MovementSpeed < 0 || x.JumpBoost < 0 || x.ManaRegen < 0 || x.LifeRegen < 0
                    || x.Combat is { } combat && (combat.DefensePoints < 0 || combat.AttackSpeedPercent < 0
                        || combat.CritChancePoints < 0 || combat.DamagePercent < 0)))
            ?? throw new Exception("compiled fixture must contain an actually negative executable modifier");
        WithPlayer((player, generated) =>
        {
            player.active = true; player.statDefense = new Player.DefenseStat(); player.statDefense += 200;
            player.pickSpeed = 1;
            float movement = player.moveSpeed;
            float speed = player.GetAttackSpeed(Terraria.ModLoader.DamageClass.Generic);
            float crit = player.GetCritChance(Terraria.ModLoader.DamageClass.Generic);
            float damage = player.GetDamage(TerrariaRuntimeVocabulary.ResolveDamageClass(buff.Combat?.DamageClass ?? "generic")).Additive;
            Equal(true, generated.ApplyGeneratedUtilityBuff(buff), "compiled signed wire reaches live player owner");
            var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
            var effects = typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetMethod("ApplyGeneratedUtilityBuffEffects", flags)!;
            effects.Invoke(generated, null);
            Equal(movement + buff.MovementSpeed, player.moveSpeed, "compiled signed movement native consumer");
            Equal(buff.JumpBoost, player.jumpSpeedBoost, "compiled signed jump native consumer");
            Equal(buff.ManaRegen, player.manaRegenBonus, "compiled signed mana native consumer");
            Equal(buff.LifeRegen, player.lifeRegen, "compiled signed regeneration native consumer");
            Equal(200 + (buff.Combat?.DefensePoints ?? 0), (int)player.statDefense, "compiled signed defense native consumer");
            Equal(speed + (buff.Combat?.AttackSpeedPercent ?? 0) / 100f, player.GetAttackSpeed(Terraria.ModLoader.DamageClass.Generic), "compiled signed attack speed native consumer");
            Equal(crit + (buff.Combat?.CritChancePoints ?? 0), player.GetCritChance(Terraria.ModLoader.DamageClass.Generic), "compiled signed crit native consumer");
            Equal(damage + (buff.Combat?.DamagePercent ?? 0) / 100f,
                player.GetDamage(TerrariaRuntimeVocabulary.ResolveDamageClass(buff.Combat?.DamageClass ?? "generic")).Additive,
                "compiled signed class damage native consumer");
            Equal(1f / buff.MiningSpeedMultiplier, player.pickSpeed, "sub-one mining multiplier stays a slowdown");
            using var wire = new MemoryStream();
            typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", flags)!
                .Invoke(generated, new object[] { new BinaryWriter(wire) });
            WithPlayer((peer, received) =>
            {
                wire.Position = 1; // canonical handler consumes the player index first
                typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", flags)!
                    .Invoke(received, new object[] { new BinaryReader(wire) });
                var current = received.CaptureGeneratedUtilityBuffPresentation().Current;
                Equal(buff.JumpBoost, current.JumpBoost, "same binary layout preserves negative jump");
                Equal(buff.ManaRegen, current.ManaRegen, "same binary layout preserves negative mana");
                Equal(buff.LifeRegen, current.LifeRegen, "same binary layout preserves negative regeneration");
                Equal(buff.MovementSpeed, current.MovementSpeed, "same binary layout preserves negative movement");
                Equal(buff.Combat?.DefensePoints ?? 0, current.Defense, "same binary layout preserves signed combat component");
            });
        });
    }

    private static void SignedGeneratedBuffAdmission()
    {
        var combat = new GeneratedCombatBuffSpec { DefensePoints = -100, AttackSpeedPercent = -80,
            CritChancePoints = -100, DamagePercent = -90, DamageClass = "generic" };
        combat.Validate();
        using var wire = new MemoryStream();
        combat.Write(new BinaryWriter(wire)); wire.Position = 0;
        Equal(combat, GeneratedCombatBuffSpec.Read(new BinaryReader(wire)), "signed combat binary roundtrip unchanged layout");
        var buff = new GeneratedBuffSpec { DurationTicks = 60, MovementSpeed = -.8f, JumpBoost = -8,
            ManaRegen = -100, LifeRegen = -100, Combat = combat };
        buff.Normalize();
        Equal(-8f, buff.JumpBoost, "negative jump remains executable");
        Equal(-100, buff.LifeRegen, "negative life regen preserved");
        Equal(true, buff.HasAnyEffect, "negative-only buff has effect");
    }
}
