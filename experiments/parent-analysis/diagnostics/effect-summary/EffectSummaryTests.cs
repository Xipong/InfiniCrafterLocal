#nullable enable
using System; using System.Collections.Generic; using System.Diagnostics; using System.Linq; using System.Reflection; using System.Text.Json; using System.IO; using Terraria;
internal static class EffectSummaryTests {
 const BindingFlags F=BindingFlags.NonPublic|BindingFlags.Public|BindingFlags.Static|BindingFlags.Instance;
 static Projectile? Other;
 class CctorMutates { static CctorMutates(){Other!.type=4;} public static void SafeLooking(Projectile p){p.scale=2;} }
 static void ViaCctor(Projectile p)=>CctorMutates.SafeLooking(p); static object? Sink;
 public class Open { public virtual void Touch(Projectile p) { } }
 public sealed class Closed { public void Touch(Projectile p) { p.scale=2; } }
 public sealed class Wrap { public readonly Entity Parent; public Wrap(Entity p){Parent=p;} }
 public sealed class ScalarWrap { public readonly int Value; public ScalarWrap(Entity p){Value=p.width;} }
 static int Read(Projectile p)=>p.type;
 static void Motion(Projectile p)=>p.scale=2;
 static void Nested(Projectile p)=>Motion(p);
 static void LocalAlias(Projectile p){var alias=p; alias.rotation=2;}
 static void JoinAlias(Projectile p,bool cond){var alias=cond?p:Other!;alias.scale=2;}
 static void Identity(Projectile p)=>p.type=4;
 static void Style(Projectile p)=>p.aiStyle=4;
 static void AliasIdentity(Projectile p){object a=p;((Projectile)a).type=4;}
 static void JoinIdentity(Projectile p,bool cond){var alias=cond?p:Other!;alias.type=4;}
 static void OtherIdentity(Projectile p){Other!.type=4;}
 static void Escape(Projectile p)=>Sink=p;
 static void EscapeAlias(Projectile p){object a=p;Sink=a;}
 static Projectile ReturnAlias(Projectile p)=>p;
 static object ReturnWrapper(Projectile p)=>new Wrap(p);
 static void CtorEscape(Projectile p){_ =new Wrap(p);}
 static int CtorReads(Projectile p){return new ScalarWrap(p).Value;}
 static void ViaOpen(Projectile p,Open o)=>o.Touch(p);
 static void ViaClosed(Projectile p,Closed o)=>o.Touch(p);
 static void Recursive(Projectile p){if(p.width>0)Recursive(p);}
 static void TryFinally(Projectile p){try {p.scale=2;}finally{p.type=4;}}
 static void TryCatch(Projectile p){try{p.type=4;throw new Exception();}catch{}}
 static void RefTarget(ref Projectile p){p.type=4;}
 static void RefLocal(Projectile p){var a=p;RefTarget(ref a);}
 static void IdentityAddress(Projectile p){Set(ref p.type);}
 static void Set(ref int v){v=4;}
 static void Indirect(Projectile p,ref object output){output=p;}
 static void ArrayEscape(Projectile p,Projectile[] a){a[0]=p;}
 static void ThrowAlias(Projectile p){throw new Exception(p.ToString());}
 static void Deep1(Projectile p)=>Deep2(p); static void Deep2(Projectile p)=>Motion(p);
 static MethodInfo M(string n)=>typeof(EffectSummaryTests).GetMethod(n,F)!;
 static int Main(string[] args){
 var rows=new List<object>();int count=0;
 void Check(string label,MethodBase m,bool expected,ClosedEffectSummary? engine=null){var sw=Stopwatch.StartNew();var r=(engine??new()).Analyze(m);sw.Stop();if(r.Proven!=expected)throw new Exception(label+": expected="+expected+" actual="+r);rows.Add(new{label,expected,result=r,elapsedMs=sw.Elapsed.TotalMilliseconds});count++;Console.WriteLine("PASS "+label+" "+r.Reason);}
 foreach(string n in new[]{"Read","Motion","Nested","LocalAlias","JoinAlias","CtorReads","ViaClosed"})Check(n,M(n),true);
 foreach(string n in new[]{"Identity","Style","AliasIdentity","JoinIdentity","OtherIdentity","Escape","EscapeAlias","ReturnAlias","ReturnWrapper","CtorEscape","ViaOpen","Recursive","TryFinally","TryCatch","RefTarget","RefLocal","IdentityAddress","Indirect","ArrayEscape","ThrowAlias","ViaCctor"})Check(n,M(n),false);
 Check("open virtual root dispatch",typeof(Open).GetMethod("Touch",F)!,true);
 var dispatch = new ClosedEffectSummary().AnalyzeInvocation(typeof(Open).GetMethod("Touch",F)!,"callvirt"); if(dispatch.Proven)throw new Exception("Open virtual root must reject");count++;rows.Add(new{label="open virtual root invocation rejects",expected=false,result=dispatch,elapsedMs=0});
 Check("depth limit",M("Deep1"),false,new(maxDepth:1));Check("method limit",M("Nested"),false,new(maxMethods:1));Check("instruction limit",M("Motion"),false,new(maxInstructions:1));Check("byte limit",M("Motion"),false,new(maxBytes:1));
 foreach(string n in new[]{"get_Center","set_Center"})Check("Entity."+n,typeof(Entity).GetMethod(n,F)!,true);
 foreach(string n in new[]{"GetProjectileSource_FromThis","Kill"})Check("Projectile."+n,typeof(Projectile).GetMethod(n,F)!,false);
 Check("EntitySource_Parent.ctor",typeof(Terraria.DataStructures.EntitySource_Parent).GetConstructors(F).Single(),false);
 var times=new List<double>();for(int i=0;i<100;i++){var sw=Stopwatch.StartNew();new ClosedEffectSummary().Analyze(typeof(Entity).GetMethod("get_Center",F)!);times.Add(sw.Elapsed.TotalMilliseconds);}times.Sort();
 File.WriteAllText(args[0],JsonSerializer.Serialize(new{passed=count,rows,warmGetterSummaryMs=new{median=times[50],p95=times[95],max=times[^1]}},new JsonSerializerOptions{WriteIndented=true})); Console.WriteLine("TOTAL "+count);return 0;
 }
}
