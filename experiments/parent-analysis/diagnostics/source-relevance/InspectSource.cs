using System; using System.Collections; using System.Collections.Generic; using System.IO; using System.Linq; using System.Reflection; using System.Runtime.Loader; using System.Text.Json;
class InspectSource {
 const BindingFlags B=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
 static object F(object x,string n)=>(x.GetType().GetField(n,B)?.GetValue(x) ?? x.GetType().GetProperty(n,B)?.GetValue(x))!;
 static object M(object x,string n, params object[] args)=>x.GetType().GetMethod(n,B)!.Invoke(x,args)!;
 static object Make(Type t,params object?[] args)=>Activator.CreateInstance(t,B,null,args,null)!;
 static IEnumerable<object> E(object x)=>((IEnumerable)x).Cast<object>();
 static object V(object x)=>new { id=F(x,"Id"),op=F(x,"Op"),operand=F(x,"Operand")?.ToString(),operandOwner=(F(x,"Operand") as MemberInfo)?.DeclaringType?.FullName,inputs=F(x,"Inputs"),at=F(x,"At"),block=F(x,"Block") };
 static void Main(string[] args){
  string dir=Path.GetFullPath(args[0]); AssemblyLoadContext.Default.Resolving+=(c,n)=>File.Exists(Path.Combine(dir,n.Name+".dll"))?c.LoadFromAssemblyPath(Path.Combine(dir,n.Name+".dll")):null;
  var asm=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(dir,"EngineRuntimeChecks.dll"));
  var native=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(dir,"tModLoader.dll"));
  var gc=asm.GetType("InfiniCrafterLocal.Common.Services.GeneratorClient")!;
  var cfg=gc.GetNestedType("ParentSourceMethod",B)!; var selector=gc.GetNestedType("AttackIdentitySelection",B)!;
  using var doc=JsonDocument.Parse(File.ReadAllText(args[1])); var p=doc.RootElement.GetProperty("itemA").GetProperty("directProjectileRaw").GetProperty("attackReference");
  string sourceMethod=p.GetProperty("motion").GetProperty("programs")[0].GetProperty("method").GetString()!;
  var method=native.GetType(sourceMethod[..sourceMethod.LastIndexOf('.')])!.GetMethod(sourceMethod[(sourceMethod.LastIndexOf('.')+1)..],B)!;
  int type=p.GetProperty("identityPredicates").GetProperty("Projectile.type").GetInt32(),style=p.GetProperty("identityPredicates").GetProperty("Projectile.aiStyle").GetInt32();
  var body=Make(cfg,method,null,null,null); var selection=Make(selector,body,type,style,true);
  var values=(IDictionary)F(body,"Values"); var blocks=(IDictionary)F(body,"Blocks"); var reachable=((IEnumerable<int>)F(selection,"Reachable")).ToHashSet();
  var all=values.Values.Cast<object>().ToArray();
  var hazards=all.Where(v=>(bool)M(selection,"IdentityHazard",v)).ToArray();
  var ilMethods=hazards.Where(v=>reachable.Contains((int)F(v,"Block"))).Select(v=>F(v,"Operand")).OfType<MethodBase>().Concat(all.Select(v=>F(v,"Operand")).OfType<MethodInfo>().Where(m=>m.Name=="NewProjectile")).Distinct().ToArray();
  var ilList=ilMethods.ToList(); var queue=new Queue<(MethodBase,int)>(ilMethods.Where(m=>m.Name=="GetProjectileSource_FromThis").Select(m=>(m,0))); while(queue.Count>0){ var (m,d)=queue.Dequeue(); if(d>=2)continue; foreach(var call in E(gc.GetMethod("AttackCode",B)!.Invoke(null,new object[]{m})!).Select(i=>F(i,"Arg")).OfType<MethodBase>().Where(c=>c.GetMethodBody()!=null)){ if(!ilList.Contains(call)){ilList.Add(call);queue.Enqueue((call,d+1));}}}
  var il=ilList.Select(m=>new {method=m.ToString(),owner=m.DeclaringType!.FullName,code=E(gc.GetMethod("AttackCode",B)!.Invoke(null,new object[]{m})!).Select(i=>new {at=F(i,"Offset"),op=F(i,"Op"),arg=F(i,"Arg")?.ToString(),argOwner=(F(i,"Arg") as MemberInfo)?.DeclaringType?.FullName})}).ToArray();
  var outdata=new {il,method=sourceMethod, nativeModule=method.Module.ModuleVersionId,identity=new{type,style},selected=F(selection,"Selected"),reachable, values=all.Select(V),statements=E(F(body,"Statements")).Select(v=>F(v,"Id")),blocks=blocks.Values.Cast<object>().Select(b=>new {start=F(b,"Start"),next=F(b,"Next")}),hazards=hazards.Select(v=>new{value=V(v),reachable=reachable.Contains((int)F(v,"Block"))}),receipt=F(selection,"Receipt").ToString()};
  File.WriteAllText(args[2],JsonSerializer.Serialize(outdata,new JsonSerializerOptions{WriteIndented=true}));
 }
}
