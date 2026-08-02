#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Terraria;

namespace InfiniCrafterLocal.Common.Models;

public sealed partial class GeneratedItemData
{
    [JsonIgnore]
    public string? LastAppliedTrace { get; private set; }

    private string BuildAppliedTrace()
    {
        var parts = new List<string>
        {
            $"name={Name}", $"category={Category}", $"kind={Gameplay.Kind}",
            $"damageClass={Gameplay.DamageClass}", $"damage={Gameplay.Damage}",
            $"useTime={Gameplay.UseTime}", $"useAnimation={Gameplay.UseAnimation}",
            $"useStyle={RuntimeProgram.ItemUse.UseStyle}",
            $"runtimeEntities={RuntimeProgram.Entities.Length}",
            $"runtimeBindings={RuntimeProgram.Bindings.Length}",
            $"runtimeEvents={RuntimeProgram.Entities.Sum(entity => entity.Events.Length)}",
        };
        foreach (RuntimeEntitySpec entity in RuntimeProgram.Entities)
            parts.Add($"entity[{entity.Id}]={entity.Kind}/move:{entity.Movement.Name}/controller:{entity.Controller.Name}");
        return string.Join(" | ", parts);
    }

    internal void StampAppliedTrace() => LastAppliedTrace = BuildAppliedTrace();

    private void SetDebugJson(string key, object value)
    {
        if (string.IsNullOrWhiteSpace(key)) return;
        Debug ??= new Dictionary<string, JsonElement>();
        try { Debug[key] = JsonSerializer.SerializeToElement(value, Options); }
        catch (InvalidOperationException) { }
        catch (NotSupportedException) { }
        catch (ArgumentException) { }
    }

    private void RecordAppliedItemTrace(Item item, bool isArmor, bool isAccessory, bool actualAmmo)
    {
        SetDebugJson("appliedTrace", new
        {
            schema = "infini.applied-low-level-runtime-trace.v1",
            item = new
            {
                damage = item.damage, useTime = item.useTime, useAnimation = item.useAnimation,
                useStyle = item.useStyle, damageClass = Gameplay.DamageClass,
                shoot = item.shoot, shootSpeed = item.shootSpeed, knockback = item.knockBack,
                rare = item.rare, value = item.value, defense = item.defense,
                accessory = item.accessory, actualAmmo, noMelee = item.noMelee,
                noUseGraphic = item.noUseGraphic, channel = item.channel,
            },
            runtimeProgram = new
            {
                RuntimeProgram.ApiVersion, RuntimeProgram.Schema, RuntimeProgram.ItemEntityId,
                entities = RuntimeProgram.Entities.Select(entity => new
                {
                    entity.Id, entity.Kind, entity.VisualRole, entity.LifetimeTicks,
                    movement = new { entity.Movement.Name, entity.Movement.Code },
                    controller = new { entity.Controller.Name, entity.Controller.Code },
                    damage = new { entity.Damage.Enabled, entity.Damage.Damage, entity.Damage.DamageClass },
                    events = entity.Events.Select(action => new { action.Id, action.Event, action.Action, action.ActionCode, action.EntityId }),
                }).ToArray(),
                bindings = RuntimeProgram.Bindings.Select(binding => new
                {
                    binding.Id,
                    binding.Input,
                    binding.Role,
                    action = binding.UsePolicy.Action.Kind,
                    target = binding.UsePolicy.Action.TargetId,
                    binding.UsePolicy.StackCost,
                    binding.UsePolicy.ContactDamage,
                }).ToArray(),
            },
            equipment = new { armor = isArmor, accessory = isAccessory },
        });
        StampAppliedTrace();
    }
}
