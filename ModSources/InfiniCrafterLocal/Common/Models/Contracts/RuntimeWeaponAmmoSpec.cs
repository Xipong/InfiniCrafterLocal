#nullable enable
using System.IO;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Explicit native ammo consumer for active authored root shots. Presence selects
/// native selection/conservation and native damage/knockback; projectile behavior
/// always remains the authored runtime entity. These are capability semantics,
/// not inferred choices or extra Author constants.
/// </summary>
public sealed class RuntimeWeaponAmmoSpec
{
    public string AmmoCategory { get; set; } = "";
    public string SpeedBasis { get; set; } = "";

    internal void NormalizeAndValidate()
    {
        if (TerrariaRuntimeVocabulary.ResolveAmmoCategory(AmmoCategory) == AmmoID.None)
            throw new InvalidDataException("weaponAmmo requires an exact nonempty native ammo category");
        if (SpeedBasis is not ("authored_spawn" or "native_shot"))
            throw new InvalidDataException("weaponAmmo requires explicit authored_spawn or native_shot speedBasis");
    }
}
