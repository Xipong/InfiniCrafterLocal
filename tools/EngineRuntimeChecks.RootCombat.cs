using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private const BindingFlags RootPrivate = BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static;
    private static RootCombatProbeGlobal? _rootCombatGlobalInstance;
    private static GeneratedItem RootCombatHost(GeneratedItemData data)
    {
        var item = new Item(); item.SetDefaults(ItemID.CopperShortsword); item.stack = 1;
        if (_rootCombatGlobalInstance is not null) typeof(Item).GetField("_globals",RootPrivate)!.SetValue(item,new GlobalItem[]{_rootCombatGlobalInstance});
        var generated = new RootCombatProbeItem();
        typeof(ModType<Item>).GetProperty("Entity", RootPrivate)!.SetValue(generated, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
        generated.SetDefaults();
        Equal(data.Id, generated.Data.Id, "native fixture projection retains the supplied definition");
        return generated;
    }
    private static GeneratedItemData RootCombatFixture(int rootDamage, float rootKb, string rootClass, bool contact = false)
    {
        var data = RootSpawnFixture(0, 1);
        data.Gameplay.Damage = 13; data.Gameplay.Knockback = 2; data.Gameplay.DamageClass = "melee";
        data.Gameplay.UseStyleName = "hold_up"; data.Gameplay.UseStyle = ItemUseStyleID.HoldUp; data.Gameplay.UseTime = data.Gameplay.UseAnimation = 20;
        data.RuntimeProgram.ItemUse.UseStyle = "hold_up";
        var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Damage.Enabled = true; root.Damage.Damage = rootDamage; root.Damage.Knockback = rootKb; root.Damage.DamageClass = rootClass;
        data.RuntimeProgram.Bindings[0].UsePolicy.ContactDamage = contact;
        var alt = System.Text.Json.JsonSerializer.Deserialize<RuntimeEntitySpec>(
            System.Text.Json.JsonSerializer.Serialize(root))!;
        alt.Id = "alt";
        alt.Damage = new RuntimeDamageSpec { Enabled = true, Damage = 9, Knockback = 5, DamageClass = "magic" };
        data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(alt).ToArray();
        data.RuntimeProgram.Bindings = data.RuntimeProgram.Bindings.Append(new RuntimeBindingSpec {
            Id = "alternate", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Secondary,
            UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = contact, Action = new RuntimeBindingActionSpec {
                Kind = RuntimeBindingAction.SpawnEntity, TargetId = "alt" } } }).ToArray();
        data.Normalize(); // Fixture setup failure must not masquerade as a missing runtime target.
        return data;
    }
    // Public old APIs only: compile/run this exact file against baseline before integration.
    private static void GeneratedRootCombatNativeLanesAndQueryCounts()
    {
        using var scope = new SwarmRuntimeScope();
        using var roster = new RootCombatPlayerRoster(Terraria.Main.player[0]);
        var bridgeType = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedRootCombatSystem");
        var bridge = bridgeType is null ? null : (ModSystem)Activator.CreateInstance(bridgeType)!;
        bridge?.Load();
        var inner = typeof(Player).GetMethod("ItemCheck_Inner", RootPrivate)!;
        var shoot = typeof(Player).GetMethod("ItemCheck_Shoot", RootPrivate)!;
        var failures = new List<string>();
        try {
            foreach (var test in new (int Damage,float Kb,string Class,bool Contact,int Alt,int Animation,bool Stale,int Prefix,bool Disabled)[] { (37,4f,"magic",true,0,0,false,0,false),
                (13,2f,"melee",true,0,0,false,0,false), (37,4f,"magic",false,1,0,false,0,false),
                (37,4f,"magic",true,2,2,false,0,false), (37,4f,"magic",false,2,0,false,0,false),
                (13,2f,"melee",true,0,0,true,0,false), (0,4f,"magic",false,0,0,false,0,false),
                (37,4f,"magic",false,0,0,false,0,true),
                (37,4f,"magic",true,0,0,false,(int)PrefixID.Legendary,false),
                (37,4f,"magic",false,0,0,false,(int)PrefixID.Broken,false),
                (13,2f,"melee",true,0,0,false,(int)PrefixID.Zealous,false),
                (13,2f,"melee",true,1,0,false,0,false),
                (13,2f,"melee",false,2,0,false,0,false) }) {
                try {
                    RootCombatProbeItem.ExpectedItem = null;
                    var owner = Terraria.Main.player[0]; var generated = RootCombatHost(RootCombatFixture(test.Damage,test.Kb,test.Class,test.Contact));
                    bool selectorControl = test.Class == "melee" && test.Prefix == 0 && test.Alt != 0;
                    RootCombatProbePlayer.AlternateOnlyDamage = selectorControl;
                    if (selectorControl)
                    {
                        var alternate = generated.Data.RuntimeProgram.TryGetEntity("alt")!;
                        alternate.Damage.Damage = 13; alternate.Damage.Knockback = 2; alternate.Damage.DamageClass = "melee";
                    }
                    owner.GetDamage(DamageClass.Generic) = StatModifier.Default + 0.2f;
                    owner.GetDamage(DamageClass.Magic) = StatModifier.Default + 0.5f;
                    owner.GetKnockback(DamageClass.Magic) = StatModifier.Default + 0.3f;
                    ref float meleeCrit = ref owner.GetCritChance(DamageClass.Melee); meleeCrit = 11;
                    ref float magicCrit = ref owner.GetCritChance(DamageClass.Magic); magicCrit = 37;
                    ref float meleeArmor = ref owner.GetArmorPenetration(DamageClass.Melee); meleeArmor = 2;
                    ref float magicArmor = ref owner.GetArmorPenetration(DamageClass.Magic); magicArmor = 9;
                    owner.inventory[0] = generated.Item; owner.selectedItem = 0; owner.controlUseItem = owner.releaseUseItem = true;
                    owner.altFunctionUse = test.Alt; owner.itemAnimation = test.Animation; owner.itemTime = owner.reuseDelay = 0;
                    owner.position = new Vector2(400,400);
                    var entity = generated.Data.RuntimeProgram.TryGetEntity(test.Alt == 1 || test.Alt == 2 && test.Animation > 1 ? "alt" : "root")!;
                    entity.Damage.Enabled = !test.Disabled;
                    if(test.Prefix != 0) Equal(true,generated.Item.Prefix(test.Prefix),"prefix really accepted on body Item");
                    int bodyDamage=generated.Item.damage; float bodyKb=generated.Item.knockBack;
                    int bodyCrit=owner.GetWeaponCrit(generated.Item), bodyArmor=owner.GetWeaponArmorPenetration(generated.Item);
                    var control = RootCombatHost(generated.Data);
                    control.Item.damage = entity.Damage.Enabled ? entity.Damage.Damage : 0; control.Item.knockBack = entity.Damage.Knockback;
                    if(test.Prefix != 0) Equal(true,control.Item.Prefix(test.Prefix),"independent native prefix root-base oracle");
                    control.Item.DamageType = InfiniCrafterLocal.Common.Models.TerrariaRuntimeVocabulary.ResolveDamageClass(entity.Damage.DamageClass);
                    int selectedAlt = test.Alt == 1 || test.Alt == 2 && test.Animation > 1 ? 2 : 0;
                    int preSelector = owner.altFunctionUse;
                    owner.altFunctionUse = selectedAlt;
                    int expected = owner.GetWeaponDamage(control.Item); float expectedKb = owner.GetWeaponKnockback(control.Item,control.Item.knockBack);
                    owner.altFunctionUse = preSelector;
                    if(entity.Damage.Enabled && entity.Damage.Damage==0) Equal(true,expected>0,"enabled zero base retains real positive native Flat");
                    if (test.Stale) generated.Item.damage = 0;
                    bool sameContext=generated.Item.damage==control.Item.damage && generated.Item.knockBack==control.Item.knockBack && generated.Item.DamageType==control.Item.DamageType;
                    int early = 0, queries = 0, rootQueries = 0, late = 0, rootKbQueries = 0;
                    RootCombatProbeItem.ExpectedItem = generated.Item;
                    RootCombatProbeItem.Trace.Clear();
                    using var query = new Hook(typeof(Player).GetMethod(nameof(Player.GetWeaponDamage),new[]{typeof(Item),typeof(bool)})!,
                        (Func<Func<Player,Item,bool,int>,Player,Item,bool,int>)((orig,p,item,tip) => {
                            if (ReferenceEquals(item,generated.Item)) { queries++; if (item.damage == control.Item.damage && item.knockBack == control.Item.knockBack && item.DamageType == control.Item.DamageType && p.altFunctionUse == selectedAlt) rootQueries++; }
                            int value=orig(p,item,tip); if (queries==1 && ReferenceEquals(item,generated.Item)) early=value; return value;
                        }));
                    using var kbQuery = new Hook(typeof(Player).GetMethod(nameof(Player.GetWeaponKnockback),new[]{typeof(Item),typeof(float)})!,
                        (Func<Func<Player,Item,float,float>,Player,Item,float,float>)((orig,p,item,basis)=> {
                            if(ReferenceEquals(item,generated.Item)) {
                                rootKbQueries++; Equal(control.Item.knockBack,basis,"native root knockback base");
                                Equal(true,ReferenceEquals(control.Item.DamageType,item.DamageType),"native knockback exact root class");
                            }
                            return orig(p,item,basis);
                        }));
                    // Observe the real selector and CanUse call before avoiding later world consumers.
                    // The native Shoot method itself still executes, including its real late hooks.
                    using var stage = new ILHook(inner, il => {
                        var c=new ILCursor(il);
                        if (!c.TryGotoNext(MoveType.After, i=>i.MatchCall<Player>("ItemCheck_StartActualUse"))) throw new InvalidOperationException("native start/selector continuation missing");
                        // Source-pinned unconditional continuation after the native
                        // selector/CanUse/start block. Retarget its branch labels too:
                        // an active alternate skips CanUse, but still reaches here.
                        c.MoveAfterLabels();
                        c.Emit(OpCodes.Ldarg_0); c.Emit(OpCodes.Ldloc,il.Body.Variables[1]);
                        c.EmitDelegate<Action<Player,Item>>((p,item)=> {
                            Equal(true,p.itemAnimation>0,"native use or continuing animation accepted");
                            shoot.Invoke(p,new object[]{p.whoAmI,item,early});
                            throw new InvalidOperationException("root did not reach native spawn entry");
                        });
                    });
                    using var lateObserver = new ILHook(typeof(CombinedHooks).GetMethod(nameof(CombinedHooks.ModifyShootStats))!, il => {
                        var c=new ILCursor(il); c.Goto(il.Body.Instructions[0]);
                        c.Emit(OpCodes.Ldarg_1); c.EmitDelegate<Action<Item>>(item=> {
                            if (!ReferenceEquals(item,generated.Item)) return;
                            late++; Equal(control.Item.damage,item.damage,"late hook target damage context");
                            Equal(true,ReferenceEquals(control.Item.DamageType,item.DamageType),"late hook exact target class context");
                        });
                    });
                    using var spawn = RootCombatSpawnObserver((source,damage,kb)=> {
                        Equal(entity.Damage.Enabled ? expected+3+7 : 0,damage,"native full modifiers and final shoot modifier preserved");
                        Equal(expectedKb+0.5f+1.25f,kb,"native root knockback and late modifier preserved");
                        Equal(true,ReferenceEquals(generated.Item,((EntitySource_ItemUse)source).Item),"source exact Item identity");
                        Equal(true,ReferenceEquals(DamageClass.Melee,generated.Item.DamageType),"source restored before native inheritance");
                        Equal(true,ReferenceEquals(owner,((EntitySource_ItemUse)source).Player),"source actor identity retained");
                        var inherited=new Projectile(); inherited.ApplyStatsFromSource(source);
                        Equal(bodyCrit,inherited.CritChance,"scoped native shoot retains body/source crit");
                        Equal(bodyArmor,inherited.ArmorPenetration,"scoped native shoot retains body/source armor");
                        Equal(bodyDamage,inherited.originalDamage,"native originalDamage uses restored body/source");
                        Equal(generated.Item.crit,inherited.OriginalCritChance,"native original crit retains actual source Item");
                        Equal(generated.Item.ArmorPenetration,inherited.OriginalArmorPenetration,"native original armor retains actual source Item");
                    });
                    try { inner.Invoke(owner,null); throw new InvalidOperationException("native observer missed spawn"); }
                    catch(TargetInvocationException error) when (RootCombatBoundary(error)) { }
                    Equal(1,late,"one native late-hook traversal");
                    Equal(1,rootKbQueries,"one native root knockback evaluation");
                    Equal(sameContext && preSelector == selectedAlt ? 1 : 2,queries,"one query per distinct actual context including selector");
                    Equal(1,rootQueries,"identical root native damage query not repeated");
                    Equal(bodyDamage,generated.Item.damage,"body damage restored"); Equal(bodyKb,generated.Item.knockBack,"body knockback restored");
                    Equal(true,ReferenceEquals(DamageClass.Melee,generated.Item.DamageType),"body class restored after native exception");
                    Equal("item-damage,global-damage,player-damage",string.Join(",",RootCombatProbeItem.Trace.Take(3)),"native ItemLoader then PlayerLoader order");
                    if(bridgeType is not null) {
                        object frame=bridgeType.GetField("_frame",RootPrivate)!.GetValue(null)!;
                        Equal(true,frame.GetType().GetProperty("Player",RootPrivate)!.GetValue(frame) is null,"native exception retires local input epoch");
                        Equal(true,bridgeType.GetField("_shootScope",RootPrivate)!.GetValue(null) is null,"native exception retires root scope");
                    }
                } catch(Exception error) { failures.Add(test+": "+error); }
            }
            if(bridge is not null) {
                bridge.Unload();
                using (var mutant=new ILHook(inner,il=> {
                    var c=new ILCursor(il);
                    if(!c.TryGotoNext(MoveType.Before,i=>i.MatchCall<Player>(nameof(Player.GetWeaponDamage)))) throw new InvalidOperationException("guard mutation site missing");
                    c.Prev.OpCode=OpCodes.Ldc_I4_1; // native forTooltip=false source pin no longer matches
                })) {
                    bool refused=false;
                    try { bridge.Load(); } catch(Exception error) { refused=error.ToString().Contains("single-call/source shape mismatch",StringComparison.Ordinal); }
                    Equal(true,refused,"real IL source mutation fails clear, never installs fallback");
                }
                bridge.Load(); // valid native pattern still installs after scoped mutant retirement
            }
        } finally { bridge?.Unload(); RootCombatProbeItem.ExpectedItem=null; RootCombatProbePlayer.AlternateOnlyDamage=false; }
        if(failures.Count!=0) throw new InvalidOperationException(string.Join(Environment.NewLine,failures));
    }
    private static void GeneratedRootCombatTerminalHoldAndSourceFence()
    {
        using var scope=new SwarmRuntimeScope(); using var roster=new RootCombatPlayerRoster(Terraria.Main.player[0]);
        var owner=Terraria.Main.player[0]; var generated=RootCombatHost(RootCombatFixture(37,4,"magic",true));
        owner.inventory[0]=generated.Item; owner.selectedItem=0; owner.controlUseItem=owner.channel=false;
        int sourceCrit=owner.GetWeaponCrit(generated.Item), sourceArmor=owner.GetWeaponArmorPenetration(generated.Item);
        var source=new EntitySource_ItemUse_WithAmmo(owner,generated.Item,ItemID.MusketBall,"root-native-source");
        using var spawn=RootCombatSpawnObserver((actual,damage,kb)=> {
            Equal(true,ReferenceEquals(source,actual),"terminal source object preserved");
            Equal(12345,damage,"literal final native damage forwarded without declared-max clamp"); Equal(7.75f,kb,"literal final native knockback forwarded");
            var inherited=new Projectile(); inherited.ApplyStatsFromSource(actual);
            Equal(sourceCrit,inherited.CritChance,"native source crit unchanged"); Equal(sourceArmor,inherited.ArmorPenetration,"native source armor unchanged");
            Equal(ItemID.MusketBall,((EntitySource_ItemUse_WithAmmo)actual).AmmoItemIdUsed,"ammo metadata retained");
            Equal("root-native-source",actual.Context!,"native Context retained");
        });
        try { generated.Shoot(owner,source,owner.Center,Vector2.UnitX,0,12345,7.75f); throw new InvalidOperationException("terminal spawn entry missed"); }
        catch(RootCombatSpawnBoundary) { }
        spawn.Dispose();
        var root=generated.Data.RuntimeProgram.TryGetEntity("root")!;
        var control=RootCombatHost(generated.Data); control.Item.damage=37; control.Item.knockBack=4; control.Item.DamageType=DamageClass.Magic;
        int expected=owner.GetWeaponDamage(control.Item); float expectedKb=owner.GetWeaponKnockback(control.Item,4);
        int queries=0;
        using var query=new Hook(typeof(Player).GetMethod(nameof(Player.GetWeaponDamage),new[]{typeof(Item),typeof(bool)})!,
            (Func<Func<Player,Item,bool,int>,Player,Item,bool,int>)((orig,p,item,tip)=> { if(ReferenceEquals(item,generated.Item)) queries++; return orig(p,item,tip); }));
        using var holdSpawn=RootCombatSpawnObserver((actual,damage,kb)=> { Equal(expected,damage,"hold uses exact independent target"); Equal(expectedKb,kb,"hold native knockback"); });
        try { generated.HoldItem(owner); throw new InvalidOperationException("accepted idle hold missed"); } catch(RootCombatSpawnBoundary) { }
        Equal(1,queries,"one query only at missing hold root spawn");
        SwarmHost(generated.Data,root,slot:0,damage:37,knockback:4);
        generated.HoldItem(owner); Equal(1,queries,"existing hold root performs no stat query");
        Equal(13,generated.Item.damage,"hold restores source damage"); Equal(true,ReferenceEquals(DamageClass.Melee,generated.Item.DamageType),"hold restores source class");
        Terraria.Main.projectile[0].active=false;
        for(int i=0;i<InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner;i++)
            SwarmHost(generated.Data,generated.Data.RuntimeProgram.TryGetEntity("alt")!,slot:i);
        generated.HoldItem(owner); Equal(1,queries,"owner cap refuses hold before native stat queries");
        foreach(var projectile in Terraria.Main.projectile) projectile.active=false;
        holdSpawn.Dispose();
        var prefixed=RootCombatHost(RootCombatFixture(37,4,"magic"));
        owner.inventory[0]=prefixed.Item;
        Equal(true,prefixed.Item.Prefix(PrefixID.Legendary),"real accepted prefix before placement/hold");
        var placing=new RuntimeBindingSpec { Id="place",Input=RuntimeInputKind.AlternateUse,Role=RuntimeEntityRole.Secondary,
            UsePolicy=new RuntimeBindingUsePolicySpec { StackCost=1,Action=new RuntimeBindingActionSpec {
                Kind=RuntimeBindingAction.PlaceItem,TargetId=prefixed.Data.RuntimeProgram.ItemEntityId,
                Placement=new RuntimePlacementSpec { TileId=-1,WallId=1,PlaceStyle=0 } } } };
        typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection",RootPrivate)!.Invoke(prefixed,new object[]{placing});
        Equal(0,prefixed.Item.damage,"native placement projection zero retained outside hold query");
        var prefixControl=RootCombatHost(prefixed.Data); prefixControl.Item.damage=37; prefixControl.Item.knockBack=4;
        Equal(true,prefixControl.Item.Prefix(PrefixID.Legendary),"native prefix hold-base oracle"); prefixControl.Item.DamageType=DamageClass.Magic;
        int prefixExpected=owner.GetWeaponDamage(prefixControl.Item); float prefixKb=owner.GetWeaponKnockback(prefixControl.Item,prefixControl.Item.knockBack);
        var snapshotField=typeof(GeneratedItem).GetField("_nativePrefixBase",RootPrivate); object? snapshot=snapshotField?.GetValue(prefixed);
        using var prefixHoldSpawn=RootCombatSpawnObserver((actual,damage,kb)=> { Equal(prefixExpected,damage,"accepted placement-prefix does not disable idle hold"); Equal(prefixKb,kb,"hold retains native prefix knockback"); });
        try { prefixed.HoldItem(owner); throw new InvalidOperationException("prefixed placement/idle hold missed"); } catch(RootCombatSpawnBoundary) { }
        Equal(0,prefixed.Item.damage,"hold restores exact placement source zero");
        Equal(true,Equals(snapshot,snapshotField?.GetValue(prefixed)),"hold never mutates prefix owner's native base snapshot");
        prefixHoldSpawn.Dispose();
        var lowData=RootCombatFixture(37,4,"magic"); lowData.Gameplay.Damage=2;
        var low=RootCombatHost(lowData); owner.inventory[0]=low.Item;
        Equal(true,low.Item.Prefix(PrefixID.Broken),"native Broken accepts original base damage two");
        Equal(1,low.Item.damage,"native positive low-base prefix control");
        var lowControl=RootCombatHost(lowData); lowControl.Item.damage=37; lowControl.Item.knockBack=4;
        Equal(true,lowControl.Item.Prefix(PrefixID.Broken),"native low-base root prefix oracle");
        lowControl.Item.DamageType=DamageClass.Magic;
        int lowExpected=owner.GetWeaponDamage(lowControl.Item); float lowKb=owner.GetWeaponKnockback(lowControl.Item,lowControl.Item.knockBack);
        using var lowSpawn=RootCombatSpawnObserver((actual,damage,kb)=> { Equal(lowExpected,damage,"already accepted low-base prefix reaches hold root"); Equal(lowKb,kb,"low-base prefix retains native knockback"); });
        try { low.HoldItem(owner); throw new InvalidOperationException("low-base prefixed hold missed"); } catch(RootCombatSpawnBoundary) { }
        Equal(1,low.Item.damage,"low-base body stats restored after native query");
        Equal((int)PrefixID.Broken,low.Item.prefix,"low-base accepted token retained");
    }
    private static Hook RootCombatSpawnObserver(Action<IEntitySource,int,float> observe)
        => new Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect),new[]{typeof(IEntitySource),typeof(Vector2),typeof(Vector2),typeof(int),typeof(int),typeof(float),typeof(int),typeof(float),typeof(float),typeof(float)})!,
            (Func<IEntitySource,Vector2,Vector2,int,int,float,int,float,float,float,Projectile>)((source,pos,velocity,type,damage,kb,owner,a,b,c)=> { observe(source,damage,kb); throw new RootCombatSpawnBoundary(); }));
    private sealed class RootCombatSpawnBoundary : Exception { }
    private static bool RootCombatBoundary(Exception error)=>error is RootCombatSpawnBoundary || error.InnerException is not null && RootCombatBoundary(error.InnerException);
    private sealed class RootCombatProbeItem : GeneratedItem
    {
        internal static Item? ExpectedItem;
        internal static readonly List<string> Trace=new();
        public override void ModifyWeaponDamage(Player player,ref StatModifier damage) { if(ExpectedItem is not null) Equal(true,ReferenceEquals(ExpectedItem,Item),"ModItem exact instance"); Trace.Add("item-damage"); damage.Flat+=2.5f; damage.Base+=1.25f; damage*=1.1f; }
        public override void ModifyWeaponKnockback(Player player,ref StatModifier kb) { kb.Flat+=0.25f; kb.Base+=0.5f; kb*=1.1f; }
    }
    private sealed class RootCombatProbePlayer : ModPlayer
    {
        internal static bool AlternateOnlyDamage;
        public override void ModifyWeaponDamage(Item item,ref StatModifier damage) { if(RootCombatProbeItem.ExpectedItem is not null) Equal(true,ReferenceEquals(RootCombatProbeItem.ExpectedItem,item),"ModPlayer exact item"); RootCombatProbeItem.Trace.Add("player-damage"); damage+=0.15f; damage.Flat+=0.75f; if(AlternateOnlyDamage && Player.altFunctionUse==2) damage.Flat+=100; }
        public override void ModifyWeaponKnockback(Item item,ref StatModifier kb) { kb+=0.2f; }
        public override void ModifyShootStats(Item item,ref Vector2 position,ref Vector2 velocity,ref int type,ref int damage,ref float kb) { damage+=7; kb+=1.25f; }
    }
    private sealed class RootCombatProbeGlobal : GlobalItem
    {
        public override bool InstancePerEntity => true;
        private void InstanceFence(Item item)
        {
            Equal(true,ReferenceEquals(this,_rootCombatGlobalInstance),"actual per-Item GlobalItem, not its template");
            if(RootCombatProbeItem.ExpectedItem is not null) Equal(true,ReferenceEquals(RootCombatProbeItem.ExpectedItem,item),"GlobalItem exact Item identity");
        }
        public override void ModifyWeaponDamage(Item item,Player player,ref StatModifier damage) { InstanceFence(item); RootCombatProbeItem.Trace.Add("global-damage"); damage.Base+=0.5f; damage*=1.05f; }
        public override void ModifyWeaponKnockback(Item item,Player player,ref StatModifier kb) { InstanceFence(item); kb.Flat+=0.125f; }
        public override void ModifyShootStats(Item item,Player player,ref Vector2 position,ref Vector2 velocity,ref int type,ref int damage,ref float kb) { InstanceFence(item); RootCombatProbeItem.Trace.Add("global-shoot"); damage+=3; kb+=0.5f; }
    }
    private sealed class RootCombatPlayerRoster : IDisposable
    {
        private readonly List<(FieldInfo Field,object? Value)> saved=new(); private readonly Player player; private readonly object? oldPlayers;
        private readonly RootCombatProbeGlobal? oldGlobalInstance=_rootCombatGlobalInstance;
        internal RootCombatPlayerRoster(Player p) {
            player=p; var field=typeof(Player).GetField("modPlayers",RootPrivate)!; oldPlayers=field.GetValue(p);
            try {
            var probe=new RootCombatProbePlayer(); typeof(ModType<Player>).GetProperty("Entity",RootPrivate)!.SetValue(probe,p); field.SetValue(p,new ModPlayer[]{probe});
            var template=new RootCombatProbeGlobal(); _rootCombatGlobalInstance=new RootCombatProbeGlobal();
            foreach(var global in new[]{template,_rootCombatGlobalInstance}) typeof(GlobalType<GlobalItem>).GetProperty("PerEntityIndex",RootPrivate)!.SetValue(global,(short)0);
            foreach(string name in new[]{"HookModifyWeaponDamage","HookModifyWeaponKnockback","HookModifyShootStats"}) {
                var globalField=typeof(ItemLoader).GetField(name,RootPrivate)!; saved.Add((globalField,globalField.GetValue(null)));
                var globalType=globalField.FieldType;
                // Clone the already-native typed hook descriptor; its MethodInfo
                // constructor cannot construct a generic delegate with ref parameters.
                var globalHook=typeof(object).GetMethod("MemberwiseClone",RootPrivate)!
                    .Invoke(globalField.GetValue(null)!,null)!;
                globalType.GetField("hookGlobals",RootPrivate)!.SetValue(globalHook,new GlobalItem[]{template});
                var byType=Enumerable.Range(0,ItemID.Count).Select(_=>new GlobalItem[]{template}).ToArray();
                globalType.GetField("hookGlobalsByType",RootPrivate)!.SetValue(globalHook,byType);
                globalField.SetValue(null,globalHook);
                var hookField=typeof(PlayerLoader).GetField(name,RootPrivate)!; saved.Add((hookField,hookField.GetValue(null)));
                var hookType=hookField.FieldType; var method=typeof(ModPlayer).GetMethod(name.Substring(4))!;
                var old=hookField.GetValue(null)!;
                // Preserve the real override-query delegate; give the new HookList an isolated roster.
                var query=hookType.GetProperty("HookOverrideQuery",RootPrivate)!.GetValue(old);
                var ctor=hookType.GetConstructors(RootPrivate).Single(c=>c.GetParameters().Length==1 && c.GetParameters()[0].ParameterType.IsInstanceOfType(query));
                var hook=ctor.Invoke(new[]{query}); hookType.GetMethod("Update")!.Invoke(hook,new object[]{new ModPlayer[]{probe}}); hookField.SetValue(null,hook);
            }
            } catch { Dispose(); throw; }
        }
        public void Dispose() { foreach(var row in saved) row.Field.SetValue(null,row.Value); typeof(Player).GetField("modPlayers",RootPrivate)!.SetValue(player,oldPlayers); _rootCombatGlobalInstance=oldGlobalInstance; }
    }
}
