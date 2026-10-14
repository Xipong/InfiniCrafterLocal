using System;
using System.IO;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void RetiredMovementSixIsReservedNotRenumbered()
    {
        foreach (string name in new[] { "move_bounce", "" })
        {
            var retired = new RuntimeMovementSpec { Code = 6, Name = name };
            bool refused = false;
            try { retired.NormalizeAndValidate(RuntimeEntityKind.FreeProjectile); }
            catch (InvalidDataException) { refused = true; }
            Equal(true, refused, "retired opcode six refused, including absent name");
        }
        foreach (var control in new[] { (5, "move_boomerang"), (7, "move_sine_homing"), (19, "move_forward_then_retract") })
        {
            var current = new RuntimeMovementSpec { Code = control.Item1, Name = control.Item2 };
            current.NormalizeAndValidate(control.Item1 == 19 ? RuntimeEntityKind.OwnerAttachedProjectile : RuntimeEntityKind.FreeProjectile);
            Equal(control.Item1, current.Code, "neighbor current opcode unchanged");
            Equal(control.Item2, current.Name, "neighbor current movement name unchanged");
        }
    }
}
