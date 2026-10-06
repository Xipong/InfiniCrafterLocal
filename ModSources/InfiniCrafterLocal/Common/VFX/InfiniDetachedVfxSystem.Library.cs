#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Luminance.Core.Graphics;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ParticleLibrary.Core.V3;
using ParticleLibrary.Core.V3.Particles;
using ReLogic.Content;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.VFX;

public sealed partial class InfiniDetachedVfxSystem
{
    private const int MaxLibraryRecords=128;
    private const int LibraryReadyWaitTicks=30;
    private sealed record LibraryParticleDesign(int Count,float SpeedMin,float SpeedMax,float Spread,float Inheritance,float Drag,
        Vector2 Acceleration,float Width,float Height,float Rotation,float Spin,Vector3 ColorStart,Vector3 ColorEnd,float EndScale,float EndOpacity);
    private sealed record LibraryShakeDesign(float Strength,float Variance,float Direction,float Dissipation,float TaperStart,float TaperEnd);
    private sealed record LibraryDesign(string Layer,string Blend,float Alpha,int Duration,int MaxDraw,int MaxPerTick,int MaxTotal,
        bool ItemBudget,int Seed,LibraryParticleDesign? Particle,LibraryShakeDesign? Shake);
    private sealed class LibraryEmissionState(LibraryDesign design,int count)
    {
        internal readonly LibraryDesign Design=design;
        internal readonly int Count=count; // Client scaling is captured once, not on readiness retries.
        internal ParticleInfo[] Particles=Array.Empty<ParticleInfo>();
        internal ScreenShakeSystem.ShakeInfo? Shake;
        internal float? LastCameraStrength;
        internal bool Retired;
    }

    // Four fixed, manually rendered V3 buffers. GeometryBuffer automatically
    // registers only IDisposable ownership with ParticleManagerV3; no library
    // Renderable/Updatable registration, no invented Layer.AfterProjectiles.
    // World clear keeps these buffers reusable: the library has no unregister-
    // buffer API, so reallocating at every world would retain unbounded entries.
    private static LibraryBuffer[]? LibraryBuffers;
    private static Texture2D? LibraryStar;
    private static bool LibraryInitQueued,LibraryInitAttempted,LibraryUnloaded;
    private static int LibraryResourceEpoch;
    private static readonly object LibraryResourceGate=new();

