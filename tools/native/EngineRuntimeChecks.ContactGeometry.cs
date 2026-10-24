using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void CombatContactGeometry()
    {
        var entity = Entity(); entity.Kind = "free_projectile";
        entity.ContactGeometry = new() { Shape = "ellipse", LengthPx = 100, WidthPx = 20, Orientation = "fixed", AngleRadians = 0 };
        var p = new Projectile { damage = 100, Center = new Vector2(500, 500) };
        var host = Attach(p); host.Configure(new GeneratedItemData(), entity, 0, 8, Vector2.UnitX);
        Equal(true, host.Colliding(p.Hitbox, new Rectangle(545, 499, 6, 2)) == true, "ellipse end overlap");
        Equal(false, host.Colliding(p.Hitbox, new Rectangle(545, 508, 4, 2)) == true, "ellipse excludes rectangle corner");
        entity.ContactGeometry.Shape = "rectangle";
        Equal(true, host.Colliding(p.Hitbox, new Rectangle(545, 508, 4, 2)) == true, "rectangle includes corner");
        entity.ContactGeometry.AngleRadians = MathF.PI / 2;
        Equal(false, host.Colliding(p.Hitbox, new Rectangle(545, 499, 6, 2)) == true, "oriented narrow axis misses");
        Equal(true, host.Colliding(p.Hitbox, new Rectangle(499, 545, 2, 6)) == true, "oriented long axis hits");
        entity.ContactGeometry.Shape = "capsule"; entity.ContactGeometry.AngleRadians = 0;
        Equal(true, host.Colliding(p.Hitbox, new Rectangle(555, 499, 4, 2)) == true, "caps extend beyond central segment");
        Equal(false, host.Colliding(p.Hitbox, new Rectangle(558, 508, 2, 2)) == true, "caps round the corner");
        p.scale = 100;
        Equal(false, host.Colliding(p.Hitbox, new Rectangle(570, 499, 2, 2)) == true, "artwork never expands damage");
        entity.ContactGeometry.Orientation = "velocity"; p.velocity = Vector2.UnitY;
        Equal(true, host.Colliding(p.Hitbox, new Rectangle(499, 555, 2, 4)) == true, "velocity axis owns orientation");
    }
}
