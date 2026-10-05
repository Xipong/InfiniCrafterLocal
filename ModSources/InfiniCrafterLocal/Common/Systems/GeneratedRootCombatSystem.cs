#nullable enable
using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Mono.Cecil;
using Mono.Cecil.Cil;
using Mono.Cecil.Rocks;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ModLoader;
using Triple = InfiniCrafterLocal.Content.Items.GeneratedItem.RootCombatTriple;

namespace InfiniCrafterLocal.Common.Systems;

// Fix: exact authored binding target -> native combat context; no design choice.
// Supported native source: tML 2026.6.3.6, independently inspected ItemCheck_Inner
// early GetWeaponDamage, then native alternate selector/CanUse, then shoot stage.
public sealed class GeneratedRootCombatSystem : ModSystem
{
    private ILHook? _earlyHook;
    private Hook? _shootHook;
    [ThreadStatic] private static Frame _frame;
    [ThreadStatic] private static long _nextEpoch;
    [ThreadStatic] private static ShootScope? _shootScope;
    private const BindingFlags PrivateInstance = BindingFlags.Instance | BindingFlags.NonPublic;
    private static readonly Guid SupportedModule = new("2dc689ad-ceed-4fd9-848d-e10218d2e473");
    private readonly record struct Context(Triple Triple, int Prefix, int Type, int UseAmmo, int InputSelector)
    {
        internal static Context Capture(Player player, Item item) => new(Triple.Capture(item), item.prefix, item.type, item.useAmmo, player.altFunctionUse);
    }
    private readonly record struct EarlyDamage(Item Item, GeneratedItemData Data, Context Context, int Value, long Epoch);
    private readonly record struct Frame(Player? Player, long Epoch, EarlyDamage? Damage);

    public override void Load()
    {
        if (_earlyHook is not null || _shootHook is not null) throw Guard("already installed");
        RequireSupportedSource();
        MethodInfo inner = typeof(Player).GetMethod("ItemCheck_Inner", PrivateInstance, null, Type.EmptyTypes, null) ?? throw Guard("ItemCheck_Inner signature missing");
        MethodInfo shoot = typeof(Player).GetMethod("ItemCheck_Shoot", PrivateInstance, null, new[]{typeof(int),typeof(Item),typeof(int)}, null) ?? throw Guard("ItemCheck_Shoot signature missing");
        try {
            _earlyHook = new ILHook(inner, CaptureItemCheck);
            _shootHook = new Hook(shoot, (Action<Action<Player,int,Item,int>,Player,int,Item,int>)NativeShoot);
        }
        catch { Unload(); throw; }
    }

    public override void Unload()
    {
        _shootHook?.Dispose(); _shootHook = null;
        _earlyHook?.Dispose(); _earlyHook = null;
        while (_shootScope is not null) _shootScope.Dispose();
        _frame = default; _nextEpoch = 0;
    }

    internal static void RequireSupportedSource()
    {
        if (typeof(Player).Module.ModuleVersionId != SupportedModule || BuildInfo.tMLVersion != new Version(2026,6,3,6))
            throw Guard("unsupported native module/version; re-inspect source before enabling");
    }
    private static InvalidOperationException Guard(string reason)
        => new("Generated root combat native bridge: " + reason);
    private static Frame EnterFrame(Player player)
    {
        Frame previous = _frame;
        _frame = new Frame(player, ++_nextEpoch, null);
        return previous;
    }
    private static void ExitFrame(Frame previous) => _frame = previous;

    // Called only in place of the one inspected native callsite, not as a global
    // GetWeaponDamage detour and not from a held-item/tooltip semantic router.
    private static int CaptureEarlyDamage(Player player, Item item, bool forTooltip)
    {
        if (item.ModItem is not GeneratedItem generated) return player.GetWeaponDamage(item, forTooltip);
        Frame frame = _frame;
        Context context = Context.Capture(player,item);
        GeneratedItemData data = generated.Data;
        int value = player.GetWeaponDamage(item, forTooltip);
        // A hook that changes the query input cannot authorize reuse. Also fence
        // reentrant ItemCheck, definition replacement and actual post-query fields.
        if (!forTooltip && ReferenceEquals(frame.Player,player) && frame.Epoch == _frame.Epoch
            && ReferenceEquals(data,generated.Data) && context == Context.Capture(player,item))
            _frame = frame with { Damage = new EarlyDamage(item,data,context,value,frame.Epoch) };
        return value;
    }