    internal static bool EnqueueSnapshotVfx(GeneratedItemData data,string entityId,VfxSlotSpec slot,string sourceKey,VfxSourceFrame frame,
        VfxSourceBinding? binding=null,bool itemBudget=false,MaterialEventAllowance? allowance=null)
        =>VfxLibraryValidation.HasPayload(slot)?EnqueueLibrary(data,slot,sourceKey,frame,itemBudget,allowance)
            :EnqueueElement(data,entityId,slot,sourceKey,frame,binding,itemBudget,allowance);
    internal static bool HasSnapshotVfx(VfxSlotSpec slot)=>slot.Element is not null||VfxLibraryValidation.HasPayload(slot);
    internal static bool HasOwnedVfx(VfxSlotSpec slot)=>HasSnapshotVfx(slot)||slot.Path is not null;
    private static int LibraryRecordCount=>MaterialEmissions.Count(e=>e.Library is not null);
    private static int OwnedParticleCount=>MaterialEmissions.Sum(e=>e.Particles.Length+(e.Library?.Particles.Length??0));
    private static bool LibraryClient=>!Main.dedServ&&Main.netMode!=NetmodeID.Server;
    private static bool LibraryEnabled(LibraryDesign d)=>LibraryClient&&(d.Particle is not null
        ?InfiniVfxClientOptions.EnableParticleLibraryBackend:InfiniVfxClientOptions.EnableLuminanceScreenShakeBackend);
    private static Color LibraryColor(string token,Color effect)=>token=="effect"?effect:token=="white"?Color.White:RuntimeColorPolicy.Resolve(token,Color.White);
    private static LibraryDesign CopyLibrary(GeneratedItemData data,VfxSlotSpec slot,bool item)
    {
        var budget=data.VfxManifest.Budget;
        var legacy=item?RuntimeColorPolicy.Resolve(data.Visual?.Palette?.Length>0?data.Visual.Palette[0]:"white",Color.White)
            :InfiniVfxRuntime.LegacyPresentationColor(data.VfxManifest,Color.White);
        var effect=InfiniVfxRuntime.PresentationColor(data,legacy);
        var p=slot.Particle;var s=slot.ScreenShake;
        return new(slot.Layer,slot.Blend,slot.Alpha,slot.Duration,budget.MaxDrawCalls,budget.MaxParticlesPerTick,budget.MaxParticlesTotal,item,slot.SlotSeed,
            p is null?null:new(p.Count,p.SpeedMinPxPerTick,p.SpeedMaxPxPerTick,p.SpreadRadians,p.InheritVelocity,p.Drag,
                new(p.AccelerationXPxPerTickSquared,p.AccelerationYPxPerTickSquared),p.WidthPx,p.HeightPx,p.RotationRadians,p.RotationSpeedRadiansPerTick,
                LibraryColor(p.ColorStart,effect).ToVector3(),LibraryColor(p.ColorEnd,effect).ToVector3(),p.EndScaleMultiplier,p.EndOpacity),
            s is null?null:new(s.StrengthPx,s.AngularVarianceRadians,s.DirectionRadians,s.DissipationPxPerFrame,s.TaperStartDistancePx,s.TaperEndDistancePx));
    }
    internal static bool EnqueueLibrary(GeneratedItemData data,VfxSlotSpec slot,string sourceKey,VfxSourceFrame frame,
        bool itemBudget=false,MaterialEventAllowance? allowance=null)
    {
        if(!LibraryClient||LibraryUnloaded||!frame.Valid||string.IsNullOrWhiteSpace(sourceKey)||!VfxLibraryValidation.HasPayload(slot))return false;
        try {slot.NormalizeAndValidate();} catch {return false;}
        return EnqueueCopiedLibrary(CopyLibrary(data,slot,itemBudget),sourceKey,frame,
            slot.Event==RuntimeEventKind.Periodic?0:slot.StartTick,allowance);
    }
    private static bool EnqueueCopiedLibrary(LibraryDesign design,string sourceKey,VfxSourceFrame frame,int delay,MaterialEventAllowance? allowance=null)
    {
        if(!LibraryEnabled(design)||LibraryUnloaded||!frame.Valid||design.MaxPerTick<=0||design.MaxTotal<=0||allowance is{Remaining:<=0}
            ||OwnedRecordCount>=MaxEmissions||LibraryRecordCount>=MaxLibraryRecords)return false;
        if(design.Particle is { } p&&(p.Count==0||p.Width<=0||p.Height<=0||design.Alpha<=0))return false;
        if(design.Shake is {Strength:<=0})return false;
        int count=design.Particle is {} particle?Math.Min(64,InfiniVfxClientOptions.ScaleParticleCount(particle.Count)):1;
        if(count<=0)return false;
        var e=new MaterialEmission{SourceKey=sourceKey,Frame=frame,InitialFrame=frame,Due=unchecked((uint)(Main.GameUpdateCount+(ulong)delay)),
            Library=new LibraryEmissionState(design,count),Allowance=allowance};
        MaterialEmissions.Add(e);
        if(delay==0)UpdateLibraryEmission(e,Main.GameUpdateCount);
        return true;
    }

    private static void UpdateLibraryEmission(MaterialEmission e,ulong now)
    {
        var state=e.Library!;var d=state.Design;
        if(state.Retired)return;
        if(!LibraryEnabled(d)){if(state.Shake is {} h)h.ShakeStrength=0;state.Retired=true;return;}
        int sinceDue=unchecked((int)((uint)now-(uint)e.Due));
        if(sinceDue<0)return;
        if(!e.Started) {
            if(d.Particle is not null&&!EnsureLibraryReady()) {
                if(sinceDue>=LibraryReadyWaitTicks)state.Retired=true;
                return;
            }
            e.Start=now;e.Started=true;
            if(d.Shake is {} shake) {
                // One admitted native handle consumes one existing particle-
                // instance budget; native camera cadence/dissipation stays native.
                if(Main.LocalPlayer is not{active:true}||e.Allowance is{Remaining:<=0}
                    ||!TrySpendDetachedParticle(e.SourceKey,d.MaxPerTick,d.ItemBudget?int.MaxValue:d.MaxTotal)){state.Retired=true;return;}
                if(e.Allowance is {} allowance)allowance.Remaining--;
                state.Shake=ScreenShakeSystem.StartShakeAtPoint(e.Frame.Position,shake.Strength,shake.Variance,
                    e.Frame.Rotate(new Vector2(MathF.Cos(shake.Direction),MathF.Sin(shake.Direction))),shake.Dissipation,shake.TaperEnd,shake.TaperStart);
                return;
            }
            int count=Math.Min(state.Count,MaxMaterialParticles-OwnedParticleCount);
            var particles=new List<ParticleInfo>(Math.Max(0,count));var random=new Random(d.Seed^unchecked((int)now));
            for(int i=0;i<count;i++) {
                if(e.Allowance is{Remaining:<=0}||!TrySpendDetachedParticle(e.SourceKey,d.MaxPerTick,d.ItemBudget?int.MaxValue:d.MaxTotal))break;
                if(e.Allowance is {} allowance)allowance.Remaining--;
                particles.Add(CreateLibraryInfoCore(d,e.Frame,(float)random.NextDouble(),(float)random.NextDouble()));
            }
            state.Particles=particles.ToArray();
        }
        if(d.Shake is not null){if(state.Shake is null||state.Shake.ShakeStrength<=0)state.Retired=true;return;}
        int age=(int)Math.Min((uint)d.Duration,unchecked((uint)now-(uint)e.Start));
        for(int t=e.IntegratedAge;t<age;t++)for(int i=0;i<state.Particles.Length;i++)AdvanceLibraryInfo(ref state.Particles[i]);
        e.IntegratedAge=age;
        if(age>=d.Duration||state.Particles.Length==0)state.Retired=true;
    }
    private static bool LibraryEmissionExpired(MaterialEmission e)=>e.Library!.Retired;

