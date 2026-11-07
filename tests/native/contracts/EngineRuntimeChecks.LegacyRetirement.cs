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
        foreach (int code in System.Linq.Enumerable.Range(1, 20)) {
            var retired = new RuntimeMovementSpec { Code = code, Name = "move_straight" };
            bool refused = false;
            try { retired.NormalizeAndValidate(RuntimeEntityKind.FreeProjectile); }
            catch (InvalidDataException) { refused = true; }
            Equal(true, refused, "retired movement slot stays reserved " + code);
        }
        var current = new RuntimeMovementSpec { Code = 0, Name = "move_straight" };
        current.NormalizeAndValidate(RuntimeEntityKind.FreeProjectile);
        Equal(0, current.Code, "current straight opcode is not renumbered");
    }
}
