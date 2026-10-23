#nullable enable
using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
internal static partial class EngineRuntimeChecks
{
    private static void TargetManaRefusesAndRollsBackAtSpawnBoundary()
    {
        using var state = new SentryTargetScope(); state.Target(0, 80);
        state.Owner.statMana = 100; state.Owner.manaCost = 1;
        var data = SentryTargetingFixture(); var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Targeting.RequireLineOfSight = false; root.Targeting.ManaCost = 10;
        root.Targeting.ManaCostBasis = "shot"; root.Targeting.ManaReserve = 20;
        var projectile = new Projectile { owner = 0, active = true };
        var generated = Attach(projectile); var budget = new RuntimeSpawnBudget(12);
        generated.Configure(data, root, 0, 12, Vector2.UnitX, activationBudget: budget);
        projectile.Center = new Vector2(1600, 1600);
        int attempts = 0; bool throwAtBoundary = false;
        using var native = new Hook(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, owner, ai0, ai1, ai2) => {
                attempts++; Equal(60, state.Owner.statMana, "requested volley mana is reserved before native emission");
                if (throwAtBoundary) throw new InvalidOperationException("controlled native spawn refusal");
                return new Projectile(); // Unregistered native result is a refusal, never claimed success.
            }));
        var fire = typeof(GeneratedProjectile).GetMethod("ApplyTargetAndFire", SentryPrivate)!;
        var timer = typeof(GeneratedProjectile).GetField("_controllerTimer", SentryPrivate)!;
        void Volley() { timer.SetValue(generated, 5); fire.Invoke(generated, null); }
        Volley(); Equal(4, attempts, "admitted volley reaches actual native spawn boundary");
        Equal(100, state.Owner.statMana, "zero registered children refund all reserved mana");
        Equal(12, budget.Remaining, "refusal restores spawn reservation");
        throwAtBoundary = true;
        bool raised = false;
        try { Volley(); } catch (TargetInvocationException error) when (error.InnerException is InvalidOperationException) { raised = true; }
        Equal(true, raised, "native failure remains visible");
        Equal(100, state.Owner.statMana, "exception settles zero successful child mana");
        Equal(12, budget.Remaining, "exception does not double-return spawn capacity");
        int previous = attempts; root.Targeting.ManaReserve = 80;
        Volley(); Equal(previous, attempts, "protected reserve refuses before native spawn");
        Equal(100, state.Owner.statMana, "mana shortage preserves owner resources");
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
        root.Targeting.ManaReserve = 0; Volley();
        Equal(previous, attempts, "observer cannot pay or emit"); Equal(100, state.Owner.statMana, "observer cannot debit captured owner");
    }
}