    public override void ModifyScreenPosition()
    {
        if(!LibraryClient)return;
        // Luminance's real camera hook dissipates every retained handle on each
        // visit, but universal rumble can remove it without zeroing its strength.
        // Observe that native progress across camera visits, never simulate it
        // with world ticks or inspect/mutate the library's private global roster.
        // Either relative hook order is valid: the first visit establishes a
        // sample; an orphan is detected after at most two subsequent visits.
        foreach(var emission in MaterialEmissions) {
            if(emission.Library is not {Retired:false,Shake:{ } shake} state)continue;
            if(shake.ShakeStrength<=0||state.LastCameraStrength==shake.ShakeStrength)state.Retired=true;
            else state.LastCameraStrength=shake.ShakeStrength;
        }
    }

    // CPU observer seam uses the exact creation/update path used at admission.
    internal static ParticleInfo CreateLibraryInfo(VfxSlotSpec slot,VfxSourceFrame frame,Color effect,float angleUnit,float speedUnit)
    {
        var p=slot.Particle!;var design=new LibraryDesign(slot.Layer,slot.Blend,slot.Alpha,slot.Duration,0,0,0,false,slot.SlotSeed,
            new(p.Count,p.SpeedMinPxPerTick,p.SpeedMaxPxPerTick,p.SpreadRadians,p.InheritVelocity,p.Drag,
                new(p.AccelerationXPxPerTickSquared,p.AccelerationYPxPerTickSquared),p.WidthPx,p.HeightPx,p.RotationRadians,p.RotationSpeedRadiansPerTick,
                LibraryColor(p.ColorStart,effect).ToVector3(),LibraryColor(p.ColorEnd,effect).ToVector3(),p.EndScaleMultiplier,p.EndOpacity),null);
        return CreateLibraryInfoCore(design,frame,angleUnit,speedUnit);
    }
    private static ParticleInfo CreateLibraryInfoCore(LibraryDesign design,VfxSourceFrame frame,float angleUnit,float speedUnit)
    {
        var p=design.Particle!;float angle=(angleUnit-0.5f)*p.Spread;
        Vector2 velocity=frame.Rotate(new Vector2(MathF.Cos(angle),MathF.Sin(angle))*MathHelper.Lerp(p.SpeedMin,p.SpeedMax,speedUnit))+frame.Velocity*p.Inheritance;
        return new ParticleInfo(new(frame.Position.X,frame.Position.Y),new(velocity.X,velocity.Y),frame.Forward.ToRotation()+p.Rotation,
            new(p.Width,p.Height),new Color(new Vector4(p.ColorStart,1))*design.Alpha,design.Duration,
            p.Drag,p.Acceleration.X,p.Acceleration.Y,p.Spin,p.EndScale,p.EndOpacity,design.Alpha,
            p.ColorStart.X,p.ColorStart.Y,p.ColorStart.Z,p.ColorEnd.X,p.ColorEnd.Y,p.ColorEnd.Z);
    }
    internal static void AdvanceLibraryInfo(ref ParticleInfo info)
    {
        if(info.Time<=0)return;
        var d=info.Data;info.Velocity=info.Velocity*d[0]+new System.Numerics.Vector2(d[1],d[2]);info.Position+=info.Velocity;info.Rotation+=d[3];info.Time--;
        float age=1-info.Time/(float)info.Duration;
        info.Scale=info.InitialScale*MathHelper.Lerp(1,d[4],age);
        Vector3 rgb=Vector3.Lerp(new(d[7],d[8],d[9]),new(d[10],d[11],d[12]),age);
        info.Color=info.Time==0?Color.Transparent:new Color(new Vector4(rgb,1))*(d[6]*MathHelper.Lerp(1,d[5],age));
    }

