#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using InfiniCrafterLocal.Common.Runtime;
internal static partial class EngineRuntimeChecks { private static void StationTargetMana() {
        TargetingDtoContract("{\"manaCost\":12,\"manaCostBasis\":\"shot\",\"manaReserve\":20,\"onManaShortage\":\"retire\"}", new[] { "{\"manaCost\":null}", "{\"manaCost\":-1}", "{\"manaCostBasis\":\"item\"}", "{\"manaReserve\":401}", "{\"onManaShortage\":\"guess\"}" }, "manaCost", "manaCostBasis", "manaReserve", "onManaShortage");
using var state = new SentryTargetScope();
        var owner = state.Owner; owner.statMana = 100; owner.manaCost = .75f;
        Equal(true, RuntimeVolleyManaPayment.TryReserve(owner, 10, true, 4, 20, out var payment), "reserve requested shot cost with native multiplier");
        Equal(70, owner.statMana, "full payment reserved before spawning");
        owner.manaCost = 0; payment!.Complete(2);
        Equal(85, owner.statMana, "partial spawn pays only two shots at captured multiplier");
        payment.Complete(0); Equal(85, owner.statMana, "settlement is idempotent");
        owner.manaCost = 1;
        Equal(true, RuntimeVolleyManaPayment.TryReserve(owner, 10, false, 4, 0, out payment), "volley payment");
        payment!.Complete(1); Equal(75, owner.statMana, "partial successful volley pays once");
        Equal(true, RuntimeVolleyManaPayment.TryReserve(owner, 10, true, 4, 0, out payment), "failed batch reservation");
        payment!.Complete(0); Equal(75, owner.statMana, "zero successful children restore full mana");
        Equal(false, RuntimeVolleyManaPayment.TryReserve(owner, 10, true, 4, 40, out payment), "reserve floor denies drain");
        Equal(75, owner.statMana, "refusal does not consume mana");
        var data = SentryTargetingFixture(); var root = data.RuntimeProgram.TryGetEntity("root")!;
        var projectile = new Projectile { owner = 0, active = true }; var generated = Attach(projectile);
        generated.Configure(data, root, 0, 12, Vector2.UnitX);
        Equal(true, generated.TryGetFiringOwner(out var captured) && ReferenceEquals(captured, owner), "exact configured owner admitted");
        projectile.owner = 1; Equal(false, generated.TryGetFiringOwner(out _), "changed native owner cannot charge old or replacement owner");
        projectile.owner = 0; Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
        Equal(false, generated.TryGetFiringOwner(out _), "reused player slot cannot inherit resource authority");
} }
