using System;
using System.Globalization;
using System.Reflection;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void QolHealingFeedback()
    {
        using var scope = new SwarmRuntimeScope();
        Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
        RuntimeHealingFeedback.Clear();
        var owner = Terraria.Main.player[0]; owner.statLifeMax2 = 100; owner.statLife = 97;
        var heal = typeof(RuntimeProgramExecutor).GetMethod("HealOwner", BindingFlags.Static | BindingFlags.NonPublic)!;
        var action = new RuntimeEventActionSpec { DamageFraction = .5f, MaxHeal = 20 };
        heal.Invoke(null, new object[] { action, owner, 100, "Source A" });
        Equal(100, owner.statLife, "native lifesteal clamps to missing health");
        var view = RuntimeHealingFeedback.Capture(owner, Terraria.Main.GameUpdateCount, CultureInfo.InvariantCulture)!;
        Equal(3, view.Applied, "feedback counts actual native health gain"); Equal(20, view.Requested, "authored cap remains visible");
        heal.Invoke(null, new object[] { action, owner, 100, "Source A" });
        view = RuntimeHealingFeedback.Capture(owner, Terraria.Main.GameUpdateCount, CultureInfo.InvariantCulture)!;
        Equal(3, view.Applied, "full health does not fabricate recovery"); Equal(40, view.Requested, "full-health excess remains inspectable");
        heal.Invoke(null, new object[] { action, owner, 0, "Source B" });
        Equal(40, RuntimeHealingFeedback.Capture(owner, Terraria.Main.GameUpdateCount, CultureInfo.InvariantCulture)!.Requested, "zero damage creates no proc");
        Equal(true, RuntimeHealingFeedback.Capture(owner, Terraria.Main.GameUpdateCount + 600, CultureInfo.InvariantCulture) is null, "receipt window follows native clock");
        Equal(100, owner.statLife, "reading history never heals or consumes life");
        RuntimeHealingFeedback.Clear();
    }
}