    private static bool EnsureLibraryReady()
    {
        int epoch;
        lock(LibraryResourceGate) {
            if(!LibraryClient||LibraryUnloaded)return false;
            if(LibraryBuffers is not null&&LibraryStar is not null)return true;
            // Headless/loading absence is normal; no half-initialized buffers.
            if(LibraryInitQueued||LibraryInitAttempted||Main.graphics?.GraphicsDevice is null||ParticleManagerV3.InstancedParticleEffect is null)return false;
            LibraryInitQueued=true;LibraryInitAttempted=true;epoch=LibraryResourceEpoch;
        }
        Main.QueueMainThreadAction(()=>{
            var buffers=new List<LibraryBuffer>(4);
            try {
                lock(LibraryResourceGate)if(epoch!=LibraryResourceEpoch||LibraryUnloaded||!LibraryClient)return;
                var texture=ModContent.Request<Texture2D>("ParticleLibrary/Assets/Textures/Star",AssetRequestMode.ImmediateLoad).Value;
                for(int i=0;i<4;i++) {var buffer=new LibraryBuffer();buffers.Add(buffer);buffer.InitializeOwned();}
                lock(LibraryResourceGate) {
                    if(epoch!=LibraryResourceEpoch||LibraryUnloaded||buffers.Any(b=>b.Capacity==0))return;
                    LibraryStar=texture;LibraryBuffers=buffers.ToArray();buffers.Clear();
                }
            }catch(Exception error){InfiniCrafterLocalMod.Instance?.Logger.Warn("Explicit library VFX initialization failed; no fallback: "+error.Message);}
            finally{
                foreach(var buffer in buffers)buffer.DisposeOwned();
                lock(LibraryResourceGate)LibraryInitQueued=false;
            }
        });
        return false;
    }
    private static void DrawLibraryParticles(string layer,GraphicsDevice device)
    {
        LibraryBuffer[]? buffers;Texture2D? star;
        lock(LibraryResourceGate){buffers=LibraryBuffers;star=LibraryStar;}
        if(!LibraryClient||!InfiniVfxClientOptions.EnableParticleLibraryBackend||buffers is null||star is null)return;
        for(int blend=0;blend<2;blend++) {
            var buffer=buffers[(layer=="AfterProjectiles"?2:0)+blend];int count=0;
            string blendName=blend==0?"alpha":"additive";
            foreach(var e in MaterialEmissions) {
                if(!e.Started||e.Library is not {Retired:false} state||state.Design.Particle is null
                    ||state.Design.Layer!=layer||state.Design.Blend!=blendName)continue;
                foreach(var info in state.Particles) {
                    if(count>=buffer.Capacity)break;
                    if(info.Time<=0||info.Scale.X<=0||info.Scale.Y<=0)continue;
                    Color color=info.Color*InfiniVfxClientOptions.ParticleAlphaMultiplier;
                    if(color.A==0)continue;
                    // Additive uses SourceAlpha/One; RGB is already premultiplied.
                    // Unit vertex alpha avoids multiplying authored opacity twice.
                    if(blend==1)color.A=255;
                    // Compact ONLY this exact source's admitted particles. A zero-
                    // budget source never piggybacks inside another source's batch.
                    if(!TrySpendSourceDraw(e.SourceKey,state.Design.MaxDraw,1))break;
                    buffer.Instances[count++]=new ParticleInstance {Position_Scale=new Vector4(info.Position.X,info.Position.Y,info.Scale.X,info.Scale.Y),
                        Rotation_Depth=new Vector2(info.Rotation,info.Depth),Color=color};
                }
            }
            if(count>0)buffer.RenderOwned(device,star,count,blend==0?BlendState.AlphaBlend:BlendState.Additive);
        }
    }
    private static void ClearLibrary(bool unload=false)
    {
        foreach(var e in MaterialEmissions)if(e.Library?.Shake is {} shake)shake.ShakeStrength=0;
        if(!unload)return; // world clears pending records at the canonical owner, keeps four fixed resources
        LibraryBuffer[]? owned;
        lock(LibraryResourceGate){LibraryUnloaded=true;LibraryResourceEpoch++;owned=LibraryBuffers;LibraryBuffers=null;LibraryStar=null;}
        if(owned is not null)Main.QueueMainThreadAction(()=>{foreach(var b in owned)b.DisposeOwned();});
    }
    private static void LoadLibrary()
    {
        lock(LibraryResourceGate){LibraryUnloaded=false;LibraryInitAttempted=false;LibraryResourceEpoch++;}
    }

