using System;using System.Linq;using System.IO;using System.Reflection;using System.Diagnostics;using System.Text.Json;using System.Security.Cryptography;using System.Collections.Generic;using InfiniCrafterLocal.Common.Services;using Terraria;using Terraria.ID;
class ProfileLastPrism {
 static void Main(string[] args){
  const BindingFlags all=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
  Terraria.Program.SavePath=Path.Combine(Path.GetTempPath(),"ifc-magic-profile-"+Guid.NewGuid());Directory.CreateDirectory(Terraria.Program.SavePath);Terraria.Main.dedServ=true;Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(91);
  for(int id=1;id<ProjectileID.Count;id++){var p=new Projectile();p.SetDefaults(id);ContentSamples.ProjectilesByType[id]=p;}
  string[] names={"LastPrism"};
  var rows=new List<object>();var method=typeof(GeneratorClient).GetMethod("Prepare",all)!;var process=Process.GetCurrentProcess();var client=new GeneratorClient();
  foreach(string name in names){var item=new Item(Convert.ToInt32(typeof(ItemID).GetField(name)!.GetValue(null)));var other=new Item(ItemID.DirtBlock);var player=new Player();
   for(int iteration=0;iteration<3;iteration++){
    Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(91);var par=method.GetParameters().Select(p=>p.HasDefaultValue?p.DefaultValue:null).ToArray();par[0]=item;par[1]=other;par[2]=player;
    long allocations=GC.GetTotalAllocatedBytes(true);var cpu=process.TotalProcessorTime;var clock=Stopwatch.StartNew();var request=method.Invoke(client,par)!;var packet=(string)request.GetType().GetProperty("PayloadJson",all)!.GetValue(request)!;clock.Stop();
    var row=new{name,itemType=item.type,iteration,measurement=iteration==0?"first_encounter_in_fixed_roster":"same_item_repeated_capture",wallSeconds=clock.Elapsed.TotalSeconds,cpuSeconds=(process.TotalProcessorTime-cpu).TotalSeconds,allocatedBytes=GC.GetTotalAllocatedBytes(true)-allocations,utf8Bytes=System.Text.Encoding.UTF8.GetByteCount(packet),sha256=Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(packet))).ToLowerInvariant()};rows.Add(row);Console.WriteLine(JsonSerializer.Serialize(row));
   }
  }
  File.WriteAllText(args[0],JsonSerializer.Serialize(new{scope="Headless actual Prepare, registered native samples, fixed roster; first encounter is not independent cold process per item; repeat captures share source caches; no gameplay loop/GPU/model",sourceModule=typeof(GeneratorClient).Module.ModuleVersionId,nativeModule=typeof(Projectile).Module.ModuleVersionId,rows},new JsonSerializerOptions{WriteIndented=true}));
 }
}
