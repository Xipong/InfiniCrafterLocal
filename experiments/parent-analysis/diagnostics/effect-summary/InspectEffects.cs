using System; using System.Linq; using System.Reflection; using System.Collections; using System.Collections.Generic; using System.IO; using InfiniCrafterLocal.Common.Services; using Terraria;
class InspectEffects {
 const BindingFlags F=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static|BindingFlags.Instance;
 static object V(object o,string f)=>o.GetType().GetField(f,F)!.GetValue(o)!;
 static object Call(object o,string m,params object[] a)=>o.GetType().GetMethod(m,F)!.Invoke(o,a)!;
 static string Input(IDictionary vals,string id,int depth=0){if(depth>8)return "...";var v=vals[id]!;return $"{id}:{V(v,"Op")}({V(v,"Operand")})["+string.Join(",",((IEnumerable)V(v,"Inputs")).Cast<string>().Select(s=>Input(vals,s,depth+1)))+"]";}
 static void Main(string[] args){
 var gc=typeof(GeneratorClient); var method=typeof(Projectile).GetMethod("AI_075",F)!;
 var code=gc.GetMethod("AttackCode",F)!.Invoke(null,new object[]{method});
 var body=Activator.CreateInstance(gc.GetNestedType("ParentSourceMethod",F)!,F,null,new object?[]{method,code,null,null},null)!;
 var sel=Activator.CreateInstance(gc.GetNestedType("AttackIdentitySelection",F)!,F,null,new object[]{body,633,75,true},null)!;
 var reachable=((IEnumerable)V(sel,"Reachable")).Cast<int>().ToHashSet(); var values=(IDictionary)V(body,"Values");
 Console.WriteLine("RECEIPT "+V(sel,"Receipt"));
 foreach(var h in ((IEnumerable)V(sel,"hazards")).Cast<object>().Where(h=>reachable.Contains((int)V(h,"Block"))))Console.WriteLine("HAZARD "+Input(values,(string)V(h,"Id")));
 foreach(DictionaryEntry entry in values){var v=entry.Value!;if(V(v,"Operand") is FieldInfo fi && fi.DeclaringType==typeof(Projectile) && (fi.Name=="type" || fi.Name=="aiStyle") && (string)V(v,"Op")=="ldfld" && reachable.Contains((int)V(v,"Block")))Console.WriteLine($"READ {V(v,"At")} {fi.Name} stable={Call(sel,"Unmodified",v)}");}
 }
}
