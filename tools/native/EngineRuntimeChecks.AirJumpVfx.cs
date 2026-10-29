using System;
using System.IO;
using System.Reflection;
using System.Text;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void AirJumpVfxProducerAndPacketContract()
    {
        var data=NativeUtilityItem("\"playerEffect\":{\"airJump\":{\"count\":2,\"launchSpeedPxPerTick\":8,\"holdDurationTicks\":12}}").Data;
        Equal(true,data.HasAirJumpProducer,"functional authored movement proves jump presentation");
        var body=data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!;
        RuntimeEventKind.ValidateProducer(body,RuntimeEventKind.OnJump,false,false,true,true);
        bool refused=false;
        try{RuntimeEventKind.ValidateProducer(body,RuntimeEventKind.OnJump,false,false,true);}
        catch(InvalidDataException){refused=true;}
        Equal(true,refused,"equipment alone cannot invent a jump producer");
        data.VfxManifest=LightManifest(body.Id,RuntimeEventKind.OnJump);
        data.Normalize();
        data.VfxManifest.Slots[0].Anchor="tip";
        refused=false;
        try{data.Normalize();}catch(InvalidDataException){refused=true;}
        Equal(true,refused,"jump presentation cannot borrow an unrelated held-item tip");
        data.VfxManifest.Slots[0].Anchor="self";data.Normalize();
        data.Accessory.PlayerEffect=new PlayerEffectSpec{NightVision=true};
        Equal(false,data.HasAirJumpProducer,"unrelated player modifier cannot expose on_jump");
        refused=false;
        try{data.Normalize();}catch(InvalidDataException){refused=true;}
        Equal(true,refused,"strict native VFX admission rejects unavailable jump event");

        MethodInfo read=typeof(InfiniItemVfxRuntime).GetMethod("ReadAirJumpEvent",BindingFlags.Static|BindingFlags.NonPublic)!;
        byte[] Wire(long generation=11,string item="jump_source",float centerX=40)
        {
            using var stream=new MemoryStream();using var writer=new BinaryWriter(stream);
            writer.Write((byte)0);writer.Write(generation);writer.Write((ulong)3);
            writer.Write(item);writer.Write(new string('a',64));writer.Write("item");
            foreach(var vector in new[]{new Vector2(40,50),new Vector2(centerX,50),new Vector2(60,50),Vector2.UnitX,new Vector2(2,-8)})
            {writer.Write(vector.X);writer.Write(vector.Y);}
            return stream.ToArray();
        }
        object Decode(byte[] bytes)=>read.Invoke(null,new object[]{new BinaryReader(new MemoryStream(bytes))})!;
        bool Rejected(byte[] bytes)
        {
            try{Decode(bytes);return false;}
            catch(TargetInvocationException error) when(error.InnerException is InvalidDataException or DecoderFallbackException or EndOfStreamException){return true;}
        }
        object packet=Decode(Wire());
        Equal(11L,(long)packet.GetType().GetProperty("Generation")!.GetValue(packet)!,"grant lifetime crosses exact wire");
        Equal(new Vector2(40,50),(Vector2)packet.GetType().GetProperty("Point")!.GetValue(packet)!,"captured jump point crosses exact wire");
        var snapshot=(InfiniItemVfxSnapshot)packet.GetType().GetProperty("Snapshot")!.GetValue(packet)!;
        Equal(new Vector2(2,-8),snapshot.Velocity,"jump snapshot preserves authored actual movement");
        Equal(true,Rejected(Wire(generation:0)),"zero lifetime cannot witness a jump");
        Equal(true,Rejected(Wire(centerX:float.NaN)),"nonfinite source snapshot rejected");
        Equal(true,Rejected(Wire(item:new string('x',257))),"item identity bounded by UTF8 bytes");
        using var oversized=new MemoryStream();
        using(var writer=new BinaryWriter(oversized,Encoding.UTF8,true))
        {writer.Write((byte)0);writer.Write(11L);writer.Write((ulong)3);writer.Write7BitEncodedInt(int.MaxValue);}
        Equal(true,Rejected(oversized.ToArray()),"length guard rejects oversized declaration before allocating or reading payload");
    }

    private static void AirJumpVfxLiveSourceAdmission()
    {
        using var actors=new NativeActorState();
        using var jumps=new NativeAirJumpScope();
        WithPlayer((player,owner)=>{
            player.active=true;player.whoAmI=0;Terraria.Main.player[0]=player;
            var source=AirJumpSource("jump_vfx_source");
            source.Gameplay.GeneratedBuff=new GeneratedBuffSpec{DurationTicks=60,
                PlayerEffect=new PlayerEffectSpec{AirJump=source.Accessory.PlayerEffect!.AirJump!}};
            source.VfxManifest=LightManifest(source.RuntimeProgram.ItemEntityId,RuntimeEventKind.OnJump);
            source.Normalize();
            owner.RegisterAirJumpGrant(source,source.Accessory.PlayerEffect!.AirJump!,11);
            MethodInfo read=typeof(InfiniItemVfxRuntime).GetMethod("ReadAirJumpEvent",BindingFlags.Static|BindingFlags.NonPublic)!;
            MethodInfo resolve=typeof(InfiniItemVfxRuntime).GetMethod("TryResolveAirJumpEvent",BindingFlags.Static|BindingFlags.NonPublic)!;
            object Claim(long generation=11,string? definition=null,string? entity=null)
            {
                using var stream=new MemoryStream();
                using(var writer=new BinaryWriter(stream,Encoding.UTF8,true))
                {
                    writer.Write((byte)0);writer.Write(generation);writer.Write((ulong)1);
                    writer.Write(source.Id);writer.Write(definition??GeneratedItemRegistryService.DefinitionIdentity(source));
                    writer.Write(entity??source.RuntimeProgram.ItemEntityId);
                    foreach(var vector in new[]{Vector2.Zero,Vector2.Zero,Vector2.Zero,Vector2.UnitX,new Vector2(0,-9.25f)})
                    {writer.Write(vector.X);writer.Write(vector.Y);}
                }
                stream.Position=0;return read.Invoke(null,new object[]{new BinaryReader(stream)})!;
            }
            bool Admitted(object claim)
                =>(bool)resolve.Invoke(null,new object?[]{claim,player,null})!;
            object valid=Claim();
            Equal(true,Admitted(valid),"exact current authored jump grant admits its source event");
            Equal(false,Admitted(Claim(generation:12)),"different physical/buff lifetime cannot borrow a grant");
            Equal(false,Admitted(Claim(definition:new string('b',64))),"same item id cannot borrow a different definition");
            Equal(false,Admitted(Claim(entity:"other_entity")),"jump grant owns exactly its item-body VFX entity");
            owner.RegisterAirJumpGrant(source,source.Accessory.PlayerEffect.AirJump!,-22,"buff");
            Equal(true,Admitted(Claim(generation:-22)),"second same-item component resolves its exact active lifetime");
            Equal(true,Admitted(valid),"first same-item component stays independently active");
            var secondBinding=VfxSourceBinding.CaptureAirJump(player,source.Id,-22);
            Equal(true,secondBinding.IsLive,"attached VFX resolve the requested same-item component");
            owner.ResetAirJumpGrants();
            Equal(false,Admitted(valid),"retired source cannot emit a delayed claim");
            owner.RegisterAirJumpGrant(source,source.Accessory.PlayerEffect.AirJump!,12);
            Equal(false,Admitted(valid),"same definition renewed with new lifetime rejects old claim");
            Equal(true,Admitted(Claim(generation:12)),"renewed current source accepts its own lifetime");
            Equal(false,secondBinding.IsLive,"other component cannot inherit a renewed same-item grant");
            player.dead=true;
            Equal(false,Admitted(Claim(generation:12)),"dead owner cannot revive presentation");
        });
    }
}
