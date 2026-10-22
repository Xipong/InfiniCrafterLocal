#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.Utilities;

internal static partial class EngineRuntimeChecks
{
    // Baseline-capable: calls existing native hooks/decoder/scheduler, never a new
    // candidate-only method. No copied gameplay, world loop, GPU or socket result.
    private sealed class Rt01NpcScope : IDisposable
    {
        private static readonly Type Generation = typeof(RuntimeHitNpcGeneration);
        private static FieldInfo Field(string name) => Generation.GetField(name,
            BindingFlags.NonPublic | BindingFlags.Static)!;
        private readonly NPC?[] hosts = (NPC?[])((NPC?[])Field("Hosts").GetValue(null)!).Clone();
        private readonly uint[] tokens = (uint[])((uint[])Field("Tokens").GetValue(null)!).Clone();
        private readonly uint next = (uint)Field("_next").GetValue(null)!;
        private readonly bool goodWorld = Terraria.Main.getGoodWorld;
        private readonly UnifiedRandom random = Terraria.Main.rand;
        private readonly SwarmRuntimeScope actors;
        internal Rt01NpcScope(int mode = NetmodeID.MultiplayerClient)
        {
            actors = new SwarmRuntimeScope(mode);
            RuntimeHitPullBridge.Clear();
            Terraria.Main.getGoodWorld = false;
            Terraria.Main.rand = new UnifiedRandom(17);
            Terraria.Main.player[0].Center = Vector2.Zero;
            MaterialClock(1000);
        }
        public void Dispose()
        {
            RuntimeHitPullBridge.Clear();
            Array.Copy(hosts, (NPC?[])Field("Hosts").GetValue(null)!, hosts.Length);
            Array.Copy(tokens, (uint[])Field("Tokens").GetValue(null)!, tokens.Length);
            Field("_next").SetValue(null, next);
            Terraria.Main.getGoodWorld = goodWorld;
            Terraria.Main.rand = random;
            actors.Dispose();
        }
    }

    private static NPC Rt01Npc(int slot, int type = NPCID.BlueSlime)
    {
        var npc = Terraria.Main.npc[slot] = new NPC();
        npc.SetDefaults(type); // actual tML reset, not type-field substitution
        npc.whoAmI = slot; npc.active = true; npc.Center = new Vector2(100, 0);
        return npc;
    }

