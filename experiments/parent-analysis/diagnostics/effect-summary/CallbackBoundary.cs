using System; using System.Linq; using System.Reflection; using System.Collections; using System.Collections.Generic; using System.IO; using InfiniCrafterLocal.Common.Services; using Terraria;
class CallbackBoundary {
 const BindingFlags F=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static|BindingFlags.Instance;
 static object V(object o,string f)=>o.GetType().GetField(f,F)?.GetValue(o) ?? o.GetType().GetProperty(f,F)?.GetValue(o)!;
 static object Call(object o,string m,params object[] a)=>o.GetType().GetMethod(m,F)!.Invoke(o,a)!;
 static string Input(IDictionary vals,string id,int depth=0){if(depth>8)return "...";var v=vals[id]!;return $"{id}:{V(v,"Op")}({V(v,"Operand")})["+string.Join(",",((IEnumerable)V(v,"Inputs")).Cast<string>().Select(s=>Input(vals,s,depth+1)))+"]";}
 static void Main(string[] args){
 var gc=typeof(GeneratorClient);
 foreach(var method in typeof(Projectile).GetMethods(F).Where(m=>m.Name=="Kill" || m.Name=="NewProjectile")){
 Console.WriteLine("METHOD "+method+" owner="+method.DeclaringType+" bytes="+method.GetMethodBody()?.GetILAsByteArray()?.Length);
 var code=(IEnumerable)gc.GetMethod("AttackCode",F)!.Invoke(null,new object[]{method})!;
 foreach(var i in code.Cast<object>()) if(V(i,"Arg") is MethodBase callee && (callee.Name.Contains("Kill") || callee.Name.Contains("Spawn"))) Console.WriteLine($"{V(i,"Offset")} {V(i,"Op")} {callee.DeclaringType}.{callee}");
 }
 }
}