    private sealed class LibraryBuffer : GeometryBuffer<VertexPositionTexture,ParticleInstance>,IDisposable
    {
        internal readonly ParticleInstance[] Instances;
        internal int Capacity=>Instances.Length;
        private VertexBuffer? Vertices;
        private IndexBuffer? Indices;
        private DynamicVertexBuffer? InstanceBuffer;
        private VertexDeclaration? Declaration;
        private VertexBufferBinding[]? Bindings;
        internal LibraryBuffer():base(MaxMaterialParticles){Instances=new ParticleInstance[GetMaxInstances()];}
        internal void InitializeOwned()
        {
            // Do NOT use base.Initialize: its nested queued callback is unguarded
            // and can allocate after Clear/Unload. All allocation is inside the
            // helper's one caught, epoch-fenced graphics-owner callback.
            if(Capacity==0)return;
            var device=Main.graphics.GraphicsDevice;
            Vertices=new VertexBuffer(device,typeof(VertexPositionTexture),4,BufferUsage.WriteOnly);
            Indices=new IndexBuffer(device,IndexElementSize.SixteenBits,6,BufferUsage.WriteOnly);
            Vertices.SetData(new[]{new VertexPositionTexture(new Vector3(-0.5f,-0.5f,0),Vector2.Zero),
                new VertexPositionTexture(new Vector3(-0.5f,0.5f,0),Vector2.UnitY),new VertexPositionTexture(new Vector3(0.5f,-0.5f,0),Vector2.UnitX),
                new VertexPositionTexture(new Vector3(0.5f,0.5f,0),Vector2.One)});
            Indices.SetData(new short[]{0,2,3,0,3,1});
            Declaration=new VertexDeclaration(new VertexElement(0,VertexElementFormat.Vector4,VertexElementUsage.Normal,0),
                new VertexElement(16,VertexElementFormat.Vector2,VertexElementUsage.Normal,1),new VertexElement(24,VertexElementFormat.Color,VertexElementUsage.Color,0));
            InstanceBuffer=new DynamicVertexBuffer(device,Declaration,Capacity,BufferUsage.WriteOnly);
            Bindings=new[]{new VertexBufferBinding(Vertices),new VertexBufferBinding(InstanceBuffer,0,1)};
        }
        internal void RenderOwned(GraphicsDevice device,Texture2D texture,int count,BlendState blend)
        {
            if(count<=0||Bindings is null||InstanceBuffer is null)return;
            var oldBlend=device.BlendState;var oldDepth=device.DepthStencilState;var oldRaster=device.RasterizerState;
            var oldSampler=device.SamplerStates[0];var oldTexture=device.Textures[0];var oldIndices=device.Indices;var oldVertices=device.GetVertexBuffers();
            try {
                InstanceBuffer.SetData(Instances,0,count,SetDataOptions.Discard);
                device.BlendState=blend;device.DepthStencilState=DepthStencilState.None;device.RasterizerState=Main.Rasterizer;
                device.SamplerStates[0]=SamplerState.PointClamp;device.SetVertexBuffers(Bindings);device.Indices=Indices;device.Textures[0]=texture;
                ParticleManagerV3.InstancedParticleEffect.Apply();device.DrawInstancedPrimitives(PrimitiveType.TriangleList,0,0,4,0,2,count);
            }finally {
                device.SetVertexBuffers(oldVertices);device.Indices=oldIndices;device.Textures[0]=oldTexture;device.SamplerStates[0]=oldSampler;
                device.BlendState=oldBlend;device.DepthStencilState=oldDepth;device.RasterizerState=oldRaster;
            }
        }
        // Only the exact detached under/over owner calls RenderOwned.
        public override void Render() { }
        internal void DisposeOwned()
        {
            Vertices?.Dispose();Vertices=null;Indices?.Dispose();Indices=null;InstanceBuffer?.Dispose();InstanceBuffer=null;Declaration?.Dispose();Declaration=null;Bindings=null;
            base.Dispose();
        }
        void IDisposable.Dispose()=>DisposeOwned();
    }
}