    private static void Rt01ReceiveToken(NPC npc, uint token)
    {
        using var stream = new MemoryStream();
        using var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, leaveOpen: true);
        writer.Write(token); writer.Flush(); stream.Position = 0;
        using var reader = new BinaryReader(stream);
        new RuntimeHitNpcGeneration().ReceiveExtraAI(npc, null!, reader);
        Equal(token, RuntimeHitNpcGeneration.Get(npc), "actual NPC ExtraAI decoder installed token");
    }

    private static GeneratedItemData Rt01HitData(string eventName, int delay, bool status = false)
    {
        var data = SwarmGameplayFixture();
        data.RuntimeProgram.TryGetEntity("root")!.Events = new[] {
            status ? new RuntimeEventActionSpec {
                Id = "rt01_status", Event = eventName, Action = "apply_status_on_event",
                ActionCode = RuntimeEventActionCode.ApplyStatus,
                BuffId = BuffID.OnFire, DurationTicks = 90, DelayTicks = delay,
            } : new RuntimeEventActionSpec {
                Id = "rt01_pull", Event = eventName, Action = "pull_on_event",
                ActionCode = RuntimeEventActionCode.Pull, Mode = "owner_to_target",
                Strength = 2, RadiusTiles = 10, DelayTicks = delay,
            },
        };
        return SwarmWire(data); // strict production DTO before the native producer
    }

    private static bool Rt01Transition(NPC target, string state, uint initialToken)
    {
        switch (state)
        {
            case "same": return true;
            case "same-token-decoder": Rt01ReceiveToken(target, initialToken); return true;
            case "transform":
                int netMode = Terraria.Main.netMode;
                Terraria.Main.netMode = NetmodeID.SinglePlayer;
                try { target.Transform(NPCID.Zombie); }
                finally { Terraria.Main.netMode = netMode; }
                Equal(NPCID.Zombie, target.type, "real Transform changed type");
                Equal(true, ReferenceEquals(target, Terraria.Main.npc[0]), "Transform kept NPC object");
                Equal(initialToken, RuntimeHitNpcGeneration.Get(target), "Transform kept incarnation");
                target.Center = new Vector2(100, 0); // keep the direction fixture stable after native height changes
                return true;
            case "inactive": target.active = false; return false;
            case "reference-replacement":
                var replacement = Rt01Npc(0, NPCID.Zombie);
                replacement.Center = new Vector2(0, 100);
                Rt01ReceiveToken(replacement, initialToken); // equality alone cannot replace reference fence
                Equal(false, ReferenceEquals(target, replacement), "replacement is a new object");
                return false;
            case "setdefaults-same-type-new-token":
            case "setdefaults-new-type-new-token":
                target.active = false;
                target.SetDefaults(state == "setdefaults-same-type-new-token" ? NPCID.BlueSlime : NPCID.Zombie);
                target.whoAmI = 0; target.active = true; target.Center = new Vector2(0, 100);
                Equal(true, ReferenceEquals(target, Terraria.Main.npc[0]), "real SetDefaults reused same object");
                Rt01ReceiveToken(target, 42);
                Equal(false, initialToken == RuntimeHitNpcGeneration.Get(target), "reuse received new incarnation");
                return false;
            case "token-cleared": Rt01ReceiveToken(target, 0); return false;
            case "token-arrives-after-enqueue": Rt01ReceiveToken(target, 41); return false;
            default: throw new ArgumentException(state);
        }
    }

    private static void NativeDelayedNpcIncarnationRejectsInPlaceReuse()
    {
        var failures = new List<string>();
        int cases = 0;
        foreach (string eventName in new[] { RuntimeEventKind.OnHit, RuntimeEventKind.OnCrit })
        foreach (string state in new[] { "same", "same-token-decoder", "transform", "inactive",
            "reference-replacement", "setdefaults-same-type-new-token", "setdefaults-new-type-new-token",
            "token-cleared", "token-arrives-after-enqueue" })
        {
            string label = "rt01 owner-client " + eventName + " " + state;
            try
            {
                using var scope = new Rt01NpcScope();
                Player owner = Terraria.Main.player[0]; NPC target = Rt01Npc(0);
                uint token = state == "token-arrives-after-enqueue" ? 0u : 41u;
                Rt01ReceiveToken(target, token);
                var data = Rt01HitData(eventName, 2);
                var generated = SwarmHost(data, data.RuntimeProgram.TryGetEntity("root")!);
                generated.OnHitNPC(target, new NPC.HitInfo { Crit = eventName == RuntimeEventKind.OnCrit }, 10);
                Equal(1, PendingActions(), label + " actual hook enqueued one action");
                bool current = Rt01Transition(target, state, token);
                RuntimeDelayedActionScheduler.Update();
                Equal(Vector2.Zero, owner.velocity, label + " same-count visit is not due");
                MaterialClock(1001); RuntimeDelayedActionScheduler.Update();
                Equal(Vector2.Zero, owner.velocity, label + " one tick early");
                Equal(1, PendingActions(), label + " retained before due");
                MaterialClock(1002); RuntimeDelayedActionScheduler.Update();
                Equal(0, PendingActions(), label + " due action retired");
                Vector2 expected = current ? new Vector2(2, 0) : Vector2.Zero;
                Equal(expected, owner.velocity, label + " only captured incarnation supplies direct target");
                Equal(Vector2.Zero, Terraria.Main.npc[0].velocity, label + " no NPC-mode fallthrough");
                Rt01ReceiveToken(target, token); target.active = true; Terraria.Main.npc[0] = target;
                MaterialClock(1003); RuntimeDelayedActionScheduler.Update();
                Equal(expected, owner.velocity, label + " restoration never replays retired hit");
                cases++;
            }
            catch (Exception error) { failures.Add(label + ": " + error.Message); }
        }
        Console.WriteLine($"DETAIL: rt01 owner-client native hook incarnation variants passed={cases}; no sockets/world/GPU");
        if (failures.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void NativeDelayedNpcStatusRejectsNewIncarnation()
    {
        // SP uses the very same target resolver and real AddBuff, avoiding native
        // MP buff packet emission. This is not a socket-delivery assertion.
        foreach (string state in new[] { "same", "transform", "setdefaults-same-type-new-token",
            "setdefaults-new-type-new-token", "reference-replacement", "inactive" })
        {
            using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
            NPC target = Rt01Npc(0); Rt01ReceiveToken(target, 41);
            Equal(false, target.buffImmune[BuffID.OnFire], state + " original permits real status");
            var data = Rt01HitData(RuntimeEventKind.OnHit, 2, status: true);
            var generated = SwarmHost(data, data.RuntimeProgram.TryGetEntity("root")!);
            generated.OnHitNPC(target, new NPC.HitInfo(), 10);
            Equal(1, PendingActions(), state + " native status hook queued");
            bool current = Rt01Transition(target, state, 41);
            Equal(false, Terraria.Main.npc[0].buffImmune[BuffID.OnFire], state + " current fixture permits status");
            MaterialClock(1001); RuntimeDelayedActionScheduler.Update();
            Equal(false, Terraria.Main.npc[0].HasBuff(BuffID.OnFire), state + " status is not early");
            MaterialClock(1002); RuntimeDelayedActionScheduler.Update();
            Equal(current, Terraria.Main.npc[0].HasBuff(BuffID.OnFire), state + " status cannot cross incarnation");
            Equal(0, PendingActions(), state + " status retired");
            if (current)
            {
                int index = target.FindBuffIndex(BuffID.OnFire);
                Equal(90, target.buffTime[index], state + " actual authored duration");
                target.buffTime[index] = 17;
                MaterialClock(1003); RuntimeDelayedActionScheduler.Update();
                Equal(17, target.buffTime[index], state + " status not refreshed twice");
            }
        }
    }

}
