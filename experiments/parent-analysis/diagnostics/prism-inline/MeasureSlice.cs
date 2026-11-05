#nullable enable
using System; using System.IO; using System.Linq; using System.Reflection; using System.Diagnostics; using System.Collections; using System.Collections.Generic; using System.Text.Json; using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services; using Terraria;
class MeasureSlice {
const BindingFlags A=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
static object? F(object o,string n)=>o.GetType().GetField(n,A)?.GetValue(o)??o.GetType().GetProperty(n,A)?.GetValue(o);
static object? Run(string label,Func<object?> fn){long alloc=GC.GetTotalAllocatedBytes(true);var s=Stopwatch.StartNew();object? r=null;string? error=null;try{r=fn();}catch(Exception e){error=(e.InnerException??e).ToString();}s.Stop();Console.WriteLine(JsonSerializer.Serialize(new{label,ms=s.Elapsed.TotalMilliseconds,alloc=GC.GetTotalAllocatedBytes(true)-alloc,error}));return r;}
static IEnumerable<object> Items(object o)=>((IEnumerable)o).Cast<object>();
static void CheckSparse(object body,string label){
 var method=(MethodBase)F(body,"Method")!;
 var blocks=Items(F(body,"Blocks")!).Select(kv=>F(kv,"Value")!).Where(b=>(int)F(b,"Height")!>=0).ToArray();
 var entries=(HashSet<int>)F(body,"sliceEntries")!;
 var all=method.GetMethodBody()!.LocalVariables.Select(v=>v.LocalIndex).ToArray();
 var used=Items(F(body,"Code")!).Where(i=>(string)F(i,"Op")! is "ldloc" or "stloc" or "ldloca").Select(i=>(int)F(i,"Arg")!).Distinct().Order().ToArray();
 var incomingAll=blocks.ToDictionary(b=>(int)F(b,"Start")!,_=>new List<int>());
 foreach(var b in blocks)foreach(int n in (List<int>)F(b,"Next")!)if(incomingAll.ContainsKey(n))incomingAll[n].Add((int)F(b,"Start")!);
 Dictionary<int,HashSet<string>> Copy(Dictionary<int,HashSet<string>> d)=>d.ToDictionary(x=>x.Key,x=>new HashSet<string>(x.Value));
 bool Same(Dictionary<int,HashSet<string>> a,Dictionary<int,HashSet<string>> b)=>a.Count==b.Count&&a.All(p=>b.TryGetValue(p.Key,out var v)&&p.Value.SetEquals(v));
 foreach(var (variant,locals) in new[]{("dense",all),("sparse",used)})Run(label+"_locals_"+variant,()=>{
 var entry=locals.ToDictionary(x=>x,x=>new HashSet<string>{"local_entry:"+x});var ins=blocks.ToDictionary(b=>(int)F(b,"Start")!,_=>new Dictionary<int,HashSet<string>>());var outs=blocks.ToDictionary(b=>(int)F(b,"Start")!,_=>new Dictionary<int,HashSet<string>>());
 var stores=blocks.ToDictionary(b=>(int)F(b,"Start")!,b=>Items(F(b,"Code")!).Where(i=>(string)F(i,"Op")! =="stloc").Select(i=>(slot:(int)F(i,"Arg")!,at:(int)F(i,"Offset")!)).ToArray());
 bool changed=true;int passes=0;while(changed){if(++passes>512)throw new Exception("bound");changed=false;foreach(var b in blocks){int start=(int)F(b,"Start")!;var inc=entries.Contains(start)?Copy(entry):new Dictionary<int,HashSet<string>>();foreach(int pred in incomingAll[start])foreach(var pair in outs[pred]){if(!inc.TryGetValue(pair.Key,out var defs))inc[pair.Key]=defs=new HashSet<string>();defs.UnionWith(pair.Value);}var output=Copy(inc);foreach(var st in stores[start])output[st.slot]=new HashSet<string>{st.at.ToString()};changed|=!Same(output,outs[start]);ins[start]=inc;outs[start]=output;}}
 int assertions=0;foreach(var b in blocks){int start=(int)F(b,"Start")!;foreach(var (field,actual) in new[]{("Incoming",ins[start]),("Outgoing",outs[start])}){var expected=(Dictionary<int,HashSet<string>>)F(b,field)!;var projection=expected.Where(p=>locals.Contains(p.Key)).ToDictionary(p=>p.Key,p=>p.Value);if(!Same(projection,actual))throw new Exception("mismatch "+label+" "+variant+" "+start+" "+field);assertions++;}}
 Console.WriteLine(JsonSerializer.Serialize(new{label,variant,allLocals=all.Length,usedLocals=used.Length,blocks=blocks.Length,passes,assertions,storedCells=ins.Values.Sum(d=>d.Count)+outs.Values.Sum(d=>d.Count)}));return null;
 });
}
static void Main(string[] args){string outdir=args[0];int type=int.Parse(args[1]),style=int.Parse(args[2]);Directory.CreateDirectory(outdir);var g=typeof(GeneratorClient);var method=typeof(Projectile).GetMethod("VanillaAI",A)!;var code=(IList)Run("decode",()=>g.GetMethod("AttackCode",A)!.Invoke(null,new object[]{method}))!;
var il=Items(code).ToArray();int Off(object i)=>(int)F(i,"Offset")!;string Op(object i)=>(string)F(i,"Op")!;object? Arg(object i)=>F(i,"Arg");
var rows=il.Select(i=>new{at=Off(i),op=Op(i),arg=Arg(i) is MemberInfo m?(object)(m.DeclaringType?.FullName+"."+m.Name):Arg(i)}).ToArray();File.WriteAllText(outdir+"/VanillaAI.il.json",JsonSerializer.Serialize(rows));
var summaries=new Dictionary<string,object>();
foreach(var callee in il.Select(Arg).OfType<MethodBase>().Where(m=>m.DeclaringType==typeof(Projectile)||m.DeclaringType==typeof(Entity)).Distinct()){
 var key=callee.DeclaringType!.FullName+"."+callee.Name;
 if(callee.GetMethodBody() is not null && callee.GetMethodBody()!.GetILAsByteArray()!.Length<=2000){var ci=Items(g.GetMethod("AttackCode",A)!.Invoke(null,new object[]{callee})!).ToArray();summaries[key]=new{callee.IsVirtual,callee.IsStatic,code=ci.Select(i=>new{at=Off(i),op=Op(i),arg=Arg(i) is MemberInfo m?(object)(m.DeclaringType?.FullName+"."+m.Name):Arg(i)}).ToArray()};}
}
File.WriteAllText(outdir+"/callees.json",JsonSerializer.Serialize(summaries));
var next=il.Zip(il.Skip(1),(x,y)=>(a:Off(x),b:Off(y))).ToDictionary(x=>x.a,x=>x.b);
var windows=new List<object>(); var matches=new List<(int n,int start,int end)>();
for(int n=0;n+4<il.Length;n++){if(Op(il[n])!="ldarg"||!Equals(Arg(il[n]),0)||Op(il[n+1])!="ldfld"||Arg(il[n+1]) is not FieldInfo f||f.DeclaringType!=typeof(Projectile)||Op(il[n+2])!="const"||Arg(il[n+2]) is not int lit||!(f.Name=="type"&&lit==type||f.Name=="aiStyle"&&lit==style)||Op(il[n+3]) is not("bne.un" or "bne.un.s" or "beq" or "beq.s")||Arg(il[n+3]) is not int end)continue;int start=n+4;if(Op(il[n+3]).StartsWith("beq")){start=Array.FindIndex(il,i=>Off(i)==end);if(start<1||Op(il[start-1]) is not("bne.un" or "bne.un.s" or "br" or "br.s")||Arg(il[start-1]) is not int boundary||boundary<=end)continue;end=boundary;}
var win=il.Skip(n).Take(4).Concat(il.Skip(start).TakeWhile(i=>Off(i)<end)).ToArray();windows.Add(new{field=f.Name,literal=lit,guard=Off(il[n+3]),start=Off(il[start]),end,raw=win.Length,meaningful=win.Count(i=>Op(i)!="nop")});if(f.Name=="aiStyle")matches.Add((n,start,end));}
Console.WriteLine(JsonSerializer.Serialize(new{total=il.Length,windows}));File.WriteAllText(outdir+"/windows.json",JsonSerializer.Serialize(windows,new JsonSerializerOptions{WriteIndented=true}));
foreach(var w in matches){var slice=(IList)Activator.CreateInstance(code.GetType())!;foreach(var i in il.Skip(w.n).Take(4).Concat(il.Skip(w.start).TakeWhile(i=>Off(i)<w.end)))slice.Add(i);
var bt=g.GetNestedType("ParentSourceMethod",A)!;var it=g.GetNestedType("AttackIdentitySelection",A)!;var ot=g.GetNestedType("AttackSourceObservation",A)!;
var body=Run("body",()=>Activator.CreateInstance(bt,A,null,new object?[]{method,slice,next,null},null));if(body==null)continue;
var identity=Run("identity",()=>Activator.CreateInstance(it,A,null,new object?[]{body,type,style,true},null));if(identity==null)continue;
File.WriteAllText(outdir+"/identity.json",((JsonObject)F(identity,"Receipt")!).ToJsonString(new JsonSerializerOptions{WriteIndented=true}));
var sel=Run("selectedBody",()=>Activator.CreateInstance(bt,A,null,new object?[]{method,slice,next,F(identity,"Selected")},null));if(sel==null)continue;
CheckSparse(body,"raw");CheckSparse(sel,"selected");
Console.WriteLine(JsonSerializer.Serialize(new{selectedEdges=((IDictionary)F(identity,"Selected")!).Count,reachable=Items(F(identity,"Reachable")!).Count(),bodyStatements=Items(F(body,"Statements")!).Count(),selectedStatements=Items(F(sel,"Statements")!).Count(),bodyValues=((IDictionary)F(body,"Values")!).Count,selectedValues=((IDictionary)F(sel,"Values")!).Count,bodyBlocks=((IDictionary)F(body,"Blocks")!).Count,selectedBlocks=((IDictionary)F(sel,"Blocks")!).Count}));
var broad=Run("selected_effects",()=>{
 var prototype=Activator.CreateInstance(ot,A,null,new object?[]{sel,"dispatch",null,identity},null)!;
 var values=Items(F(sel,"Statements")!).Where(v=>{
 if((bool)ot.GetMethod("IsRoot",A)!.Invoke(prototype,new[]{v})!)return true;
 var operand=F(v,"Operand");var op=(string)F(v,"Op")!;
 return op=="stfld" && operand is FieldInfo f && (f.DeclaringType==typeof(Projectile)||f.DeclaringType==typeof(Entity))
 || operand is MethodInfo m && (m.IsSpecialName&&m.Name.StartsWith("set_")&&(m.DeclaringType==typeof(Projectile)||m.DeclaringType==typeof(Entity))||m.GetParameters().Any(p=>p.ParameterType.IsArray||p.ParameterType.IsByRef));
 }).ToArray();
 var array=Array.CreateInstance(g.GetNestedType("ParentSourceMethod",A)!.GetNestedType("Value",A)!,values.Length);for(int n=0;n<values.Length;n++)array.SetValue(values[n],n);
 var obs=Activator.CreateInstance(ot,A,null,new object?[]{sel,"dispatch",array,identity},null)!;return ot.GetMethod("Finish",A)!.Invoke(obs,null);
});if(broad is JsonObject bj){File.WriteAllText(outdir+"/selected_effects.json",bj.ToJsonString());Console.WriteLine(JsonSerializer.Serialize(new{label="selected_effects",chars=bj.ToJsonString().Length,observations=(bj["observations"] as JsonArray)?.Count,dependencies=(bj["dependencies"] as JsonObject)?.Count,predicates=(bj["predicates"] as JsonArray)?.Count}));}
foreach(var (name,b,id) in new[]{("raw",body,(object?)null),("selected",sel,identity)}){File.WriteAllText(outdir+"/"+name+".statements.json",JsonSerializer.Serialize(Items(F(b,"Statements")!).Select(v=>new{at=F(v,"At"),block=F(v,"Block"),op=F(v,"Op"),operand=F(v,"Operand") is MemberInfo m?m.DeclaringType?.FullName+"."+m.Name:F(v,"Operand"),inputs=F(v,"Inputs")})));foreach(string role in new[]{"dispatch","motion"}){var label=name+"_"+role;var r=Run(label,()=>{var o=Activator.CreateInstance(ot,A,null,new object?[]{b,role,null,id},null);return ot.GetMethod("Finish",A)!.Invoke(o,null);});if(r is JsonObject j){File.WriteAllText(outdir+"/"+label+".json",j.ToJsonString());Console.WriteLine(JsonSerializer.Serialize(new{label,chars=j.ToJsonString().Length,observations=(j["observations"] as JsonArray)?.Count,dependencies=(j["dependencies"] as JsonObject)?.Count,predicates=(j["predicates"] as JsonArray)?.Count,coverage=j["coverage"]?.ToString(),unresolved=j["unresolved"]?.ToString()}));}}}
}
}
}