    private static void CaptureItemCheck(ILContext il)
    {
        var body = il.Body;
        var calls = body.Instructions.Where(i => i.Operand is MethodReference).ToArray();
        var query = calls.Where(i => i.MatchCall<Player>(nameof(Player.GetWeaponDamage))).ToArray();
        var canUse = calls.Where(i => i.MatchCall<Player>("ItemCheck_CheckCanUse")).ToArray();
        var owner = calls.Where(i => i.MatchCall<Player>("ItemCheck_OwnerOnlyCode")).ToArray();
        if (body.ExceptionHandlers.Count != 0 || query.Length != 1 || canUse.Length != 1 || owner.Length != 1
            || query[0].Offset >= canUse[0].Offset || canUse[0].Offset >= owner[0].Offset
            || ((MethodReference)query[0].Operand).FullName != "System.Int32 Terraria.Player::GetWeaponDamage(Terraria.Item,System.Boolean)"
            || query[0].Previous.OpCode != OpCodes.Ldc_I4_0 || query[0].Next.OpCode != OpCodes.Stloc_S)
            throw Guard("early ItemCheck single-call/source shape mismatch");
        body.SimplifyMacros();
        var first = body.Instructions[0];
        var returns = body.Instructions.Where(i => i.OpCode == OpCodes.Ret).ToArray();
        if (returns.Length == 0) throw Guard("ItemCheck returns missing");
        query[0].OpCode = OpCodes.Call;
        query[0].Operand = il.Method.Module.ImportReference(typeof(GeneratedRootCombatSystem).GetMethod(nameof(CaptureEarlyDamage), BindingFlags.Static | BindingFlags.NonPublic)!);
        var previous = new VariableDefinition(il.Method.Module.ImportReference(typeof(Frame)));
        body.Variables.Add(previous); body.InitLocals = true;
        var cursor = new ILCursor(il);
        cursor.Goto(first);
        cursor.Emit(OpCodes.Ldarg_0); cursor.EmitDelegate<Func<Player,Frame>>(EnterFrame); cursor.Emit(OpCodes.Stloc,previous);
        var finalReturn = Instruction.Create(OpCodes.Ret);
        var finallyStart = Instruction.Create(OpCodes.Ldloc,previous);
        foreach (var ret in returns) { ret.OpCode = OpCodes.Leave; ret.Operand = finalReturn; }
        body.GetILProcessor().Append(finallyStart);
        cursor.Goto(finallyStart, MoveType.After);
        cursor.EmitDelegate<Action<Frame>>(ExitFrame);
        cursor.Emit(OpCodes.Endfinally);
        body.GetILProcessor().Append(finalReturn);
        body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Finally) {
            TryStart = first, TryEnd = finallyStart, HandlerStart = finallyStart, HandlerEnd = finalReturn,
        });
        // MonoMod owns ILLabel operands (including switch arrays). Cecil's
        // OptimizeMacros expects raw Instruction arrays and cannot size them.
    }

    private static void NativeShoot(Action<Player,int,Item,int> orig, Player player, int i, Item item, int weaponDamage)
    {
        if (item.ModItem is not GeneratedItem generated
            || !generated.TryGetSelectedRootCombat(player,out RuntimeEntitySpec? entity,out Triple root)) {
            orig(player,i,item,weaponDamage); return;
        }
        using var scope = new ShootScope(player,item,root);
        // Compare actual captured native query context, including Item reference,
        // current applied prefix, unchanged definition and this invocation epoch.
        // Authored equality alone, an old placement zero or overwritten damage
        // argument can never authorize the shortcut.
        EarlyDamage? early = _frame.Damage;
        bool reusable = early is EarlyDamage captured && ReferenceEquals(_frame.Player,player)
            && captured.Epoch == _frame.Epoch && ReferenceEquals(captured.Item,item)
            && ReferenceEquals(captured.Data,generated.Data) && captured.Context == Context.Capture(player,item)
            && captured.Value == weaponDamage;
        int damage = reusable ? weaponDamage : player.GetWeaponDamage(item);
        orig(player,i,item,entity!.Damage.Enabled ? damage : 0);
        // NativeShoot owns knockback/ModifyShootStats exactly once; never re-query
        // either damage or knockback in GeneratedItem.Shoot.
    }

    internal static Triple SourceContext(Item item)
    {
        for (ShootScope? scope=_shootScope; scope is not null; scope=scope.Previous)
            if (ReferenceEquals(scope.Item,item)) return scope.Source;
        return Triple.Capture(item);
    }
    internal static void RestoreSource(Player player, Item item)
    {
        if (_shootScope is ShootScope scope && ReferenceEquals(scope.Player,player) && ReferenceEquals(scope.Item,item))
            scope.Source.Apply(item);
    }

    private sealed class ShootScope : IDisposable
    {
        internal readonly Player Player;
        internal readonly Item Item;
        internal readonly Triple Source;
        private readonly Triple before;
        private readonly ShootScope? previous;
        internal ShootScope? Previous => previous;
        private bool disposed;
        internal ShootScope(Player player, Item item, Triple root)
        {
            Player = player; Item = item; before = Triple.Capture(item); previous = _shootScope;
            Source = before;
            for (ShootScope? scope=previous; scope is not null; scope=scope.previous)
                if (ReferenceEquals(scope.Item,item)) Source = scope.Source;
            _shootScope = this; root.Apply(item);
        }
        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            before.Apply(Item); _shootScope = previous;
        }
    }
}
