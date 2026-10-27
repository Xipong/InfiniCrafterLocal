using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Reflection;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;

internal static partial class EngineRuntimeChecks
{
    private static JsonObject MaterialElementWire(string attachment = "world")
    {
        JsonObject Profile(float a, float b, float c) => new() { ["start"] = a, ["middle"] = b, ["end"] = c, ["curve"] = "linear" };
        var data = GeneratedItemData.Placeholder();
        data.Visual.RenderSizePx=32; data.Visual.ForwardAngleDegrees=0;
        JsonObject wire = JsonNode.Parse(data.ToJson())!.AsObject();
        var slot = new VfxSlotSpec { Id = "element", EntityId = "unavailable_item", Event = "periodic",
            RendererKind = "spriteElement", RepeatEvery = 1, Duration = 12, Alpha = 1, Blend = "alpha", Layer = "BeforeProjectiles", StartTick = 0 };
        var row = JsonSerializer.SerializeToNode(slot, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!.AsObject();
        row["element"] = new JsonObject {
            ["texture"] = new JsonObject { ["source"] = "asset", ["assetId"] = "Shard_A" },
            ["attachment"] = attachment, ["count"] = 2,
            ["offsetForwardPx"] = 3, ["offsetSidePx"] = -2,
            ["speedMinPxPerTick"] = 1, ["speedMaxPxPerTick"] = 1, ["spreadRadians"] = 0,
            ["inheritVelocity"] = 0.5, ["drag"] = 1,
            ["accelerationXPxPerTickSquared"] = 0, ["accelerationYPxPerTickSquared"] = 0,
            ["rotationRadians"] = 0, ["rotationSpeedRadiansPerTick"] = 0,
            ["widthPx"] = 8, ["heightPx"] = 20,
            ["widthProfile"] = Profile(1,2,0), ["heightProfile"] = Profile(2,1,0),
            ["opacityProfile"] = Profile(1,0.5f,0),
            ["colorProfile"] = new JsonObject { ["start"] = RgbWire(255,255,255), ["middle"] = RgbWire(255,255,255), ["end"] = RgbWire(90,235,255), ["curve"] = "linear" }
        };
        wire["vfxManifest"]!["slots"] = new JsonArray(row);
        wire["vfxManifest"]!["assets"] = new JsonArray(new JsonObject { ["id"] = "Shard_A", ["prompt"] = "one isolated soft shard",
            ["negativePrompt"] = "text", ["canvasSize"] = 32, ["layout"] = "cutout",
            ["spritePath"] = "recipe_vfx_Shard_A.png", ["spriteUrl"] = "", ["spriteStatus"] = "generated", ["spriteTechnicalScore"] = 1 });
        return wire;
    }

    private static GeneratedItemData ParseMaterialElement(JsonObject wire)
    {
        var data = GeneratedItemData.FromJson(wire.ToJsonString());
        if (data is null) {
            ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson", out var error);
            throw new InvalidOperationException("accepted individual-material DTO was rejected: " + error?.Message);
        }
        return data;
    }

    private static void MaterialClock(ulong tick) => typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!.SetValue(null,(uint)tick);

    private static System.Collections.IList OwnedMaterialQueue()
        => (System.Collections.IList)(typeof(InfiniDetachedVfxSystem).GetField("MaterialEmissions", BindingFlags.Static | BindingFlags.NonPublic)?.GetValue(null)
            ?? throw new InvalidOperationException("individual material emission owner is missing"));

    private static void MaterialElementRuntimeMovesAndKeepsIndependentProfiles()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) => {
            var system = new InfiniDetachedVfxSystem(); var tick = Terraria.Main.GameUpdateCount;

            using var borrowedCache = new BorrowedSpriteCache();
            var cache = borrowedCache.Cache; var textures = borrowedCache.Textures; var record = borrowedCache.Record;
            string path = Path.Combine(Terraria.Program.SavePath, "material.png");
            textures.Add(path, Activator.CreateInstance(record, texture, 2f, 0L)!); // a PCA angle must not rotate authored axes
            try {
                system.OnWorldUnload();
                var data = ParseMaterialElement(MaterialElementWire());
                var slot = data.VfxManifest.Slots[0]; slot.Event = "on_hit"; slot.RepeatEvery = 0;
                data.VfxManifest.Assets![0].SpritePath = path;
                var source = new Projectile { Center = new Vector2(100,120), velocity = new Vector2(2,0), rotation = 0, scale = 1 };
                var snapshot = InfiniVfxProjectileSnapshot.Capture(source,data,slot.EntityId);
                InfiniVfxRuntime.OnDetachedEvent(data,slot.EntityId,slot.Event,data.VfxManifest,source.Center,source.velocity,"material",snapshot);
                var queue = OwnedMaterialQueue(); Equal(1,queue.Count,"event emission group admitted");
                var draw = typeof(InfiniDetachedVfxSystem).GetMethod("DrawMaterialSprites",BindingFlags.Static|BindingFlags.NonPublic)!;
                draw.Invoke(null,new object[]{ "BeforeProjectiles", batch, (Action)(()=>{}) });
                Equal(2,count(),"literal count reaches real FNA quad queue");
                AssertVfxNear(new Vector2(103,118)-Terraria.Main.screenPosition,VfxVertexCenter(positions(0)),"captured source-frame offset");
                var v=positions(0); Equal(true, Math.Abs(Vector3.Distance(v[0],v[1])-8)<0.001f,"independent X width in pixels");
                Equal(true,Math.Abs(Vector3.Distance(v[0],v[2])-40)<0.001f,"independent Y height in pixels");
                data.VfxManifest.Slots[0].Element!.WidthPx=128; data.VfxManifest.Slots[0].Element!.WidthProfile.Middle=0;
                source.Center=Vector2.Zero; source.velocity=Vector2.Zero;
                MaterialClock(tick+6); system.PostUpdateEverything();
                var reset=typeof(InfiniDetachedVfxSystem).GetMethod("BeginDrawBudgetFrame",BindingFlags.Static|BindingFlags.NonPublic)!;reset.Invoke(null,null);
                draw.Invoke(null,new object[]{ "BeforeProjectiles",batch,(Action)(()=>{}) });
                Equal(4,count(),"middle lifetime draw");
                AssertVfxNear(new Vector2(115,118)-Terraria.Main.screenPosition,VfxVertexCenter(positions(2)),"world motion uses captured initial velocity and no source lookup");
                v=positions(2); Equal(true,Math.Abs(Vector3.Distance(v[0],v[1])-16)<0.001f,"copied X middle knot");
                Equal(true,Math.Abs(Vector3.Distance(v[0],v[2])-20)<0.001f,"copied independent Y middle knot");
                int frozen=count(); draw.Invoke(null,new object[]{ "BeforeProjectiles",batch,(Action)(()=>{}) });
                AssertVfxNear(VfxVertexCenter(positions(2)),VfxVertexCenter(positions(frozen)),"Draw does not integrate motion");
                MaterialClock(tick+12);system.PostUpdateEverything();Equal(0,queue.Count,"client cleanup requires neither Draw nor new emission");
            } finally {textures.Clear();system.OnWorldUnload();MaterialClock(tick);}
        });
    }
    private static void MaterialElementLiveSourcePeriodicUsesFinalPoseAndGeneration()
    {
        using var actorState = new NativeActorState();
        WithLighting((config,_)=> {
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;

            try {
                system.OnWorldUnload(); config.ParticleSpawnMultiplier=1;
                Terraria.Main.player[0]=new Player{whoAmI=0,active=true};
                var data=ParseMaterialElement(MaterialElementWire("source"));
                var entity=Entity();entity.Id="probe";entity.Kind=RuntimeEntityKind.FreeProjectile;entity.LifetimeTicks=90;
                data.RuntimeProgram.Entities=new[]{entity};var slot=data.VfxManifest.Slots[0];slot.EntityId="probe";
                var source=Terraria.Main.projectile[0]=new Projectile{whoAmI=0,owner=0,active=true,identity=17,timeLeft=90,velocity=new Vector2(2,0)};
                var generated=Attach(source);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(source,generated);
                generated.Configure(data,entity,0,0,Vector2.UnitX);
                for(int i=0;i<3;i++)generated.AI();
                source.Center=new Vector2(100,120); // final engine position after actual AI/motion, never fabricated by presentation
                Equal(0,OwnedMaterialQueue().Count,"new periodic sampling is not before motion in AI");
                system.PostUpdateEverything();Equal(1,OwnedMaterialQueue().Count,"one world-tick periodic group despite extra hook visits");
                var emission=OwnedMaterialQueue()[0]!;var frameField=emission.GetType().GetField("Frame",BindingFlags.Instance|BindingFlags.NonPublic)!;
                var frame=(VfxSourceFrame)frameField.GetValue(emission)!;Equal(source.Center,frame.Position,"final live pose at client update");
                system.PostUpdateEverything();Equal(1,OwnedMaterialQueue().Count,"same world tick does not emit twice");
                MaterialClock(tick+1);source.Center=new Vector2(200,200);source.velocity=new Vector2(0,2);
                system.PostUpdateEverything();Equal(2,OwnedMaterialQueue().Count,"literal periodic overlap next world tick");
                frame=(VfxSourceFrame)frameField.GetValue(emission)!;Equal(Vector2.UnitY,frame.Forward,"attached frame follows actual source rotation");
                // Reconfigure the SAME host, slot, owner, type and identity: a new presentation generation must not inherit attachment.
                generated.Configure(data,entity,0,0,Vector2.UnitX);
                MaterialClock(tick+2);system.PostUpdateEverything();Equal(0,OwnedMaterialQueue().Count,"stale generation attachment retires without Draw");
            }finally{system.OnWorldUnload();MaterialClock(tick);}
        });
    }

    private static void MaterialElementDelayFreezesWorldButFencesSource()
    {
        using var actorState = new NativeActorState();
        WithLighting((_,__)=> {
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;
            try {
                system.OnWorldUnload();Terraria.Main.player[0]=new Player{whoAmI=0,active=true};
                var data=ParseMaterialElement(MaterialElementWire());var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.StartTick=3;slot.RepeatEvery=0;
                var entity=Entity();entity.Id="probe";data.RuntimeProgram.Entities=new[]{entity};slot.EntityId=entity.Id;
                var source=Terraria.Main.projectile[0]=new Projectile{whoAmI=0,owner=0,active=true,identity=17,timeLeft=90,Center=new Vector2(300,400),velocity=Vector2.UnitX};
                var generated=Attach(source);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(source,generated);generated.Configure(data,entity,0,0,Vector2.UnitX);
                generated.OnHitNPC(new NPC{active=true,Center=new Vector2(20,30)},new NPC.HitInfo(),1);
                Equal(1,OwnedMaterialQueue().Count,"world delayed event pending");
                var emission=OwnedMaterialQueue()[0]!;Equal(false,(bool)emission.GetType().GetField("Started",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(emission)!,"delay does not consume emission at capture");
                slot.Element!.WidthPx=99;source.Center=Vector2.Zero;source.active=false;Terraria.Main.projectile[0]=new Projectile{whoAmI=0,owner=0,active=true,identity=17};
                MaterialClock(tick+3);system.PostUpdateEverything();
                Equal(1,OwnedMaterialQueue().Count,"world delay survives source removal/reuse");
                var frame=(VfxSourceFrame)emission.GetType().GetField("Frame",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(emission)!;
                Equal(new Vector2(300,400),frame.Position,"immutable event-time self anchor");
                system.OnWorldUnload();MaterialClock(tick);Terraria.Main.projectile[0]=source;source.active=true;slot.Element.Attachment="source";
                generated.OnHitNPC(new NPC{active=true},new NPC.HitInfo(),1);Equal(1,OwnedMaterialQueue().Count,"live source delayed group pending");
                generated.Configure(data,entity,0,0,Vector2.UnitX);
                MaterialClock(tick+3);system.PostUpdateEverything();Equal(0,OwnedMaterialQueue().Count,"source delay requires exact live generation");
            }finally{system.OnWorldUnload();MaterialClock(tick);}
        });
    }

    private static void MaterialElementItemAttachmentUsesInstanceNotDefinition()
    {
        WithLighting((config,_)=> {
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;var prior=Terraria.Main.player[0];
            try {
                system.OnWorldUnload();var player=Terraria.Main.player[0]=new Player{whoAmI=0,active=true,selectedItem=0,Center=new Vector2(100,200),itemLocation=Vector2.Zero,itemRotation=0,direction=1};
                var data=ParseMaterialElement(MaterialElementWire("source"));
                InfiniCrafterLocal.Content.Items.GeneratedItem Host() {
                    var gi=new InfiniCrafterLocal.Content.Items.GeneratedItem();var item=new Item{type=1,stack=1};
                    AttachItem(gi, item, data);return gi;
                }
                var a=Host();var b=Host();player.inventory[0]=a.Item;
                a.HoldItem(player);system.PostUpdateEverything();Equal(1,OwnedMaterialQueue().Count,"real HoldItem emits attached element");
                player.inventory[0]=b.Item;MaterialClock(tick+1);system.PostUpdateEverything();
                Equal(0,OwnedMaterialQueue().Count,"equal-definition replacement does not inherit previous item attachment");
                b.HoldItem(player);MaterialClock(tick+2);system.PostUpdateEverything();Equal(1,OwnedMaterialQueue().Count,"replacement gets its own independent source lifecycle");
                // A world event remains independent of Item consumption and selection.
                data.VfxManifest.Slots[0].Element!.Attachment="world";data.VfxManifest.Slots[0].Event="on_hit";data.VfxManifest.Slots[0].RepeatEvery=0;
                InfiniItemVfxRuntime.EmitAndSyncEvent(player,data,"unavailable_item","on_hit",new Vector2(40,50));
                Equal(2,OwnedMaterialQueue().Count,"item event producer reaches material owner");
                player.inventory[0]=new Item();MaterialClock(tick+3);system.PostUpdateEverything();Equal(1,OwnedMaterialQueue().Count,"world item event survives original item disappearance");
            }finally{system.OnWorldUnload();Terraria.Main.player[0]=prior;MaterialClock(tick);}
        });
    }

    private static void MaterialItemPeriodicSurvivesEquipmentSlotTransitions()
    {
        WithLighting((config, _) => WithPlayer((player, modPlayer) => {
            var system = new InfiniDetachedVfxSystem(); var tick = Terraria.Main.GameUpdateCount;
            var prior = Terraria.Main.player[0];
            try {
                config.ParticleSpawnMultiplier = 1;
                foreach (string attachment in new[] { "world", "source" }) {
                    system.OnWorldUnload(); MaterialClock(105);
                    Terraria.Main.player[0] = player; player.whoAmI = 0; player.active = true; player.selectedItem = 0;
                    player.Center = new Vector2(100, 200); player.itemLocation = new Vector2(120, 200); player.direction = 1;
                    for (int i = 0; i < player.armor.Length; i++) player.armor[i] = new Item();
                    for (int i = 0; i < player.inventory.Length; i++) player.inventory[i] = new Item();
                    var data = ParseMaterialElement(MaterialElementWire(attachment));
                    data.Accessory.Enabled = true;
                    data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                        UsePolicy = new() { Action = new() { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId } } } };
                    var slot = data.VfxManifest.Slots[0]; slot.RepeatEvery = 7; slot.Element!.Count = 1;
                    var item = new Item { type = 1, stack = 1, accessory = true };
                    var generated = AttachItem(new InfiniCrafterLocal.Content.Items.GeneratedItem(), item, data);
                    var queue = OwnedMaterialQueue();
                    void Visit(bool held = false, bool vanity = false) {
                        // Actual producers can visit repeatedly in the same world tick.
                        for (int i = 0; i < 2; i++) {
                            if (held) generated.HoldItem(player);
                            else {
                                if (!vanity) generated.UpdateAccessory(player, false);
                                InfiniCrafterLocal.Common.Players.GeneratedEquipOverlayDrawLayerBase.EmitVisibleEquipmentVfx(player);
                            }
                        }
                        system.PostUpdateEverything();
                    }
                    int StartedAt(uint at) => queue.Cast<object>().Count(e =>
                        (ulong)e.GetType().GetField("Start", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(e)! == at);
                    void Due(uint at, bool held = false, bool vanity = false) {
                        MaterialClock(at); Visit(held, vanity);
                        Equal(1, StartedAt(at), attachment + ": moved instance emits exactly once at authored due tick " + at);
                        system.PostUpdateEverything();
                        Equal(1, StartedAt(at), attachment + ": repeated update keeps one emission");
                    }
                    player.armor[3] = item; Due(105);
                    // ItemSlot uses this native reference swap; it does not clone
                    // a new presentation generation when moving an item.
                    Utils.Swap(ref player.armor[3], ref player.armor[4]); Due(112);
                    Equal(attachment == "world" ? 2 : 1, queue.Count, attachment + ": swap preserves world overlap and retires old source attachment");
                    MaterialClock(113); Visit();
                    Equal(0, StartedAt(113), attachment + ": slot change does not reset world-clock cadence");
                    Utils.Swap(ref player.armor[4], ref player.armor[14]); Due(119, vanity: true);
                    Utils.Swap(ref player.armor[14], ref player.inventory[0]); Due(126, held: true);
                    Utils.Swap(ref player.inventory[0], ref player.inventory[1]); MaterialClock(133); system.PostUpdateEverything();
                    Equal(0, StartedAt(133), attachment + ": unequipped item has no periodic producer");
                    Equal(attachment == "world" ? 1 : 0, queue.Count, attachment + ": unequip preserves only authored world lifetime");
                    Utils.Swap(ref player.inventory[1], ref player.armor[3]); Due(140);
                    Equal(1, queue.Count, attachment + ": re-equip starts one current emission after old lifetimes expire");
                }
            }
            finally { system.OnWorldUnload(); Terraria.Main.player[0] = prior; MaterialClock(tick); }
        }));
    }

    private delegate Terraria.ModLoader.ModPacket VfxGetPacketOriginal(Terraria.ModLoader.Mod mod,int capacity);
    private delegate Terraria.ModLoader.ModPacket VfxGetPacketHook(VfxGetPacketOriginal orig,Terraria.ModLoader.Mod mod,int capacity);
    private static void MaterialOwnerHitReachesValidatedServerRelayAndRemote()
    {
        WithLighting((_,lights)=> {
            using var peers = new ReviewPeers();
            var system = peers.System; var mod = peers.Mod; var registry = peers.Registry; var outgoing = peers.Sent;
            var tick = Terraria.Main.GameUpdateCount;
            InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ClearVfxEventSyncCaches();
            Terraria.Main.netMode = Terraria.ID.NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            var data=ParseMaterialElement(MaterialElementWire());data.Id="network_material";InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
            var entity=Entity();entity.Id="probe";data.RuntimeProgram.Entities=new[]{entity};
            var slot=data.VfxManifest.Slots[0];slot.EntityId="probe";slot.Event="on_hit";slot.RepeatEvery=0;slot.StartTick=2;
            var crit=new VfxSlotSpec{Id="crit",EntityId="probe",Event="on_crit",RendererKind="spriteElement",Element=slot.Element,Duration=12,Alpha=1, Blend = "alpha", Layer = "BeforeProjectiles", RepeatEvery = 0, StartTick = 0 };
            var simpleHit=LightManifest("probe", RuntimeEventKind.OnHit).Slots[0]; simpleHit.Anchor="hitPoint";
            data.VfxManifest.Slots=new[]{slot,crit,simpleHit};
            ((System.Collections.IDictionary)registry.GetType().GetField("_byId",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(registry)!).Add(data.Id,data);
            Terraria.Main.projectile=new Projectile[16];for(int i=0;i<16;i++)Terraria.Main.projectile[i]=new Projectile{whoAmI=i};
            var source=Terraria.Main.projectile[3]=new Projectile{whoAmI=3,owner=0,identity=71,active=true,Center=new Vector2(200,300),velocity=Vector2.UnitX,timeLeft=90};
            var generated=Attach(source);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(source,generated);generated.Configure(data,entity,0,0,Vector2.UnitX);
            generated.OnHitNPC(new NPC{active=true,Center=new Vector2(10,20)},new NPC.HitInfo{Crit=true},1);
            Equal(2,outgoing.Count,"actual owner-client OnHitNPC sends independent hit+crit packets even without NPC-pull gameplay");
            source.extraUpdates=2;
            generated.OnHitNPC(new NPC{active=true,Center=new Vector2(30,40)},new NPC.HitInfo(),1);
            Equal(3,outgoing.Count,"second real same-name hit in same world tick is a new producer occurrence");
            var claims=outgoing.ToArray();outgoing.Clear();
            using var extra=new MemoryStream();generated.SendExtraAI(new BinaryWriter(extra));
            system.OnWorldUnload();Terraria.Main.netMode=Terraria.ID.NetmodeID.Server;Terraria.Main.myPlayer=255;
            source.active=false;
            var serverHost=Terraria.Main.projectile[11]=new Projectile{whoAmI=11,owner=0,identity=71,active=true,Center=new Vector2(999,999),timeLeft=90};
            var server=Attach(serverHost);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(serverHost,server);extra.Position=0;server.ReceiveExtraAI(new BinaryReader(extra));
            foreach(var bytes in claims)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),0);
            Equal(3,outgoing.Count,"validated server relay resolves owner+identity across different local slots");
            foreach(var bytes in claims)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),0);Equal(3,outgoing.Count,"same technical occurrence replay suppressed");
            foreach(var bytes in claims)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),1);Equal(3,outgoing.Count,"wrong sender cannot relay owner claim");
            var relays=outgoing.ToArray();outgoing.Clear();serverHost.active=false;Terraria.Main.projectile=Array.Empty<Projectile>();
            Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=2; lights.Clear();
            foreach(var bytes in relays)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),256);
            Equal(2,lights.Count,"remote receives both simple projectile hit effects without a surviving source");
            Equal(3,OwnedMaterialQueue().Count,"remote has all distinct delayed world emissions without surviving source");
            MaterialClock(tick+2);system.PostUpdateEverything();Equal(3,OwnedMaterialQueue().Count,"remote emission uses captured world pose at due tick");
            foreach(var bytes in relays)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),256);Equal(3,OwnedMaterialQueue().Count,"remote same occurrence replay suppressed");
            Equal(2,lights.Count,"remote same occurrence replay suppresses simple effects too");
            Vector2 EmittedVelocity(object emission) {var parts=(Array)emission.GetType().GetField("Particles",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(emission)!;var part=parts.GetValue(0)!;return (Vector2)part.GetType().GetField("Velocity",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(part)!;}
            AssertVfxNear(new Vector2(1+0.5f,0),EmittedVelocity(OwnedMaterialQueue()[0]!),"real owner/server/remote delayed chain inherits MaxUpdates=1");
            AssertVfxNear(new Vector2(1+3*0.5f,0),EmittedVelocity(OwnedMaterialQueue()[2]!),"real owner/server/remote delayed chain copies MaxUpdates=3 before source removal");
            // Reuse the real owner->server->remote chain with exact live attachment.
            data.VfxManifest.Slots=new[]{slot,crit};
            system.OnWorldUnload();MaterialClock(tick);outgoing.Clear();Terraria.Main.projectile=new Projectile[16];for(int i=0;i<16;i++)Terraria.Main.projectile[i]=new Projectile{whoAmI=i};
            Terraria.Main.projectile[3]=source;source.active=true;source.Center=new Vector2(200,300);slot.Element!.Attachment="source";
            generated.Configure(data,entity,0,0,Vector2.UnitX);source.extraUpdates=2;slot.Element.Count=1;slot.Element.SpeedMinPxPerTick=slot.Element.SpeedMaxPxPerTick=0;slot.Element.InheritVelocity=1;slot.Element.Drag=1;slot.Element.AccelerationXPxPerTickSquared=slot.Element.AccelerationYPxPerTickSquared=0;
            Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=0;
            generated.OnHitNPC(new NPC{active=true,Center=new Vector2(40,50)},new NPC.HitInfo(),1);Equal(1,outgoing.Count,"live source hit producer packet");
            var attachedClaim=outgoing[0];outgoing.Clear();using var attachedExtra=new MemoryStream();generated.SendExtraAI(new BinaryWriter(attachedExtra));source.active=false;
            Terraria.Main.projectile[11]=serverHost;serverHost.active=true;attachedExtra.Position=0;server.ReceiveExtraAI(new BinaryReader(attachedExtra));
            Terraria.Main.netMode=Terraria.ID.NetmodeID.Server;Terraria.Main.myPlayer=255;mod.HandlePacket(new BinaryReader(new MemoryStream(attachedClaim)),0);
            Equal(1,outgoing.Count,"server validates exact source generation before attached relay");var attachedRelay=outgoing[0];outgoing.Clear();serverHost.active=false;
            system.OnWorldUnload();var remoteHost=Terraria.Main.projectile[5]=new Projectile{whoAmI=5,owner=0,identity=71,active=true,Center=new Vector2(400,500),velocity=Vector2.UnitY,timeLeft=90};
            var remote=Attach(remoteHost);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(remoteHost,remote);attachedExtra.Position=0;remote.ReceiveExtraAI(new BinaryReader(attachedExtra));
            Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=2;mod.HandlePacket(new BinaryReader(new MemoryStream(attachedRelay)),256);
            Equal(1,OwnedMaterialQueue().Count,"remote source delay retains exact peer binding");MaterialClock(tick+2);system.PostUpdateEverything();
            var attachedEmission=OwnedMaterialQueue()[0]!;var attachedFrame=(VfxSourceFrame)attachedEmission.GetType().GetField("Frame",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(attachedEmission)!;
            Equal(remoteHost.Center,attachedFrame.Position,"attached source moves from live peer rather than event center");
            Equal(1,((Array)attachedEmission.GetType().GetField("Particles",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(attachedEmission)!).Length,"same live peer generation permits delayed source emission");
            AssertVfxNear(new Vector2(3,0),EmittedVelocity(attachedEmission),"attached relay's initial local inheritance uses copied MaxUpdates=3 despite differently updated remote host");
            remote.Configure(data,entity,0,0,Vector2.UnitX);MaterialClock(tick+3);system.PostUpdateEverything();Equal(0,OwnedMaterialQueue().Count,"reconfigured same peer host cannot inherit an old binding");
            Console.WriteLine("DETAIL: projectile relay real same-tick hits=2 hit/crit packets=3 live-attachment-chain=1");

        });
    }

    private static void MaterialItemSnapshotRelayPreservesPoseAndInstance()
    {
        WithLighting((_,__)=> {
            using var peers = new ReviewPeers();
            var system = peers.System; var mod = peers.Mod; var registry = peers.Registry; var outgoing = peers.Sent;
            var tick = Terraria.Main.GameUpdateCount;
            InfiniItemVfxRuntime.ClearUseEventCaches();
            var data=ParseMaterialElement(MaterialElementWire());data.Id="item_material_net";InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
            var entity=data.RuntimeProgram.Entities[0];var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;slot.StartTick=2;
            data.RuntimeProgram.Bindings=new[]{new RuntimeBindingSpec{Id="primary",Role=RuntimeEntityRole.Primary,Input=RuntimeInputKind.PrimaryUse,UsePolicy=new RuntimeBindingUsePolicySpec{ContactDamage=true,Action=new RuntimeBindingActionSpec{Kind=RuntimeBindingAction.UseItemBody,TargetId=entity.Id}}}};
            ((System.Collections.IDictionary)registry.GetType().GetField("_byId",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(registry)!).Add(data.Id,data);
            InfiniCrafterLocal.Content.Items.GeneratedItem Host() {var gi=new InfiniCrafterLocal.Content.Items.GeneratedItem();var item=new Item{type=1,stack=1};AttachItem(gi, item, data);return gi;}
            var player=Terraria.Main.player[0]=new Player{active=true,whoAmI=0,selectedItem=0,Center=new Vector2(300,400),itemRotation=1.1f,direction=-1,velocity=new Vector2(2,3),itemLocation=new Vector2(320,410)};
            var owner=Host();player.inventory[0]=owner.Item;Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=0;
            owner.OnHitNPC(player,new NPC{active=true,Center=new Vector2(10,20)},new NPC.HitInfo(),1);Equal(1,outgoing.Count,"real owner item-contact producer sends snapshot");
            Equal((byte)5,outgoing[0][1],"material item event uses immutable v5 ordered snapshot, not v3 live-player reconstruction");
            var claim=outgoing[0];outgoing.Clear();data.RuntimeProgram.ItemUse.Configured=true;data.RuntimeProgram.ItemUse.DisableMeleeHitbox=false;data.Normalize();using var wire=new MemoryStream();owner.NetSend(new BinaryWriter(wire));
            var server=Host();wire.Position=0;server.NetReceive(new BinaryReader(wire));player.inventory[0]=server.Item;
            Equal(data.Id,server.Data.Id,"server item hydration identity; diagnostics="+(ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson",out var diag)?diag?.Message:"none"));
            Equal(owner.PresentationToken,server.PresentationToken,"item peer technical generation round trip");
            system.OnWorldUnload();Terraria.Main.netMode=Terraria.ID.NetmodeID.Server;Terraria.Main.myPlayer=255;
            mod.HandlePacket(new BinaryReader(new MemoryStream(claim)),0);Equal(1,outgoing.Count,"server validates exact synchronized item generation");
            var relay=outgoing[0];mod.HandlePacket(new BinaryReader(new MemoryStream(claim)),0);Equal(1,outgoing.Count,"item occurrence replay does not relay twice");
            var remote=Host();wire.Position=0;remote.NetReceive(new BinaryReader(wire));player.inventory[0]=remote.Item;player.Center=new Vector2(999,999);player.itemRotation=-2;player.velocity=Vector2.Zero;
            Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=2;
            mod.HandlePacket(new BinaryReader(new MemoryStream(relay)),256);Equal(1,OwnedMaterialQueue().Count,"remote item world element admitted");
            var emission=OwnedMaterialQueue()[0]!;var frame=(VfxSourceFrame)emission.GetType().GetField("Frame",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(emission)!;
            Equal(new Vector2(300,400),frame.Position,"remote world position frozen at original hit");Equal(new Vector2(2,3),frame.Velocity,"remote inherited velocity frozen");
            AssertVfxNear(1.1f.ToRotationVector2()*-1,frame.Forward,"remote facing frozen before source mutation");
            player.inventory[0]=Host().Item;MaterialClock(tick+2);system.PostUpdateEverything();Equal(1,OwnedMaterialQueue().Count,"world item delay survives same-definition replacement");
            system.OnWorldUnload();MaterialClock(tick);outgoing.Clear();slot.Element!.Attachment="source";slot.Anchor="hitPoint";
            player.inventory[0]=owner.Item;player.Center=new Vector2(300,400);player.itemRotation=0;player.direction=1;player.velocity=Vector2.UnitX;
            Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=0;
            owner.OnHitNPC(player,new NPC{active=true,Center=new Vector2(40,50)},new NPC.HitInfo(),1);owner.OnHitNPC(player,new NPC{active=true,Center=new Vector2(60,70)},new NPC.HitInfo(),1);
            Equal(2,outgoing.Count,"two real same-name item hits in one tick send two occurrences");var attachedClaims=outgoing.ToArray();outgoing.Clear();
            player.inventory[0]=server.Item;Terraria.Main.netMode=Terraria.ID.NetmodeID.Server;Terraria.Main.myPlayer=255;
            foreach(var bytes in attachedClaims)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),0);
            Equal(2,outgoing.Count,"server relays both distinct item occurrences");var attachedRelays=outgoing.ToArray();outgoing.Clear();
            foreach(var bytes in attachedClaims)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),1);Equal(0,outgoing.Count,"wrong sender cannot claim item material event");
            system.OnWorldUnload();player.inventory[0]=remote.Item;player.Center=new Vector2(999,999);player.itemRotation=1;
            Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=2;
            foreach(var bytes in attachedRelays)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),256);
            Equal(2,OwnedMaterialQueue().Count,"remote attached item events retain exact net-synchronized instance");MaterialClock(tick+2);system.PostUpdateEverything();
            var attachedEmission=OwnedMaterialQueue()[0]!;var particles=(Array)attachedEmission.GetType().GetField("Particles",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(attachedEmission)!;
            Equal(new Vector2(-257,-352),(Vector2)particles.GetValue(0)!.GetType().GetField("Position",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(particles.GetValue(0))!,"remote source hit offset uses immutable item source center and forward");
            player.inventory[0]=Host().Item;MaterialClock(tick+3);system.PostUpdateEverything();Equal(0,OwnedMaterialQueue().Count,"same-definition remote item replacement retires attached emissions");
            system.OnWorldUnload();foreach(var bytes in attachedRelays)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),256);
            Equal(0,OwnedMaterialQueue().Count,"stale synchronized Item token cannot bind a replacement or convert to world");
            Console.WriteLine("DETAIL: item relay immutable-world=1 real same-tick hits=2 live-attachment-chain=1 stale-token-rejected=1");

            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
    }

    private static void MaterialBudgetsShareLegacyActiveAndDetachedCosts()
    {
        WithLighting((config,_)=> {
            var system=new InfiniDetachedVfxSystem();try {
                system.OnWorldUnload();config.DrawBudgetMultiplier=1;
                var data=ParseMaterialElement(MaterialElementWire());data.VfxManifest.Budget.MaxDrawCalls=2;data.VfxManifest.Budget.MaxParticlesPerTick=2;
                var state=new InfiniVfxState{SourceKey="mixed",LastGameUpdate=Terraria.Main.GameUpdateCount};
                var active=typeof(InfiniVfxRuntime).GetMethod("SpendDraw",BindingFlags.Static|BindingFlags.NonPublic)!;
                object[] args={data.VfxManifest,state,1};Equal(true,(bool)active.Invoke(null,args)!,"active cost one");
                InfiniDetachedVfxSystem.Enqueue("mixed","one.png","AfterProjectiles",Vector2.Zero,0,1,1,Color.White,10,2);
                var oldQueue=(System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
                var detached=typeof(InfiniDetachedVfxSystem).GetMethod("SpendDraw",BindingFlags.Static|BindingFlags.NonPublic)!;
                Equal(true,(bool)detached.Invoke(null,new[]{oldQueue[0]})!,"detached shares second source cost");
                Equal(false,(bool)detached.Invoke(null,new[]{oldQueue[0]})!,"active+detached cannot each claim independent full cap");
                var particle=typeof(InfiniVfxRuntime).GetMethod("SpendParticle",BindingFlags.Static|BindingFlags.NonPublic)!;
                args=new object[]{data.VfxManifest,state};Equal(true,(bool)particle.Invoke(null,args)!,"active particle reserves one");
                Equal(true,InfiniDetachedVfxSystem.TrySpendDetachedParticle("mixed",2,1000),"detached shares remaining tick particle");
                Equal(false,InfiniDetachedVfxSystem.TrySpendDetachedParticle("mixed",2,1000),"mixed particle lanes share tick cap");
            }finally{system.OnWorldUnload();}
        });
    }

    private static void MaterialOccurrencesKeepTwoRealHitsButRejectSameOccurrence()
    {
        WithLighting((_,__)=>{
            var system=new InfiniDetachedVfxSystem();try{
                system.OnWorldUnload();var data=ParseMaterialElement(MaterialElementWire());var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;slot.Anchor="hitPoint";
                var source=new Projectile{Center=Vector2.Zero,velocity=Vector2.UnitX,scale=1};var snap=InfiniVfxProjectileSnapshot.Capture(source,data,slot.EntityId);
                InfiniVfxRuntime.OnDetachedEvent(data,slot.EntityId,slot.Event,data.VfxManifest,new Vector2(10,20),source.velocity,"occ",snap,null,71);
                InfiniVfxRuntime.OnDetachedEvent(data,slot.EntityId,slot.Event,data.VfxManifest,new Vector2(30,40),source.velocity,"occ",snap,null,72);
                Equal(2,OwnedMaterialQueue().Count,"two genuine same-name hits in one tick remain independent");
                InfiniVfxRuntime.OnDetachedEvent(data,slot.EntityId,slot.Event,data.VfxManifest,new Vector2(10,20),source.velocity,"occ",snap,null,71);
                Equal(2,OwnedMaterialQueue().Count,"identical producer occurrence is not a third emission");
            }finally{system.OnWorldUnload();}
        });
    }

}
