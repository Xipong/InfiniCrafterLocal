#nullable enable
using System.Linq;
using System.Text.Json.Serialization;
using Terraria;

namespace InfiniCrafterLocal.Common.Models;

public sealed partial class GeneratedItemData
{
    // Snapshot of the last successful projection of this definition, not a live
    // view of an Item after prefix/player/global hooks. Never part of the DTO.
    [JsonIgnore]
    public string? LastAppliedTrace { get; private set; }

    private void StampAppliedTrace(Item item)
    {
        // Read the final Item, not Gameplay: passive equipment and ammo can
        // intentionally project different fields. Do not write into Debug or
        // serialize the runtime graph on every application.
        LastAppliedTrace = string.Join(" | ", new[] {
            $"damage={item.damage}", $"damageClass={item.DamageType.Name}",
            $"useTime={item.useTime}", $"useAnimation={item.useAnimation}",
            $"useStyle={item.useStyle}", $"shoot={item.shoot}",
            $"shootSpeed={item.shootSpeed}", $"knockback={item.knockBack}",
            $"rare={item.rare}", $"value={item.value}", $"defense={item.defense}",
            $"accessory={item.accessory}", $"ammo={item.ammo}",
            $"noMelee={item.noMelee}", $"noUseGraphic={item.noUseGraphic}",
            $"channel={item.channel}", $"maxStack={item.maxStack}",
            $"runtimeEntities={RuntimeProgram.Entities.Length}",
            $"runtimeBindings={RuntimeProgram.Bindings.Length}",
            $"runtimeEvents={RuntimeProgram.Entities.Sum(entity => entity.Events.Length)}",
        });
    }
}
