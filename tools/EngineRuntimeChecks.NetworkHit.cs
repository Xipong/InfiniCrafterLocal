using System;
using System.IO;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void OwnerHitNpcEffectsUseNativeSync()
    {
        var oldOwner = Terraria.Main.player[0]; var oldNpc = Terraria.Main.npc[0];
        var oldProjectile = Terraria.Main.projectile[0];
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        try
        {
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true };
            var action = new RuntimeEventActionSpec { Id = "burn", Event = "on_hit", Action = "apply_status_on_event",
                ActionCode = RuntimeEventActionCode.ApplyStatus, BuffId = BuffID.OnFire, DurationTicks = 120 };
            var entity = Entity(); entity.Id = "bolt"; entity.Kind = RuntimeEntityKind.FreeProjectile;
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            Equal(true, RuntimeProgramExecutor.ShouldRunNpcEvent(action, owner), "owner hit selected for native status sync");
            Terraria.Main.myPlayer = 1;
            Equal(false, RuntimeProgramExecutor.ShouldRunNpcEvent(action, owner), "remote peer cannot apply owner hit");
            Terraria.Main.netMode = NetmodeID.Server;
            Equal(false, RuntimeProgramExecutor.ShouldRunNpcEvent(action, owner), "server does not replay owner's hit");
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            RuntimeProgramExecutor.ExecuteAction(GeneratedItemData.Placeholder(), entity, action, owner,
                owner.GetSource_Misc("check"), Vector2.Zero, Vector2.UnitX, Terraria.Main.npc[0], 10, 0, new RuntimeSpawnBudget(0));
            Equal(true, Terraria.Main.npc[0].HasBuff(BuffID.OnFire), "SP hit applies authored status");
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true };
            entity.Events = new[] { action };
            var data = GeneratedItemData.Placeholder(); data.Id = "status_item";
            data.RuntimeProgram.Entities = new[] { entity };
            var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = 0, active = true };
            var generated = Attach(projectile);
            generated.Configure(data, entity, 0, 0, Vector2.UnitX);
            generated.OnHitNPC(target, new NPC.HitInfo(), 10);
            Equal(true, target.HasBuff(BuffID.OnFire), "actual projectile SP hit hook runs authored status");
            target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true };
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            int packetType = -1, packetNpc = -1, packetBuff = -1, packetDuration = -1;
            Action<int, int, int, NetworkText, int, float, float, float, int, int, int> intercept =
                (msgType, remote, ignore, text, number, number2, number3, number4, number5, number6, number7) =>
                { packetType = msgType; packetNpc = number; packetBuff = (int)number2; packetDuration = (int)number3; };
            using (var hook = new Hook(typeof(NetMessage).GetMethod(nameof(NetMessage.SendData),
                new[] { typeof(int), typeof(int), typeof(int), typeof(NetworkText), typeof(int),
                    typeof(float), typeof(float), typeof(float), typeof(int), typeof(int), typeof(int) })!, intercept))
            {
                generated.OnHitNPC(target, new NPC.HitInfo(), 10);
                Equal(true, target.HasBuff(BuffID.OnFire), "owner client applies status");
                Equal(53, packetType, "native NPC buff packet reaches network boundary");
                Equal(0, packetNpc, "native packet targets the struck NPC");
                Equal(BuffID.OnFire, packetBuff, "native packet carries authored status");
                Equal(120, packetDuration, "native packet carries authored duration");
                target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true };
                Terraria.Main.myPlayer = 1; packetType = -1;
                generated.OnHitNPC(target, new NPC.HitInfo(), 10);
                Equal(false, target.HasBuff(BuffID.OnFire), "remote hook cannot apply owner's status");
                Equal(-1, packetType, "remote hook cannot emit owner's native buff packet");
            }
            target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true };
            Terraria.Main.netMode = NetmodeID.Server;
            generated.OnHitNPC(target, new NPC.HitInfo(), 10);
            Equal(false, target.HasBuff(BuffID.OnFire), "direct server hook cannot replay owner hit");
        }
        finally { Terraria.Main.player[0] = oldOwner; Terraria.Main.npc[0] = oldNpc; Terraria.Main.projectile[0] = oldProjectile; Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal; }
    }

    private static void OwnerProjectileHitBridgesNpcPull()
    {
        var previousOwner = Terraria.Main.player[0]; var previousNpc = Terraria.Main.npc[0];
        var previousProjectile = Terraria.Main.projectile[0];
        var previousReceiverProjectile = Terraria.Main.projectile[1];
        int previousMode = Terraria.Main.netMode, previousLocal = Terraria.Main.myPlayer;
        try
        {
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            owner.Center = Vector2.Zero;
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true,
                position = new Vector2(64, 0), width = 20, height = 20, knockBackResist = 1f };
            var entity = Entity(); entity.Id = "bolt"; entity.Kind = RuntimeEntityKind.FreeProjectile;
            Terraria.Main.netMode = NetmodeID.Server;
            new RuntimeHitNpcGeneration().OnSpawn(target, owner.GetSource_Misc("spawn"));
            entity.Events = new[] { new RuntimeEventActionSpec { Id = "pull", Event = RuntimeEventKind.OnHit,
                Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull, Mode = "target_to_owner",
                Strength = 2f, RadiusTiles = 8f } };
            var data = GeneratedItemData.Placeholder(); data.Id = "exact_item";
            GeneratedItemRegistryService.StampCurrentWorld(data);
            data.RuntimeProgram.Entities = new[] { entity };
            var generationHook = new RuntimeHitNpcGeneration();
            Terraria.Main.netMode = NetmodeID.Server;
            generationHook.OnSpawn(target, owner.GetSource_Misc("spawn"));
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            using (var wire = new MemoryStream())
            {
                generationHook.SendExtraAI(target, null!, new BinaryWriter(wire));
                var senderNpc = target;
                var clientNpc = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true,
                    position = senderNpc.position, width = 20, height = 20, knockBackResist = 1f };
                wire.Position = 0;
                generationHook.ReceiveExtraAI(clientNpc, null!, new BinaryReader(wire));
                using var replacedReceipt = new MemoryStream();
                var probe = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = 0, identity = 73, active = true };
                var probeGenerated = Attach(probe);
                typeof(Projectile).GetProperty("ModProjectile")!.SetValue(probe, probeGenerated);
                probeGenerated.Configure(data, entity, 0, 0, Vector2.UnitX);
                using (var writer = new BinaryWriter(replacedReceipt, System.Text.Encoding.UTF8, true))
                    Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, probe, clientNpc, false), "receipt identifies NPC generation");
                Terraria.Main.netMode = NetmodeID.Server;
                wire.Position = 0;
                generationHook.ReceiveExtraAI(senderNpc, null!, new BinaryReader(wire)); // independent server table in this process
                Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, position = senderNpc.position,
                    width = 20, height = 20, knockBackResist = 1f };
                generationHook.OnSpawn(Terraria.Main.npc[0], owner.GetSource_Misc("replacement"));
                replacedReceipt.Position = 0;
                using (var reader = new BinaryReader(replacedReceipt)) RuntimeHitPullBridge.HandlePacket(reader, 0);
                Equal(Vector2.Zero, Terraria.Main.npc[0].velocity, "pre-receive NPC replacement rejected");
                Terraria.Main.npc[0] = target;
                wire.Position = 0;
                generationHook.ReceiveExtraAI(target, null!, new BinaryReader(wire));
            }
            var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, identity = 72,
                owner = 0, active = true, type = ProjectileID.WoodenArrowFriendly };
            projectile.Center = target.Center;
            var generated = Attach(projectile);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
            generated.Configure(data, entity, 0, 0, Vector2.UnitX);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            using var stream = new MemoryStream();
            using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, false),
                    "only owner authored NPC pull writes a bounded receipt");
            Equal(Vector2.Zero, target.velocity, "owner doesn't mutate NPC velocity");
            // The receiver allocates its own local slot for the same owner+network identity.
            Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = 0, active = false };
            var receiver = Terraria.Main.projectile[1] = new Projectile { whoAmI = 1, identity = 72,
                owner = 0, active = true, type = ProjectileID.WoodenArrowFriendly };
            var receiverGenerated = Attach(receiver);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(receiver, receiverGenerated);
            receiverGenerated.Configure(data, entity, 0, 0, Vector2.UnitX);
            Terraria.Main.netMode = NetmodeID.Server;
            stream.Position = 0;
            using (var reader = new BinaryReader(stream, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(true, target.velocity.X < 0, "server resolves owner+identity across different local slots");
            Equal(true, target.netUpdate, "server syncs NPC velocity");
            var applied = target.velocity;
            stream.Position = 0;
            using (var duplicate = new BinaryReader(stream, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(duplicate, 0);
            Equal(applied, target.velocity, "duplicate receipt cannot reapply pull");
            stream.Position = 0;
            using (var wrongOwner = new BinaryReader(stream, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(wrongOwner, 1);
            Equal(applied, target.velocity, "different sender cannot claim owner projectile");
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            using var stale = new MemoryStream();
            using (var writer = new BinaryWriter(stale, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, false), "second receipt");
            Terraria.Main.netMode = NetmodeID.Server;
            receiver.identity++; // receiver slot reused for a different network generation
            stale.Position = 0;
            using (var reader = new BinaryReader(stale, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(applied, target.velocity, "stale identity cannot apply to reused receiver slot");
            byte[] malformed = stream.ToArray();
            malformed[malformed.Length - System.Text.Encoding.UTF8.GetByteCount(data.Id)
                - System.Text.Encoding.UTF8.GetByteCount(entity.Id) - 2] = 255; // first bounded identity length
            using (var reader = new BinaryReader(new MemoryStream(malformed)))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(applied, target.velocity, "oversize identity rejected before any action");
            receiver.identity--;
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            Terraria.Main.myPlayer = 1;
            using (var ignored = new BinaryWriter(new MemoryStream()))
                Equal(false, RuntimeHitPullBridge.TryWriteProjectileReceipt(ignored, projectile, target, false),
                    "remote peer does not send owner's hit");
            Terraria.Main.myPlayer = 0;
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            using (var ignored = new BinaryWriter(new MemoryStream()))
                Equal(false, RuntimeHitPullBridge.TryWriteProjectileReceipt(ignored, projectile, target, false),
                    "SP doesn't open a packet bridge");
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            var hitAction = entity.Events[0];
            entity.Events = new[] { new RuntimeEventActionSpec { Id = "crit_pull", Event = RuntimeEventKind.OnCrit,
                ActionCode = RuntimeEventActionCode.Pull, Mode = "target_to_owner", Strength = 2f } };
            using (var ignored = new BinaryWriter(new MemoryStream()))
                Equal(false, RuntimeHitPullBridge.TryWriteProjectileReceipt(ignored, projectile, target, false),
                    "crit-only pull does not run on ordinary hit");
            using (var writer = new BinaryWriter(new MemoryStream()))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, true),
                    "crit-only authored action is eligible");
            entity.Events = new[] { hitAction };
        }
        finally {
            RuntimeHitPullBridge.Clear(); RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = previousOwner; Terraria.Main.npc[0] = previousNpc;
            Terraria.Main.projectile[0] = previousProjectile;
            Terraria.Main.projectile[1] = previousReceiverProjectile;
            Terraria.Main.netMode = previousMode; Terraria.Main.myPlayer = previousLocal;
        }
    }

    private static void RetiredProjectileHitKeepsGeneration()
    {
        var oldOwner = Terraria.Main.player[0]; var oldNpc = Terraria.Main.npc[0];
        var oldProjectile = Terraria.Main.projectile[0]; var oldReceiver = Terraria.Main.projectile[1];
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        try
        {
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            owner.Center = Vector2.Zero;
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true,
                position = new Vector2(80, 0), width = 20, height = 20, knockBackResist = 1f };
            var entity = Entity(); entity.Id = "bolt"; entity.Kind = RuntimeEntityKind.FreeProjectile;
            Terraria.Main.netMode = NetmodeID.Server;
            new RuntimeHitNpcGeneration().OnSpawn(target, owner.GetSource_Misc("spawn"));
            entity.Events = new[] { new RuntimeEventActionSpec { Id = "pull", Event = RuntimeEventKind.OnHit,
                Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull, Mode = "target_to_owner",
                Strength = 2f, RadiusTiles = 8f } };
            var data = GeneratedItemData.Placeholder(); data.Id = "retired_item";
            GeneratedItemRegistryService.StampCurrentWorld(data);
            data.RuntimeProgram.Entities = new[] { entity };
            var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0,
                identity = 45, owner = 0, active = true, type = ProjectileID.WoodenArrowFriendly };
            var generated = Attach(projectile);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
            generated.Configure(data, entity, 0, 0, Vector2.UnitX);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            using var stream = new MemoryStream();
            using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, false), "terminal hit receipt");
            Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, active = false };
            var receiver = Terraria.Main.projectile[1] = new Projectile { whoAmI = 1,
                identity = 45, owner = 0, active = true, type = ProjectileID.WoodenArrowFriendly };
            var receiverGenerated = Attach(receiver);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(receiver, receiverGenerated);
            receiverGenerated.Configure(data, entity, 0, 0, Vector2.UnitX);
            Terraria.Main.netMode = NetmodeID.Server;
            RuntimeHitPullBridge.RememberRetired(receiver);
            receiver.active = false;
            stream.Position = 0;
            using (var reader = new BinaryReader(stream, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(true, target.velocity.X < 0, "same-generation terminal hit resolves different receiver slot");
            target.velocity = Vector2.Zero;
            // A freshly active projectile can eventually reuse the retired network identity.
            // With both generations resolvable, the receipt has no unambiguous source.
            var reused = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0,
                identity = 45, owner = 0, active = true, type = ProjectileID.WoodenArrowFriendly };
            var reusedGenerated = Attach(reused);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(reused, reusedGenerated);
            reusedGenerated.Configure(data, entity, 0, 0, Vector2.UnitX);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            using var ambiguous = new MemoryStream();
            using (var writer = new BinaryWriter(ambiguous, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, false), "old hit during identity reuse");
            Terraria.Main.netMode = NetmodeID.Server; ambiguous.Position = 0;
            using (var reader = new BinaryReader(ambiguous)) RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(Vector2.Zero, target.velocity, "retired/active identity ambiguity rejects claim");
            Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, active = false };
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            using var next = new MemoryStream();
            using (var writer = new BinaryWriter(next, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, false), "fresh terminal receipt");
            Terraria.Main.netMode = NetmodeID.Server;
            receiver.identity++;
            next.Position = 0;
            using (var reader = new BinaryReader(next, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(Vector2.Zero, target.velocity, "retired generation cannot be reused with another identity");
            receiver.identity--;
            Terraria.Main.projectile[1] = new Projectile { whoAmI = 1, owner = 0, identity = 45, active = false };
            next.Position = 0;
            using (var reader = new BinaryReader(next, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(Vector2.Zero, target.velocity, "replacement host cannot inherit retired generation");
        }
        finally {
            RuntimeHitPullBridge.Clear(); RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner; Terraria.Main.npc[0] = oldNpc;
            Terraria.Main.projectile[0] = oldProjectile; Terraria.Main.projectile[1] = oldReceiver;
            Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal;
        }
    }

    private static void DelayedHitNeverRetargetsReplacedNpc()
    {
        var previousOwner = Terraria.Main.player[0]; var previousNpc = Terraria.Main.npc[0];
        var previousOther = Terraria.Main.npc[1]; var previousProjectile = Terraria.Main.projectile[0];
        int previousMode = Terraria.Main.netMode, previousLocal = Terraria.Main.myPlayer;
        try
        {
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            owner.Center = Vector2.Zero;
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true,
                position = new Vector2(80, 0), width = 20, height = 20, knockBackResist = 1f };
            var other = Terraria.Main.npc[1] = new NPC { whoAmI = 1, active = true,
                position = new Vector2(100, 0), width = 20, height = 20, knockBackResist = 1f };
            var entity = Entity(); entity.Id = "bolt"; entity.Kind = RuntimeEntityKind.FreeProjectile;
            Terraria.Main.netMode = NetmodeID.Server;
            new RuntimeHitNpcGeneration().OnSpawn(target, owner.GetSource_Misc("spawn"));
            entity.Events = new[] { new RuntimeEventActionSpec { Id = "delayed_pull", Event = RuntimeEventKind.OnHit,
                Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull, Mode = "target_to_owner",
                Strength = 2f, RadiusTiles = 8f, DelayTicks = 2 } };
            var data = GeneratedItemData.Placeholder(); data.Id = "delay_item";
            GeneratedItemRegistryService.StampCurrentWorld(data);
            data.RuntimeProgram.Entities = new[] { entity };
            var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0,
                identity = 51, owner = 0, active = true, type = ProjectileID.WoodenArrowFriendly };
            var generated = Attach(projectile);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
            generated.Configure(data, entity, 0, 0, Vector2.UnitX);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            using var stream = new MemoryStream();
            using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, false), "delayed hit receipt");
            Terraria.Main.netMode = NetmodeID.Server; stream.Position = 0;
            using (var reader = new BinaryReader(stream, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(1, PendingActions(), "server queues exact authored delay");
            Equal(Vector2.Zero, target.velocity, "delayed pull waits");
            Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, position = target.position };
            RuntimeDelayedActionScheduler.Update(); RuntimeDelayedActionScheduler.Update();
            Equal(Vector2.Zero, other.velocity, "invalid direct target cannot become area pull");
            Equal(Vector2.Zero, Terraria.Main.npc[0].velocity, "reused NPC slot cannot inherit hit");
            Terraria.Main.npc[0] = target;
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            using var second = new MemoryStream();
            using (var writer = new BinaryWriter(second, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, false), "next authored hit");
            Terraria.Main.netMode = NetmodeID.Server; second.Position = 0;
            using (var reader = new BinaryReader(second, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            RuntimeDelayedActionScheduler.Update();
            Equal(Vector2.Zero, target.velocity, "delay still pending at tick one");
            RuntimeDelayedActionScheduler.Update();
            Equal(true, target.velocity.X < 0, "delayed server pull executes at tick two");
            Equal(true, target.netUpdate, "delayed NPC velocity is synced");
        }
        finally {
            RuntimeHitPullBridge.Clear(); RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = previousOwner; Terraria.Main.npc[0] = previousNpc;
            Terraria.Main.npc[1] = previousOther; Terraria.Main.projectile[0] = previousProjectile;
            Terraria.Main.netMode = previousMode; Terraria.Main.myPlayer = previousLocal;
        }
    }

    private static void ItemHitCannotSwitchAuthoredSource()
    {
        var oldOwner = Terraria.Main.player[0]; var oldNpc = Terraria.Main.npc[0];
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        try
        {
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            owner.Center = Vector2.Zero;
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true,
                position = new Vector2(80, 0), width = 20, height = 20, knockBackResist = 1f };
            var entity = new RuntimeEntitySpec { Id = "body", Kind = RuntimeEntityKind.ItemBody,
                Events = new[] { new RuntimeEventActionSpec { Id = "exact_pull", Event = RuntimeEventKind.OnHit,
                    Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                    Mode = "target_to_owner", Strength = 2f, RadiusTiles = 8f } } };
            Terraria.Main.netMode = NetmodeID.Server;
            new RuntimeHitNpcGeneration().OnSpawn(target, owner.GetSource_Misc("spawn"));
            var data = GeneratedItemData.Placeholder(); data.Id = "original";
            GeneratedItemRegistryService.StampCurrentWorld(data);
            data.RuntimeProgram.ItemEntityId = entity.Id;
            data.RuntimeProgram.Entities = new[] { entity };
            data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Input = RuntimeInputKind.PrimaryUse,
                UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true } } };
            var item = owner.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1 };
            var generated = new InfiniCrafterLocal.Content.Items.GeneratedItem();
            typeof(ModType<Item>).GetProperty("Entity")!.SetValue(generated, item);
            typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
            typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            using var stream = new MemoryStream();
            using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteItemReceipt(writer, owner, generated, target, false), "original item sends pull");
            using var wrongDefinition = new MemoryStream();
            using (var writer = new BinaryWriter(wrongDefinition, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteItemReceipt(writer, owner, generated, target, false), "second item hit");
            using var wrongMode = new MemoryStream();
            using (var writer = new BinaryWriter(wrongMode, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteItemReceipt(writer, owner, generated, target, false), "mode identity probe");
            wrongMode.GetBuffer()[13] = 2; // v3 hit-time input, original item has no alternate contact binding
            // The server has seen this exact selected item before the owner changes tools.
            Terraria.Main.netMode = NetmodeID.Server;
            RuntimeHitPullBridge.RememberItemActivation(owner);
            owner.selectedItem = 1;
            owner.altFunctionUse = 2;
            var replacementData = GeneratedItemData.Placeholder(); replacementData.Id = "different_held";
            GeneratedItemRegistryService.StampCurrentWorld(replacementData);
            replacementData.RuntimeProgram.ItemEntityId = entity.Id;
            replacementData.RuntimeProgram.Entities = new[] { entity };
            replacementData.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Input = RuntimeInputKind.AlternateUse,
                UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true } } };
            var replacementItem = owner.inventory[1] = new Item { type = ItemID.CopperShortsword, stack = 1 };
            var replacement = new InfiniCrafterLocal.Content.Items.GeneratedItem();
            typeof(ModType<Item>).GetProperty("Entity")!.SetValue(replacement, replacementItem);
            typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(replacement, replacementData);
            typeof(Item).GetProperty("ModItem")!.SetValue(replacementItem, replacement);
            RuntimeHitPullBridge.RememberItemActivation(owner);
            Terraria.Main.netMode = NetmodeID.Server; stream.Position = 0;
            using (var reader = new BinaryReader(stream, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(true, target.velocity.X < 0, "switched held item and use mode retain original contact hit");
            target.velocity = Vector2.Zero;
            data.Id = "different_item"; // wrong original authored identity, not the current held item
            wrongDefinition.Position = 0;
            using (var reader = new BinaryReader(wrongDefinition, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(Vector2.Zero, target.velocity, "old item hit cannot apply changed definition");
            data.Id = "original";
            wrongMode.Position = 0;
            using (var reader = new BinaryReader(wrongMode, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(Vector2.Zero, target.velocity, "current alternate contact cannot stand in for original primary binding");
            stream.Position = 0;
            using (var reader = new BinaryReader(stream, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(Vector2.Zero, target.velocity, "duplicate item hit cannot reapply pull");
            target.velocity = Vector2.Zero;
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            owner.selectedItem = 0; owner.altFunctionUse = 0;
            using var staleWorld = new MemoryStream();
            using (var writer = new BinaryWriter(staleWorld, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteItemReceipt(writer, owner, generated, target, false), "world receipt");
            data.RecipeMeta.WorldId = "not-this-world";
            Terraria.Main.netMode = NetmodeID.Server; staleWorld.Position = 0;
            using (var reader = new BinaryReader(staleWorld, System.Text.Encoding.UTF8, true))
                RuntimeHitPullBridge.HandlePacket(reader, 0);
            Equal(Vector2.Zero, target.velocity, "world-mismatched item definition cannot run pull");
        }
        finally {
            RuntimeHitPullBridge.Clear(); RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner; Terraria.Main.npc[0] = oldNpc;
            Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal;
        }
    }

    private static void OwnerReceiptFloodDoesNotStarveNextSender()
    {
        var old0 = Terraria.Main.player[0]; var old1 = Terraria.Main.player[1];
        var oldNpc = Terraria.Main.npc[0];
        var oldProj0 = Terraria.Main.projectile[0]; var oldProj1 = Terraria.Main.projectile[1];
        int mode = Terraria.Main.netMode, local = Terraria.Main.myPlayer;
        try
        {
            var owner0 = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            var owner1 = Terraria.Main.player[1] = new Player { whoAmI = 1, active = true };
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true,
                position = new Vector2(80, 0), width = 20, height = 20, knockBackResist = 1f };
            Terraria.Main.netMode = NetmodeID.Server;
            new RuntimeHitNpcGeneration().OnSpawn(target, owner0.GetSource_Misc("flood"));
            var entity = Entity(); entity.Id = "flood_bolt"; entity.Kind = RuntimeEntityKind.FreeProjectile;
            entity.Events = new[] { new RuntimeEventActionSpec { Id = "pull", Event = RuntimeEventKind.OnHit,
                ActionCode = RuntimeEventActionCode.Pull, Mode = "target_to_owner",
                Strength = 2f, RadiusTiles = 8f, DelayTicks = 600 } };
            var data = GeneratedItemData.Placeholder(); data.Id = "flood_item";
            GeneratedItemRegistryService.StampCurrentWorld(data);
            data.RuntimeProgram.Entities = new[] { entity };
            var p0 = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0,
                identity = 310, owner = 0, active = true, type = ProjectileID.WoodenArrowFriendly };
            var p1 = Terraria.Main.projectile[1] = new Projectile { whoAmI = 1,
                identity = 311, owner = 1, active = true, type = ProjectileID.WoodenArrowFriendly };
            foreach (var projectile in new[] { p0, p1 })
            {
                var generated = Attach(projectile);
                typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
                generated.Configure(data, entity, 0, 0, Vector2.UnitX);
            }
            for (int i = 0; i < 33; i++)
            {
                using var stream = new MemoryStream();
                Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
                using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                    Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, p0, target, false), "owner receipt");
                Terraria.Main.netMode = NetmodeID.Server; stream.Position = 0;
                using (var reader = new BinaryReader(stream)) RuntimeHitPullBridge.HandlePacket(reader, 0);
            }
            Equal(32, PendingActions(), "same-tick sequence flood stays bounded at receiver");
            using var next = new MemoryStream();
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
            using (var writer = new BinaryWriter(next, System.Text.Encoding.UTF8, true))
                Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, p1, target, false), "second owner receipt");
            Terraria.Main.netMode = NetmodeID.Server; next.Position = 0;
            using (var reader = new BinaryReader(next)) RuntimeHitPullBridge.HandlePacket(reader, 1);
            Equal(33, PendingActions(), "second owner accepted despite first owner flood");
        }
        finally {
            RuntimeHitPullBridge.Clear(); RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = old0; Terraria.Main.player[1] = old1;
            Terraria.Main.npc[0] = oldNpc; Terraria.Main.projectile[0] = oldProj0; Terraria.Main.projectile[1] = oldProj1;
            Terraria.Main.netMode = mode; Terraria.Main.myPlayer = local;
        }
    }

    private static void NpcHitGenerationSurvivesTransform()
    {
        var npcs = (NPC[])Terraria.Main.npc.Clone();
        var players = (Player[])Terraria.Main.player.Clone();
        int mode = Terraria.Main.netMode;
        bool goodWorld = Terraria.Main.getGoodWorld;
        var random = Terraria.Main.rand;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.getGoodWorld = false;
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(17);
            for (int i = 0; i < Terraria.Main.npc.Length; i++)
                Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
            for (int i = 0; i < Terraria.Main.player.Length; i++)
                Terraria.Main.player[i] = new Player { whoAmI = i, active = false };
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            int slot = NPC.NewNPC(owner.GetSource_Misc("transform"), 1600, 1600, NPCID.BlueSlime);
            NPC npc = Terraria.Main.npc[slot];
            new RuntimeHitNpcGeneration().OnSpawn(npc, owner.GetSource_Misc("generation"));
            uint generation = RuntimeHitNpcGeneration.Get(npc);
            Equal(true, generation != 0, "server issued NPC generation");
            npc.Transform(NPCID.Zombie);
            Equal(true, ReferenceEquals(npc, Terraria.Main.npc[slot]), "Transform retains target instance");
            Equal(generation, RuntimeHitNpcGeneration.Get(npc), "Transform retains synced generation");
        }
        finally {
            RuntimeHitPullBridge.Clear();
            Array.Copy(npcs, Terraria.Main.npc, npcs.Length);
            Array.Copy(players, Terraria.Main.player, players.Length);
            Terraria.Main.netMode = mode; Terraria.Main.getGoodWorld = goodWorld; Terraria.Main.rand = random;
        }
    }

    private static void PendingHitFloodKeepsOtherOwnerCapacity()
    {
        var old0 = Terraria.Main.player[0]; var old1 = Terraria.Main.player[1];
        try
        {
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            var other = Terraria.Main.player[1] = new Player { whoAmI = 1, active = true };
            var data = GeneratedItemData.Placeholder();
            var entity = Entity(); entity.Id = "body"; entity.Kind = RuntimeEntityKind.ItemBody;
            var action = new RuntimeEventActionSpec { Id = "bounded", Event = RuntimeEventKind.OnHit,
                ActionCode = RuntimeEventActionCode.Pull, Mode = "target_to_owner", DelayTicks = 600 };
            var sourceItem = new Item { type = ItemID.CopperShortsword, stack = 1 };
            var budget = new RuntimeSpawnBudget(0);
            for (int i = 0; i < 32; i++)
                Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner,
                    owner.GetSource_ItemUse(sourceItem), Vector2.Zero, Vector2.Zero, null, 0, 0, budget,
                    ownerHitReceipt: true),
                    "first owner has finite multi-hit allowance");
            Equal(false, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner,
                owner.GetSource_ItemUse(sourceItem), Vector2.Zero, Vector2.Zero, null, 0, 0, budget,
                ownerHitReceipt: true),
                "flood cannot consume all owners' pending capacity");
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, other,
                other.GetSource_ItemUse(sourceItem), Vector2.Zero, Vector2.Zero, null, 0, 0, budget,
                ownerHitReceipt: true),
                "second owner retains pending slot");
        }
        finally { RuntimeDelayedActionScheduler.Clear(); Terraria.Main.player[0] = old0; Terraria.Main.player[1] = old1; }
    }
}
