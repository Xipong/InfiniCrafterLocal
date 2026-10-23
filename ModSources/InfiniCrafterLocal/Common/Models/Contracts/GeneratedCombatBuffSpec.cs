#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

public sealed record GeneratedCombatBuffSpec
{
    private static readonly string[] DamageClasses = { "generic", "melee", "ranged", "magic", "summon", "throwing" };
    [JsonRequired] public int DefensePoints { get; init; }
    [JsonRequired] public float AttackSpeedPercent { get; init; }
    [JsonRequired] public float CritChancePoints { get; init; }
    [JsonRequired] public float DamagePercent { get; init; }
    [JsonRequired] public string DamageClass { get; init; } = null!;
    [JsonIgnore] public bool HasEffect => DefensePoints != 0 || AttackSpeedPercent != 0 || CritChancePoints != 0 || DamagePercent != 0;

    internal static bool SameEffect(GeneratedCombatBuffSpec? left, GeneratedCombatBuffSpec? right)
        => (left?.DefensePoints ?? 0) == (right?.DefensePoints ?? 0)
            && (left?.AttackSpeedPercent ?? 0) == (right?.AttackSpeedPercent ?? 0)
            && (left?.CritChancePoints ?? 0) == (right?.CritChancePoints ?? 0)
            && (left?.DamagePercent ?? 0) == (right?.DamagePercent ?? 0)
            && ((left?.DamagePercent ?? 0) == 0 || left?.DamageClass == right?.DamageClass);

    public void Validate()
    {
        if (DefensePoints is < 0 or > 100 || !float.IsFinite(AttackSpeedPercent) || AttackSpeedPercent is < 0 or > 100
            || !float.IsFinite(CritChancePoints) || CritChancePoints is < 0 or > 100
            || !float.IsFinite(DamagePercent) || DamagePercent is < 0 or > 200
            || DamageClass is not ("generic" or "melee" or "ranged" or "magic" or "summon" or "throwing"))
            throw new InvalidDataException("combat buff fields must match the registered finite domains");
    }

    internal void Write(BinaryWriter writer)
    {
        Validate();
        writer.Write(DefensePoints); writer.Write(AttackSpeedPercent); writer.Write(CritChancePoints);
        writer.Write(DamagePercent); writer.Write((byte)Array.IndexOf(DamageClasses, DamageClass));
    }

    private static string ReadDamageClass(BinaryReader reader)
    {
        byte index = reader.ReadByte();
        if (index >= DamageClasses.Length) throw new InvalidDataException("unknown combat damage class");
        return DamageClasses[index];
    }

    internal static GeneratedCombatBuffSpec Read(BinaryReader reader)
    {
        var value = new GeneratedCombatBuffSpec { DefensePoints = reader.ReadInt32(), AttackSpeedPercent = reader.ReadSingle(),
            CritChancePoints = reader.ReadSingle(), DamagePercent = reader.ReadSingle(), DamageClass = ReadDamageClass(reader) };
        value.Validate(); return value;
    }
}
