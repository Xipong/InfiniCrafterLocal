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
        JsonObject wire = JsonNode.Parse(data.ToJson())!.AsObject();
        var slot = new VfxSlotSpec { Id = "element", EntityId = "unavailable_item", Event = "periodic",
            RendererKind = "spriteElement", Backend = "Sprite", TextureRole = "none", ParticleRole = "none",
            ParticleSystemId = "none", Scale = 1, RepeatEvery = 1, Duration = 12, Alpha = 1,
            Density = 0, Spread = 0, Jitter = 0, FadeIn = 0, FadeOut = 0, BudgetWeight = 1 };
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
            ["colorProfile"] = new JsonObject { ["start"] = "white", ["middle"] = "effect", ["end"] = "cyan", ["curve"] = "linear" }
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
            var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            var oldCache = sprites.GetValue(null);
            using var cache = new InfiniCrafterLocal.Common.Services.RuntimeSpriteCache();
            var textures = (System.Collections.IDictionary)cache.GetType().GetField("_textures", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(cache)!;
            var record = cache.GetType().GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string path = Path.Combine(Terraria.Program.SavePath, "material.png");
            textures.Add(path, Activator.CreateInstance(record, texture, 2f, 0L)!); // a PCA angle must not rotate authored axes
            try {
                system.OnWorldUnload(); sprites.SetValue(null, cache);
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
            } finally {textures.Clear();sprites.SetValue(null,oldCache);system.OnWorldUnload();MaterialClock(tick);}
        });
    }

    private static void MaterialElementLiveSourcePeriodicUsesFinalPoseAndGeneration()
    {
        WithLighting((config,_)=> {
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;
            var old=Terraria.Main.projectile[0]; var oldOwner=Terraria.Main.player[0];
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
            }finally{system.OnWorldUnload();Terraria.Main.projectile[0]=old;Terraria.Main.player[0]=oldOwner;MaterialClock(tick);}
        });
    }

    private static void MaterialElementDelayFreezesWorldButFencesSource()
    {
        WithLighting((_,__)=> {
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;var old=Terraria.Main.projectile[0];var oldOwner=Terraria.Main.player[0];
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
            }finally{system.OnWorldUnload();Terraria.Main.projectile[0]=old;Terraria.Main.player[0]=oldOwner;MaterialClock(tick);}
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
                    typeof(Terraria.ModLoader.ModType<Item>).GetProperty("Entity")!.SetValue(gi,item);typeof(Item).GetProperty("ModItem")!.SetValue(item,gi);
                    typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(gi,data);return gi;
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

    private static VfxTexturedPathSpec MaterialPathSpec(string source="beam") => new() {
        Texture=new VfxTextureSpec{Source="asset",AssetId="Shard_A"},Source=source,
        HistoryTicks=source=="anchorHistory"?8:0,MinDistancePx=0,MaxSegmentLengthPx=4096,WidthPx=8,
        WidthProfile=new VfxNumericProfileSpec{Start=0,Middle=2,End=0,Curve="linear"},
        OpacityProfile=new VfxNumericProfileSpec{Start=1,Middle=1,End=1,Curve="linear"},
        ColorProfile=new VfxColorProfileSpec{Start="white",Middle="effect",End="cyan",Curve="linear"},
        ProfileDomain=source=="anchorHistory"?"age":"length",UvMode="repeat",RepeatLengthPx=16,ScrollPxPerTick=2
    };
    private static VertexPositionColorTexture[] MaterialMesh(Vector2[] points,float[] ages,VfxTexturedPathSpec path,ulong tick,Func<bool> spend)
    {
        var method=typeof(InfiniDetachedVfxSystem).GetMethod("MaterialPathVertices",BindingFlags.Static|BindingFlags.NonPublic)
            ??throw new InvalidOperationException("textured path material vertex consumer missing");
        return (VertexPositionColorTexture[])method.Invoke(null,new object[]{points,ages,path,Color.Red,1f,"alpha",tick,spend})!;
    }
    private static void MaterialPathUsesActualBeamAndWhipAndUvDistance()
    {
        WithPlayer((owner,_)=> {
            var prior=Terraria.Main.player[0];
            try {
                owner.active=true;owner.whoAmI=0;owner.position=new Vector2(300,300);Terraria.Main.player[0]=owner;
                var entity=Entity();entity.Id="beam";entity.Controller.Code=RuntimeControllerCode.ChannelBeam;entity.Controller.Params.RangeTiles=20;entity.Controller.Params.WidthPx=12;
                var projectile=new Projectile{owner=0,velocity=Vector2.UnitX,scale=3,gfxOffY=17};var generated=Attach(projectile);
                generated.Configure(new GeneratedItemData(),entity,0,0,Vector2.UnitX);
                Equal(true,generated.TryCapturePresentationGeometry("beam",out var beam),"read-only supplier reaches canonical beam");
                var path=MaterialPathSpec();int costs=0;
                var mesh=MaterialMesh(beam,Array.Empty<float>(),path,10,()=>{costs++;return true;});
                Equal(12,mesh.Length,"beam inserts actual linear midpoint for independent middle profile");Equal(2,costs,"one charge per submitted segment");
                AssertVfxNear(owner.MountedCenter+Vector2.UnitX*18, new Vector2(mesh[0].Position.X,mesh[0].Position.Y),"beam start preserved with zero endpoint width");
                AssertVfxNear(beam[1],new Vector2(mesh[^1].Position.X,mesh[^1].Position.Y),"beam end exact despite body scale/gfx offset");
                Equal(true,Math.Abs(mesh[2].TextureCoordinate.X-mesh[0].TextureCoordinate.X-10)<0.001,"U uses cumulative beam distance, not fixed section mask");
                Equal(true,generated.Colliding(default,BodyTarget(beam[1]))==true,"real beam collision includes material endpoint");
                path.MaxSegmentLengthPx=200;
                Equal(0,MaterialMesh(beam,Array.Empty<float>(),path,10,()=>true).Length,"profile midpoint cannot bridge a true original geometry gap");
                entity.Kind=RuntimeEntityKind.OwnerAttachedProjectile;entity.Controller.Code=0;entity.Movement.Name="move_whip_lash";entity.Movement.Code=18;
                entity.Movement.Params.Segments=64;entity.Movement.Params.RangeTiles=12;owner.itemAnimationMax=20;owner.itemAnimation=10;
                generated.Configure(new GeneratedItemData(),entity,0,0,Vector2.UnitX);generated.AI();
                Equal(true,generated.TryCapturePresentationGeometry("whip",out var whip),"read-only real AI whip supplier");Equal(65,whip.Length,"all installed whip corners preserved");
                path=MaterialPathSpec("whip");path.WidthProfile.Start=path.WidthProfile.Middle=path.WidthProfile.End=0; // then explicit constant zero is silence
                Equal(0,MaterialMesh(whip,Array.Empty<float>(),path,10,()=>true).Length,"zero decorative width does not fabricate a collision-width replacement");
                path.WidthProfile.Middle=1;var whipMesh=MaterialMesh(whip,Array.Empty<float>(),path,10,()=>true);
                Equal(true,whipMesh.Length<=65*6,"66 section bound with exact corners");
                var canonical=(System.Collections.Generic.List<Vector2>)typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetField("_whipPoints",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(generated)!;
                Equal(true,whip.SequenceEqual(canonical),"every real collision corner copied, no decimation");
                foreach(var point in whip) {
                    var target=BodyTarget(point);bool expected=false;
                    for(int i=1;i<whip.Length;i++){float collisionPoint=0;expected|=Collision.CheckAABBvLineCollision(target.TopLeft(),target.Size(),whip[i-1],whip[i],Math.Max(4,entity.Hitbox.WidthPx*entity.Hitbox.HitboxScale*0.5f),ref collisionPoint);}
                    Equal(expected,generated.Colliding(default,target)==true,"read-only supplier preserves exact installed collision result at "+point);
                }
                Equal(false,generated.TryCapturePresentationGeometry("beam",out var noBeam),"foreign source never falls back to a fake short beam");
                var reversal=new[]{Vector2.Zero,new Vector2(16,0),Vector2.Zero,new Vector2(1000,0),new Vector2(1016,0)};
                path=MaterialPathSpec("anchorHistory");path.MaxSegmentLengthPx=20;path.WidthProfile.Start=path.WidthProfile.Middle=path.WidthProfile.End=1;
                costs=0;var trail=MaterialMesh(reversal,new[]{0f,0.2f,0.4f,0.6f,0.8f},path,0,()=>++costs<=2);
                Equal(12,trail.Length,"budget stops after two actual reversal segments without bridging teleport");
                foreach(var vertex in trail)Equal(true,float.IsFinite(vertex.Position.X)&&float.IsFinite(vertex.Position.Y),"reversal miter remains finite");
            }finally{Terraria.Main.player[0]=prior;}
        });
    }

    private delegate Terraria.ModLoader.ModPacket VfxGetPacketOriginal(Terraria.ModLoader.Mod mod,int capacity);
    private delegate Terraria.ModLoader.ModPacket VfxGetPacketHook(VfxGetPacketOriginal orig,Terraria.ModLoader.Mod mod,int capacity);
    private static void MaterialOwnerHitReachesValidatedServerRelayAndRemote()
    {
        WithLighting((_,__)=> {
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;
            var modProperty=typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Instance")!;var oldMod=modProperty.GetValue(null);
            var registryProperty=typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;var oldRegistry=registryProperty.GetValue(null);
            var oldProjectiles=Terraria.Main.projectile;var oldOwner=Terraria.Main.player[0];var oldMode=Terraria.Main.netMode;var oldLocal=Terraria.Main.myPlayer;
            using var registry=new InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService();
            var outgoing=new System.Collections.Generic.List<byte[]>();var starts=new System.Collections.Generic.Dictionary<Terraria.ModLoader.ModPacket,int>();
            var mod=new global::InfiniCrafterLocal.InfiniCrafterLocalMod();
            var netMods=typeof(Terraria.ModLoader.Mod).Assembly.GetType("Terraria.ModLoader.ModNet")!.GetField("netMods",BindingFlags.Static|BindingFlags.NonPublic)!;
            var priorNetMods=netMods.GetValue(null);netMods.SetValue(null,new Terraria.ModLoader.Mod[]{mod});
            typeof(Terraria.ModLoader.Mod).GetField("netID",BindingFlags.Instance|BindingFlags.NonPublic)!.SetValue(mod,(short)0);
            VfxGetPacketHook packetHook=(orig,self,capacity)=>{var p=orig(self,capacity);starts[p]=(int)p.BaseStream.Position;return p;};
            Action<Terraria.ModLoader.ModPacket,int,int> send=(p,to,ignore)=>{outgoing.Add(((MemoryStream)p.BaseStream).ToArray()[starts[p]..]);};
            using var getHook=new MonoMod.RuntimeDetour.Hook(typeof(Terraria.ModLoader.Mod).GetMethod("GetPacket")!,packetHook);
            using var sendHook=new MonoMod.RuntimeDetour.Hook(typeof(Terraria.ModLoader.ModPacket).GetMethod("Send")!,send);
            try {
                system.OnWorldUnload();InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ClearVfxEventSyncCaches();modProperty.SetValue(null,mod);registryProperty.SetValue(null,registry);
                Terraria.Main.player[0]=new Player{whoAmI=0,active=true};Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=0;
                var data=ParseMaterialElement(MaterialElementWire());data.Id="network_material";InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
                var entity=Entity();entity.Id="probe";data.RuntimeProgram.Entities=new[]{entity};
                var slot=data.VfxManifest.Slots[0];slot.EntityId="probe";slot.Event="on_hit";slot.RepeatEvery=0;slot.StartTick=2;
                var crit=new VfxSlotSpec{Id="crit",EntityId="probe",Event="on_crit",RendererKind="spriteElement",Element=slot.Element,Duration=12,Alpha=1};data.VfxManifest.Slots=new[]{slot,crit};
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
                Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=2;
                foreach(var bytes in relays)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),256);
                Equal(3,OwnedMaterialQueue().Count,"remote has all distinct delayed world emissions without surviving source");
                MaterialClock(tick+2);system.PostUpdateEverything();Equal(3,OwnedMaterialQueue().Count,"remote emission uses captured world pose at due tick");
                foreach(var bytes in relays)mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)),256);Equal(3,OwnedMaterialQueue().Count,"remote same occurrence replay suppressed");
                Vector2 EmittedVelocity(object emission) {var parts=(Array)emission.GetType().GetField("Particles",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(emission)!;var part=parts.GetValue(0)!;return (Vector2)part.GetType().GetField("Velocity",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(part)!;}
                AssertVfxNear(new Vector2(1+0.5f,0),EmittedVelocity(OwnedMaterialQueue()[0]!),"real owner/server/remote delayed chain inherits MaxUpdates=1");
                AssertVfxNear(new Vector2(1+3*0.5f,0),EmittedVelocity(OwnedMaterialQueue()[2]!),"real owner/server/remote delayed chain copies MaxUpdates=3 before source removal");
                // Reuse the real owner->server->remote chain with exact live attachment.
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
            }finally{system.OnWorldUnload();netMods.SetValue(null,priorNetMods);registryProperty.SetValue(null,oldRegistry);modProperty.SetValue(null,oldMod);Terraria.Main.projectile=oldProjectiles;Terraria.Main.player[0]=oldOwner;Terraria.Main.netMode=oldMode;Terraria.Main.myPlayer=oldLocal;MaterialClock(tick);}
        });
    }

    private static void MaterialItemSnapshotRelayPreservesPoseAndInstance()
    {
        WithLighting((_,__)=> {
            var system=new InfiniDetachedVfxSystem();var oldOwner=Terraria.Main.player[0];var tick=Terraria.Main.GameUpdateCount;
            var mp=typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Instance")!;var oldMod=mp.GetValue(null);
            var rp=typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;var oldRegistry=rp.GetValue(null);
            var mod=new global::InfiniCrafterLocal.InfiniCrafterLocalMod();typeof(Terraria.ModLoader.Mod).GetField("netID",BindingFlags.Instance|BindingFlags.NonPublic)!.SetValue(mod,(short)0);
            var netMods=typeof(Terraria.ModLoader.Mod).Assembly.GetType("Terraria.ModLoader.ModNet")!.GetField("netMods",BindingFlags.Static|BindingFlags.NonPublic)!;var priorNetMods=netMods.GetValue(null);
            using var registry=new InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService();
            var outgoing=new System.Collections.Generic.List<byte[]>();var starts=new System.Collections.Generic.Dictionary<Terraria.ModLoader.ModPacket,int>();
            VfxGetPacketHook packet=(orig,self,capacity)=>{var p=orig(self,capacity);starts[p]=(int)p.BaseStream.Position;return p;};
            Action<Terraria.ModLoader.ModPacket,int,int> send=(p,to,ignore)=>outgoing.Add(((MemoryStream)p.BaseStream).ToArray()[starts[p]..]);
            using var gh=new MonoMod.RuntimeDetour.Hook(typeof(Terraria.ModLoader.Mod).GetMethod("GetPacket")!,packet);
            using var sh=new MonoMod.RuntimeDetour.Hook(typeof(Terraria.ModLoader.ModPacket).GetMethod("Send")!,send);
            var mode=Terraria.Main.netMode;var local=Terraria.Main.myPlayer;
            try {
                system.OnWorldUnload();InfiniItemVfxRuntime.ClearUseEventCaches();mp.SetValue(null,mod);rp.SetValue(null,registry);netMods.SetValue(null,new Terraria.ModLoader.Mod[]{mod});
                var data=ParseMaterialElement(MaterialElementWire());data.Id="item_material_net";InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
                var entity=data.RuntimeProgram.Entities[0];var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;slot.StartTick=2;
                data.RuntimeProgram.Bindings=new[]{new RuntimeBindingSpec{Id="primary",Role=RuntimeEntityRole.Primary,Input=RuntimeInputKind.PrimaryUse,UsePolicy=new RuntimeBindingUsePolicySpec{ContactDamage=true,Action=new RuntimeBindingActionSpec{Kind=RuntimeBindingAction.UseItemBody,TargetId=entity.Id}}}};
                ((System.Collections.IDictionary)registry.GetType().GetField("_byId",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(registry)!).Add(data.Id,data);
                InfiniCrafterLocal.Content.Items.GeneratedItem Host() {var gi=new InfiniCrafterLocal.Content.Items.GeneratedItem();var item=new Item{type=1,stack=1};typeof(Terraria.ModLoader.ModType<Item>).GetProperty("Entity")!.SetValue(gi,item);typeof(Item).GetProperty("ModItem")!.SetValue(item,gi);typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(gi,data);return gi;}
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
            }finally{system.OnWorldUnload();InfiniItemVfxRuntime.ClearUseEventCaches();netMods.SetValue(null,priorNetMods);mp.SetValue(null,oldMod);rp.SetValue(null,oldRegistry);Terraria.Main.player[0]=oldOwner;Terraria.Main.netMode=mode;Terraria.Main.myPlayer=local;MaterialClock(tick);}
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

    private static void MaterialItemEventTotalIsSharedAcrossElementsAndLegacy()
    {
        WithLighting((_,__)=>{
            var system=new InfiniDetachedVfxSystem();try{
                system.OnWorldUnload();var data=ParseMaterialElement(MaterialElementWire());var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;
                var second=JsonSerializer.Deserialize<VfxSlotSpec>(JsonSerializer.Serialize(slot))!;second.Id="second";data.VfxManifest.Slots=new[]{slot,second};data.VfxManifest.Budget.MaxParticlesTotal=3;
                var player=new Player{active=true,whoAmI=0,Center=Vector2.Zero};
                InfiniItemVfxRuntime.EmitAndSyncEvent(player,data,slot.EntityId,slot.Event,new Vector2(10,20));
                int Count(){int n=0;foreach(var e in OwnedMaterialQueue())n+=((Array)e!.GetType().GetField("Particles",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(e)!).Length;return n;}
                Equal(3,Count(),"one item event's total allowance spans all owned element slots");
            }finally{system.OnWorldUnload();}
        });
    }

    private static void MaterialSourceHitAnchorStaysSourceLocal()
    {
        WithLighting((_,__)=>{
            var system=new InfiniDetachedVfxSystem();var prior=Terraria.Main.projectile[0];var owner=Terraria.Main.player[0];try{
                system.OnWorldUnload();Terraria.Main.player[0]=new Player{whoAmI=0,active=true};
                var data=ParseMaterialElement(MaterialElementWire("source"));var entity=Entity();entity.Id="probe";data.RuntimeProgram.Entities=new[]{entity};
                var slot=data.VfxManifest.Slots[0];slot.EntityId="probe";slot.Event="on_hit";slot.RepeatEvery=0;slot.Anchor="hitPoint";
                var p=Terraria.Main.projectile[0]=new Projectile{whoAmI=0,owner=0,identity=1,active=true,Center=new Vector2(100,100),velocity=Vector2.UnitX};
                var g=Attach(p);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(p,g);g.Configure(data,entity,0,0,Vector2.UnitX);
                g.OnHitNPC(new NPC{active=true,Center=new Vector2(120,130)},new NPC.HitInfo(),1);
                var e=OwnedMaterialQueue()[0]!;var particles=(Array)e.GetType().GetField("Particles",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(e)!;
                Equal(2,particles.Length,"source-attached hitPoint has an executable local-frame anchor");
                var first=particles.GetValue(0)!;
                Equal(new Vector2(23,28),(Vector2)first.GetType().GetField("Position",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(first)!,"captured actual hit point is retained as source-local displacement");
            }finally{system.OnWorldUnload();Terraria.Main.projectile[0]=prior;Terraria.Main.player[0]=owner;}
        });
    }
    private static void MaterialPeerHydrationKeepsSourceBudgetKeyAndWorldAge()
    {
        WithLighting((_,__)=>{
            var system=new InfiniDetachedVfxSystem();var prior=Terraria.Main.projectile[0];var owner=Terraria.Main.player[0];try{
                system.OnWorldUnload();Terraria.Main.player[0]=new Player{whoAmI=0,active=true};
                var data=ParseMaterialElement(MaterialElementWire("source"));var entity=Entity();entity.Id="probe";data.RuntimeProgram.Entities=new[]{entity};
                var slot=data.VfxManifest.Slots[0];slot.EntityId="probe";slot.StartTick=5;
                var p=Terraria.Main.projectile[0]=new Projectile{whoAmI=0,owner=0,identity=1,active=true,velocity=Vector2.UnitX};var g=Attach(p);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(p,g);
                typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetField("_age",BindingFlags.Instance|BindingFlags.NonPublic)!.SetValue(g,20);
                g.Configure(data,entity,0,0,Vector2.UnitX,preserveSyncedState:true);g.AI();system.PostUpdateEverything();
                Equal(1,OwnedMaterialQueue().Count,"late hydrated projectile uses observed world age rather than restarted activation age");
                var state=(InfiniVfxState)typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetField("_vfxState",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(g)!;
                Equal(true,state.SourceKey.StartsWith("net:0:",StringComparison.Ordinal),"active and relayed same-generation effects share peer source key before first event");
            }finally{system.OnWorldUnload();Terraria.Main.projectile[0]=prior;Terraria.Main.player[0]=owner;}
        });
    }

    private static void MaterialProfilesEvaluateAllCurvesAndCapturedRgb()
    {
        int cases=0;
        foreach(string curve in new[]{"linear","easeIn","easeOut","smoothStep"}) {
            var ramp=VfxNumberRamp.Copy(new VfxNumericProfileSpec{Start=0,Middle=4,End=0,Curve=curve});
            Equal(0f,ramp.At(0),"zero start "+curve);Equal(4f,ramp.At(0.5f),"exact middle "+curve);Equal(0f,ramp.At(1),"zero end "+curve);cases+=3;
            float expected=curve=="easeIn"?0.25f:curve=="easeOut"?1.75f:curve=="smoothStep"?0.625f:1;
            Equal(expected,ramp.At(0.125f),"fixed mathematical first interval "+curve);Equal(curve=="easeIn"?1.75f:curve=="easeOut"?0.25f:expected,ramp.At(0.875f),"independent second interval "+curve);cases+=2;
            var colors=new VfxColorProfileSpec{Start="white",Middle="effect",End="cyan",Curve=curve};var rgb=VfxColorRamp.Copy(colors,Color.Red);colors.Middle="black";
            Equal(Color.White,rgb.At(0,1,"alpha"),"white preserves source RGB");Equal(Color.Red,rgb.At(0.5f,1,"alpha"),"effect captures RGB without mutable DTO reference");
            Equal(Color.Transparent,rgb.At(0.5f,0,"alpha"),"zero opacity is exact silence");Equal((byte)0,rgb.At(0.5f,0.5f,"additive").A,"additive alpha protocol");cases+=4;
        }
        Console.WriteLine("DETAIL: material profile assertions="+cases);
    }
    private static void MaterialPathDtoRejectsWrongSourceAndPayloads()
    {
        JsonObject Wire(string source="beam") {
            var wire=MaterialElementWire();var row=wire["vfxManifest"]!["slots"]![0]!.AsObject();row.Remove("element");row["rendererKind"]="texturedPath";row["backend"]="Primitive";row["repeatEvery"]=0;row["duration"]=3;row["entityId"]="path_actor";
            row["path"]=JsonSerializer.SerializeToNode(MaterialPathSpec(source),new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase});
            var entity=new RuntimeEntitySpec{Id="path_actor",Kind=source=="anchorHistory"?RuntimeEntityKind.FreeProjectile:RuntimeEntityKind.OwnerAttachedProjectile};entity.Spawn.Enabled=true;entity.Visual.AssetMode="no_asset";entity.VisualRole=source=="anchorHistory"?"projectile":"held_body";entity.Visual.Role=entity.VisualRole;
            if(source=="beam"){entity.Controller.Name="channel_beam";entity.Controller.Code=RuntimeControllerCode.ChannelBeam;}
            if(source=="whip"){entity.Movement.Name="move_whip_lash";entity.Movement.Code=18;}
            if(source=="anchorHistory"){entity.Movement.Name="move_straight";entity.Movement.Code=0;}
            wire["runtimeProgram"]!["entities"]!.AsArray().Add(JsonSerializer.SerializeToNode(entity,new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase}));return wire;
        }
        foreach(string source in new[]{"beam","whip","anchorHistory"})Equal(true,ParseMaterialElement(Wire(source)) is not null,"real path DTO happy control "+source);
        int cases=0;
        void Reject(Action<JsonObject> f,string source="beam"){var w=Wire(source);f(w);Equal(true,GeneratedItemData.FromJson(w.ToJsonString()) is null,"invalid path DTO "+cases++);}
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["anchor"]="tip");
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["path"]=null);
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["path"]!["widthProfile"]=null);
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["path"]!["texture"]!["source"]="entity");
        Reject(w=>{w["vfxManifest"]!["slots"]![0]!["path"]!["texture"]!["source"]="entity";w["vfxManifest"]!["slots"]![0]!["path"]!["texture"]!["assetId"]="";w["vfxManifest"]!.AsObject().Remove("assets");});
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["path"]!["historyTicks"]=32);
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["path"]!["uvMode"]="stretch");
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["path"]!["profileDomain"]="age");
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["event"]="on_hit");
        Reject(w=>w["vfxManifest"]!["slots"]![0]!["path"]!["historyTicks"]=33,"anchorHistory");
        Reject(w=>{w["runtimeProgram"]!["entities"]![1]!["controller"]!["name"]="channel_beam";w["runtimeProgram"]!["entities"]![1]!["controller"]!["code"]=1;},"whip");
        Console.WriteLine("DETAIL: material path DTO controls=3 invalid="+cases);
    }

    private static void MaterialCapturedSourceHitPointIsNotRebasedToLatePeerPose()
    {
        WithLighting((_,__)=>{
            var system=new InfiniDetachedVfxSystem();var prior=Terraria.Main.projectile[0];var owner=Terraria.Main.player[0];try {
                system.OnWorldUnload();Terraria.Main.player[0]=new Player{active=true,whoAmI=0};
                var data=ParseMaterialElement(MaterialElementWire("source"));var entity=Entity();entity.Id="probe";data.RuntimeProgram.Entities=new[]{entity};
                var slot=data.VfxManifest.Slots[0];slot.EntityId="probe";slot.Event="on_hit";slot.RepeatEvery=0;slot.Anchor="hitPoint";
                var p=Terraria.Main.projectile[0]=new Projectile{whoAmI=0,owner=0,identity=1,active=true,Center=new Vector2(100,100),velocity=Vector2.UnitX};
                var g=Attach(p);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(p,g);g.Configure(data,entity,0,0,Vector2.UnitX);
                var snapshot=InfiniVfxProjectileSnapshot.Capture(p,data,entity.Id);var binding=VfxSourceBinding.Capture(p);
                p.Center=new Vector2(300,300);p.velocity=Vector2.UnitY;
                InfiniVfxRuntime.OnDetachedEvent(data,entity.Id,slot.Event,data.VfxManifest,new Vector2(120,130),Vector2.UnitX,"late_peer",snapshot,binding,88);
                var e=OwnedMaterialQueue()[0]!;var particles=(Array)e.GetType().GetField("Particles",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(e)!;
                Equal(new Vector2(23,28),(Vector2)particles.GetValue(0)!.GetType().GetField("Position",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(particles.GetValue(0))!,"source-local event displacement uses captured self and forward rather than late peer pose");
            }finally{system.OnWorldUnload();Terraria.Main.projectile[0]=prior;Terraria.Main.player[0]=owner;}
        });
    }

    private static void MaterialEmptyZeroMissingTextureControls()
    {
        WithVfxGeometryQueue((batch,texture,count,positions,colors)=>{
            var system=new InfiniDetachedVfxSystem();var sp=typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;var previous=sp.GetValue(null);
            using var cache=new InfiniCrafterLocal.Common.Services.RuntimeSpriteCache();var textures=(System.Collections.IDictionary)cache.GetType().GetField("_textures",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(cache)!;
            var cached=cache.GetType().GetNestedType("CachedTexture",BindingFlags.NonPublic)!;string key=Path.Combine(Terraria.Program.SavePath,"zero_controls.png");textures.Add(key,Activator.CreateInstance(cached,texture,0f,0L)!);
            var draw=typeof(InfiniDetachedVfxSystem).GetMethod("DrawMaterialSprites",BindingFlags.Static|BindingFlags.NonPublic)!;
            try {
                sp.SetValue(null,cache);int beginCalls=0;void Draw()=>draw.Invoke(null,new object[]{"BeforeProjectiles",batch,(Action)(()=>beginCalls++)});
                system.OnWorldUnload();Draw();Equal(0,count(),"empty owned manifest draws nothing");
                foreach(string control in new[]{"count","width","height","opacity","alpha","drawBudget","particleTickBudget","particleTotalBudget","missing"}) {
                    system.OnWorldUnload();var data=ParseMaterialElement(MaterialElementWire());var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;data.VfxManifest.Assets![0].SpritePath=control=="missing"?Path.Combine(Terraria.Program.SavePath,"absent_material.png"):key;
                    var e=slot.Element!;if(control=="count")e.Count=0;if(control=="width")e.WidthPx=0;if(control=="height")e.HeightPx=0;if(control=="opacity")e.OpacityProfile.Start=e.OpacityProfile.Middle=e.OpacityProfile.End=0;
                    if(control=="alpha")slot.Alpha=0;if(control=="drawBudget")data.VfxManifest.Budget.MaxDrawCalls=0;if(control=="particleTickBudget")data.VfxManifest.Budget.MaxParticlesPerTick=0;if(control=="particleTotalBudget")data.VfxManifest.Budget.MaxParticlesTotal=0;
                    InfiniDetachedVfxSystem.EnqueueElement(data,slot.EntityId,slot,"zero:"+control,new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero));Draw();
                    Equal(0,count(),"no FNA submission for "+control);Equal(0,beginCalls,"silent control owns no Begin "+control);
                }
                Console.WriteLine("DETAIL: material empty/zero/missing sprite draw controls=10");
            }finally{textures.Clear();sp.SetValue(null,previous);system.OnWorldUnload();}
        });
    }
    private static void MaterialMotionUsesDragAccelerationAndSpin()
    {
        WithLighting((_,__)=>{
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;
            try {
                system.OnWorldUnload();var data=ParseMaterialElement(MaterialElementWire());var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;var e=slot.Element!;
                e.SpeedMinPxPerTick=e.SpeedMaxPxPerTick=2;e.InheritVelocity=0;e.Drag=0.5f;e.AccelerationXPxPerTickSquared=1;e.AccelerationYPxPerTickSquared=-1;e.RotationRadians=0.25f;e.RotationSpeedRadiansPerTick=0.5f;
                InfiniDetachedVfxSystem.EnqueueElement(data,slot.EntityId,slot,"motion",new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero));MaterialClock(tick+2);system.PostUpdateEverything();
                var emission=OwnedMaterialQueue()[0]!;var particles=(Array)emission.GetType().GetField("Particles",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(emission)!;var particle=particles.GetValue(0)!;var flags=BindingFlags.Instance|BindingFlags.NonPublic;
                Equal(new Vector2(7,-4.5f),(Vector2)particle.GetType().GetField("Position",flags)!.GetValue(particle)!,"per-world-tick drag then acceleration then integration");
                Equal(1.25f,(float)particle.GetType().GetField("Rotation",flags)!.GetValue(particle)!,"spin integrates independent of width and aspect");
                system.PostUpdateEverything();Equal(new Vector2(7,-4.5f),(Vector2)particle.GetType().GetField("Position",flags)!.GetValue(particle)!,"duplicate update visits with frozen tick never integrate twice");
            }finally{system.OnWorldUnload();MaterialClock(tick);}
        });
    }

    private static void MaterialPathClientOwnerSamplesAndRetiresHistory()
    {
        WithLighting((_,__)=>{
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;var prior=Terraria.Main.projectile[0];var owner=Terraria.Main.player[0];
            var paths=(System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("MaterialPaths",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;var f=BindingFlags.Instance|BindingFlags.NonPublic;
            try {
                system.OnWorldUnload();Terraria.Main.player[0]=new Player{active=true,whoAmI=0};
                var data=ParseMaterialElement(MaterialElementWire());var entity=Entity();entity.Id="probe";data.RuntimeProgram.Entities=new[]{entity};
                var path=MaterialPathSpec("anchorHistory");path.HistoryTicks=4;path.WidthProfile.Start=path.WidthProfile.Middle=path.WidthProfile.End=1;
                data.VfxManifest.Slots=new[]{new VfxSlotSpec{Id="live_path",EntityId=entity.Id,Event="periodic",RendererKind="texturedPath",Backend="Primitive",Path=path,Anchor="self",Duration=3,RepeatEvery=0,Alpha=1}};
                var p=Terraria.Main.projectile[0]=new Projectile{whoAmI=0,owner=0,identity=1,active=true,velocity=Vector2.UnitX,timeLeft=90};var g=Attach(p);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(p,g);g.Configure(data,entity,0,0,Vector2.UnitX);
                g.AI();p.Center=Vector2.Zero;system.PostUpdateEverything();Equal(1,paths.Count,"canonical AI registers live path with client owner");
                var record=paths[0]!;var history=(System.Collections.IList)record.GetType().GetField("History",f)!.GetValue(record)!;
                system.PostUpdateEverything();Equal(1,history.Count,"one actual sample with duplicate hooks in frozen world tick");
                MaterialClock(tick+1);p.Center=new Vector2(16,0);system.PostUpdateEverything();
                MaterialClock(tick+2);p.Center=Vector2.Zero;system.PostUpdateEverything();Equal(3,history.Count,"actual reversal and world zero remain valid history");
                var last=history[2]!;Equal(Vector2.Zero,(Vector2)last.GetType().GetProperty("Position")!.GetValue(last)!,"sample is final source pose after motion");
                path.HistoryTicks=32;p.active=false;MaterialClock(tick+3);system.PostUpdateEverything();Equal(1,paths.Count,"retired history is allowed to age, not rebound");
                MaterialClock(tick+6);system.PostUpdateEverything();Equal(0,paths.Count,"copied four-tick history ages to silence without Draw or new events");
                Equal(0,OwnedMaterialQueue().Count,"history path never spawns particles or gameplay entities");
            }finally{system.OnWorldUnload();Terraria.Main.projectile[0]=prior;Terraria.Main.player[0]=owner;MaterialClock(tick);}
        });
    }
    private static void MaterialAssetRosterMatchesSharedPythonDtoFixture()
    {
        string path=Path.Combine(Directory.GetCurrentDirectory(),"LocalGenerator","tests","fixtures","vfx_asset_roster_parity_v1.json");
        using var fixture=JsonDocument.Parse(File.ReadAllText(path));var dto=fixture.RootElement.GetProperty("data");var data=new GeneratedItemData();
        string Read(JsonElement row,string key)=>row.TryGetProperty(key,out var value)?value.GetString()??"":"";
        var visual=dto.GetProperty("visual");data.Visual.SpritePath=Read(visual,"spritePath");data.Visual.EquipOverlayPath=Read(visual,"equipOverlayPath");
        data.RuntimeProgram.Entities=dto.GetProperty("runtimeProgram").GetProperty("entities").EnumerateArray().Select(e=>new RuntimeEntitySpec{Id=Read(e,"id"),Visual=new RuntimeEntityVisualSpec{SpritePath=Read(e.GetProperty("visual"),"spritePath"),ImpactSpritePath=Read(e.GetProperty("visual"),"impactSpritePath")}}).ToArray();
        data.VfxManifest.Assets=dto.GetProperty("vfxManifest").GetProperty("assets").EnumerateArray().Select(a=>new VfxAssetSpec{Id=Read(a,"id"),SpritePath=Read(a,"spritePath")}).ToArray();
        var expected=fixture.RootElement.GetProperty("expectedFiles").EnumerateArray().Select(a=>a.GetString()).ToArray();
        Equal(string.Join(",",expected),string.Join(",",InfiniCrafterLocal.Common.Services.GeneratedAssetSyncService.AssetFilesFromData(data)),"same canonical DTO PNG roster as Python; ignore metadata and diagnostic inventory");
        Console.WriteLine("DETAIL: shared Python/C# roster files="+expected.Length);
    }

    private static void MaterialProjectileInheritanceUsesLiveMaxUpdates()
    {
        WithLighting((_,__)=>{
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;var prior=Terraria.Main.projectile;var owner=Terraria.Main.player[4];int cases=0;
            try {
                Terraria.Main.player[4]=new Player{active=true,whoAmI=4};
                foreach(int extra in new[]{0,2})foreach(string mode in new[]{"local","localDelayed","remote","remoteDelayed","sourcePeriodic"}) {
                    system.OnWorldUnload();MaterialClock(tick);var data=ParseMaterialElement(MaterialElementWire());data.Id="inherit_units_"+extra+"_"+mode;
                    InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);var entity=Entity();entity.Id="probe";data.RuntimeProgram.Entities=new[]{entity};
                    var slot=data.VfxManifest.Slots[0];slot.EntityId="probe";slot.Event="on_hit";slot.RepeatEvery=0;slot.StartTick=mode.EndsWith("Delayed")?2:0;
                    var e=slot.Element!;e.Count=1;e.SpeedMinPxPerTick=e.SpeedMaxPxPerTick=0;e.InheritVelocity=1;e.Drag=1;e.AccelerationXPxPerTickSquared=e.AccelerationYPxPerTickSquared=0;
                    e.OffsetForwardPx=e.OffsetSidePx=0;
                    Terraria.Main.projectile=new Projectile[1];var p=Terraria.Main.projectile[0]=new Projectile{whoAmI=0,owner=4,identity=41,active=true,timeLeft=90,velocity=new Vector2(2,-3)};
                    var g=Attach(p);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(p,g);g.Configure(data,entity,0,0,Vector2.UnitX);p.extraUpdates=extra;
                    Vector2 expected=p.velocity*p.MaxUpdates;
                    if(mode.StartsWith("remote")) {
                        byte[] encoded=EncodeProjectileVfxForCheck(data,p,slot.Event,p.Center);
                        var payload=typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetMethod("ReadVfxEventPayload",BindingFlags.Static|BindingFlags.NonPublic)!.Invoke(null,new object[]{new BinaryReader(new MemoryStream(encoded))})!;
                        Equal(new Vector2(2,-3),(Vector2)payload.GetType().GetProperty("Velocity")!.GetValue(payload)!,"legacy event wire retains raw engine velocity");
                        var captured=(InfiniVfxProjectileSnapshot)payload.GetType().GetProperty("Snapshot")!.GetValue(payload)!;
                        Equal(expected,captured.MaterialVelocity,"versioned new snapshot copies the separately converted technical velocity");
                        byte[] invalid=encoded.ToArray();Buffer.BlockCopy(BitConverter.GetBytes(float.NaN),0,invalid,invalid.Length-17,4);
                        ReceiveProjectileVfxForCheck(data,invalid);Equal(0,OwnedMaterialQueue().Count,"nonfinite converted velocity rejected before remote event admission");
                        p.velocity=Vector2.Zero;p.extraUpdates=0;p.active=false;Terraria.Main.projectile=Array.Empty<Projectile>();ReceiveProjectileVfxForCheck(data,encoded);
                    }else if(mode=="sourcePeriodic") {
                        slot.Event="periodic";slot.RepeatEvery=1;e.Attachment="source";var state=new InfiniVfxState();InfiniVfxRuntime.OnTick(p,data,entity.Id,data.VfxManifest,ref state);
                        system.PostUpdateEverything();
                    }else {
                        g.OnHitNPC(new NPC{active=true,Center=new Vector2(10,20)},new NPC.HitInfo(),1);
                        if(mode.EndsWith("Delayed")){p.velocity=Vector2.Zero;p.extraUpdates=0;p.active=false;Terraria.Main.projectile=Array.Empty<Projectile>();}
                    }
                    if(mode.EndsWith("Delayed")){MaterialClock(tick+2);system.PostUpdateEverything();}
                    Equal(1,OwnedMaterialQueue().Count,"new unit inheritance emission exists "+extra+"/"+mode);
                    var emission=OwnedMaterialQueue()[0]!;var flags=BindingFlags.Instance|BindingFlags.NonPublic;var particles=(Array)emission.GetType().GetField("Particles",flags)!.GetValue(emission)!;
                    Equal(1,particles.Length,"exact singleton inheritance "+extra+"/"+mode);var particle=particles.GetValue(0)!;
                    Vector2 velocity=(Vector2)particle.GetType().GetField("Velocity",flags)!.GetValue(particle)!;
                    if(mode=="sourcePeriodic"){var frame=(VfxSourceFrame)emission.GetType().GetField("Frame",flags)!.GetValue(emission)!;velocity=frame.Rotate(velocity);}
                    AssertVfxNear(expected,velocity,"new element velocity is captured engine velocity times actual MaxUpdates "+extra+"/"+mode);
                    Console.WriteLine("DETAIL: inheritance units positive extraUpdates="+extra+" mode="+mode);cases++;
                }
                Console.WriteLine("DETAIL: world-tick inheritance cases="+cases);
            }finally{system.OnWorldUnload();Terraria.Main.projectile=prior;Terraria.Main.player[4]=owner;MaterialClock(tick);}
        });
    }

    private static void MaterialElementAssetUsesNetworkRoster()
    {
        var data = ParseMaterialElement(MaterialElementWire());
        data.VfxManifest.Assets![0].SpritePath = Path.Combine(Terraria.Program.SavePath, "recipe_vfx_Shard_A.png");
        byte[] png = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGMUDJ76n4GBgYGJAQoAHTQB/GtRKAwAAAAASUVORK5CYII=");
        File.WriteAllBytes(data.VfxManifest.Assets[0].SpritePath, png);
        using var sync = new InfiniCrafterLocal.Common.Services.GeneratedAssetSyncService();
        Equal("recipe_vfx_Shard_A.png", string.Join(",", InfiniCrafterLocal.Common.Services.GeneratedAssetSyncService.AssetFilesFromData(data)), "exact PNG asset roster");
        var roster = sync.BuildServerAssetDescriptors(data);
        Equal(1, roster.Length, "individual asset descriptor");
        Equal(true, sync.HasCompleteServerAssetRoster(data), "complete asset admission");
        Equal(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(png)).ToLowerInvariant(), roster[0].Sha256, "existing content hash");
        var transport = JsonNode.Parse(data.ToNetworkJson())!;
        Equal("", transport["vfxManifest"]!["assets"]![0]!["prompt"]!.GetValue<string>(), "transport strips author caption");
        Equal("recipe_vfx_Shard_A.png", transport["vfxManifest"]!["assets"]![0]!["spritePath"]!.GetValue<string>(), "transport strips local path");
        Equal("Shard_A", transport["vfxManifest"]!["slots"]![0]!["element"]!["texture"]!["assetId"]!.GetValue<string>(), "transport preserves exact render reference");
        var received=GeneratedItemData.FromJson(transport.ToJsonString());
        Equal(true,received is not null,"hydrated asset transport reopens");
        Equal("recipe_vfx_Shard_A.png",string.Join(",",InfiniCrafterLocal.Common.Services.GeneratedAssetSyncService.AssetFilesFromData(received!)),"stripped definition retains same AssetSync roster");
        var hashOwner=typeof(InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService).GetMethod("ComputeDefinitionHash",BindingFlags.Static|BindingFlags.NonPublic)!;
        var hash=(string)hashOwner.Invoke(null,new object[]{data})!;
        Equal(hash,(string)hashOwner.Invoke(null,new object[]{received!})!,"canonical existing definition hash survives new asset transport");
        var full=JsonNode.Parse(data.ToLocalCacheJson())!;
        Equal("one isolated soft shard",full["vfxManifest"]!["assets"]![0]!["prompt"]!.GetValue<string>(),"full local cache captions are not stripped");
        Equal("text",full["vfxManifest"]!["assets"]![0]!["negativePrompt"]!.GetValue<string>(),"full local cache negative caption is intact");
        Equal(data.VfxManifest.Assets[0].SpritePath,GeneratedItemData.FromJson(full.ToJsonString())!.VfxManifest.Assets![0].SpritePath,"full local asset metadata round trips unchanged");
        // The Python producer owns naming; these independent supplied final paths
        // are consumed literally while authored case/suffix-pair IDs stay distinct.
        var ids=new[]{"Glow","glow","spark","spark_refit"};var paths=new[]{"vfx_a001.png","vfx_a002.png","vfx_a003.png","vfx_a004.png"};
        data.VfxManifest.Assets=ids.Select((id,i)=>new VfxAssetSpec{Id=id,Prompt="one fixture ingredient",NegativePrompt="",CanvasSize=32,Layout=i%2==0?"cutout":"strip",SpritePath=Path.Combine(Terraria.Program.SavePath,paths[i]),SpriteStatus="generated",SpriteTechnicalScore=1}).ToArray();
        data.VfxManifest.Slots=ids.Select((id,i)=>{var s=JsonSerializer.Deserialize<VfxSlotSpec>(JsonSerializer.Serialize(data.VfxManifest.Slots[0]))!;s.Id="shared_"+i;s.Element!.Texture.AssetId=id;return s;}).ToArray();
        var shared=JsonSerializer.Deserialize<VfxSlotSpec>(JsonSerializer.Serialize(data.VfxManifest.Slots[0]))!;shared.Id="reuse";data.VfxManifest.Slots=data.VfxManifest.Slots.Append(shared).ToArray();
        foreach(var a in data.VfxManifest.Assets)File.WriteAllBytes(a.SpritePath,png);
        using var pairSync=new InfiniCrafterLocal.Common.Services.GeneratedAssetSyncService();
        Equal(string.Join(",",paths),string.Join(",",InfiniCrafterLocal.Common.Services.GeneratedAssetSyncService.AssetFilesFromData(data)),"distinct case and suffix IDs consume only declared filenames, shared reuse emits one roster row");
        Equal(4,pairSync.BuildServerAssetDescriptors(data).Length,"four declared files use existing descriptor/hash owner");
        var pair=GeneratedItemData.FromJson(data.ToNetworkJson())!;
        Equal(string.Join(",",ids),string.Join(",",pair.VfxManifest.Assets!.Select(a=>a.Id)),"exact authored identities survive network case/suffix pairs");
    }

    private static void MaterialElementStrictWireRejectsForeignNullAndDangling()
    {
        int cases = 0;
        void Reject(Action<JsonObject> change) {
            var wire = MaterialElementWire(); change(wire);
            Equal(true, GeneratedItemData.FromJson(wire.ToJsonString()) is null, "invalid material wire must fail, case=" + cases++);
        }
        Reject(w => w["vfxManifest"]!["assets"] = null);
        Reject(w => w["vfxManifest"]!["assets"]![0] = null);
        Reject(w => w["vfxManifest"]!["slots"]![0]!["element"] = null);
        Reject(w => w["vfxManifest"]!["slots"]![0]!["element"]!.AsObject().Remove("widthProfile"));
        Reject(w => w["vfxManifest"]!["slots"]![0]!["element"]!["widthProfile"] = null);
        Reject(w => w["vfxManifest"]!["slots"]![0]!["element"]!["widthPx"] = 129);
        Reject(w => w["vfxManifest"]!["slots"]![0]!["element"]!["texture"]!["assetId"] = "missing");
        Reject(w => w["vfxManifest"]!["assets"]![0]!["id"] = "../Shard_A");
        Reject(w => w["vfxManifest"]!["assets"]!.AsArray().Add(w["vfxManifest"]!["assets"]![0]!.DeepClone()));
        Reject(w => w["vfxManifest"]!["slots"] = new JsonArray());
        Reject(w => w["vfxManifest"]!["slots"]![0]!["rendererKind"] = "childMotes");
        Reject(w => w["vfxManifest"]!["slots"]![0]!["scale"] = 2);
        Reject(w => w["vfxManifest"]!["slots"]![0]!["element"]!["speedMaxPxPerTick"] = 0);
        Reject(w => w["vfxManifest"]!["slots"]![0]!["element"]!["colorProfile"]!["start"] = "CYAN");
        Reject(w => w["vfxManifest"]!["slots"]![0]!["startTick"] = 1); // no invented item activation clock
        Reject(w => w["vfxManifest"]!["assets"]![0]!["spritePath"] = "");
        Reject(w => w["vfxManifest"]!["assets"]![0]!["spriteStatus"] = "failed");
        foreach(string malformed in new[]{"Shard_A\n","Shard_A\r","Shard_A\r\n","Shard_A\u2028","Shard_A\u2029"," Shard_A","Shard_A "}) {
            Reject(w=>w["vfxManifest"]!["assets"]![0]!["id"]=malformed);
            Reject(w=>w["vfxManifest"]!["slots"]![0]!["element"]!["texture"]!["assetId"]=malformed);
            Equal(true,ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson",out var invalidRef)&&invalidRef!.Message.Contains("invalid VFX texture assetId",StringComparison.Ordinal),"malformed literal reference fails lexical validation before a dangling-ID lookup");
        }
        Console.WriteLine("DETAIL: material DTO invalid cases=" + cases);
    }

    private static void MaterialElementDtoPreservesAuthoredAxesAndAsset()
    {
        var data = ParseMaterialElement(MaterialElementWire());
        var local = JsonNode.Parse(data.ToLocalCacheJson())!;
        Equal(8f, local["vfxManifest"]!["slots"]![0]!["element"]!["widthPx"]!.GetValue<float>(), "independent width survives local cache");
        Equal(20f, local["vfxManifest"]!["slots"]![0]!["element"]!["heightPx"]!.GetValue<float>(), "independent height survives local cache");
        Equal("Shard_A", local["vfxManifest"]!["assets"]![0]!["id"]!.GetValue<string>(), "exact declared asset identity");
        var legacy = GeneratedItemData.Placeholder();
        foreach(string json in new[]{legacy.ToJson(),legacy.ToLocalCacheJson(),legacy.ToNetworkJson()}) {
            var manifest=JsonNode.Parse(json)!["vfxManifest"]!.AsObject();Equal(false,manifest.ContainsKey("assets"),"legacy asset absence stays absent in every full/cache/network serializer");
            foreach(var row in manifest["slots"]!.AsArray()) {Equal(false,row!.AsObject().ContainsKey("element"),"legacy element absence stays absent");Equal(false,row!.AsObject().ContainsKey("path"),"legacy path absence stays absent");}
        }
    }
}
