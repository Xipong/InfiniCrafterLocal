#nullable enable
using Microsoft.Xna.Framework;
using System.IO;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// Exact bounded color vocabulary shared by generated item lights and VFX.
/// Rich visual prose/palettes never enter this runtime selector.
/// </summary>
public static class RuntimeColorPolicy
{
    public static string NormalizeRequired(string? value, bool allowEmpty = false)
    {
        string token = (value ?? "").Trim().ToLowerInvariant();
        if (allowEmpty && token.Length == 0)
            return token;
        if (token is "white" or "red" or "orange" or "yellow" or "green" or "cyan" or
            "blue" or "purple" or "pink" or "gray" or "black")
            return token;
        throw new InvalidDataException($"unknown runtime color '{token}'");
    }

    private static string NormalizeForRendering(string? value)
    {
        string token = (value ?? "").Trim().ToLowerInvariant();
        return token is "white" or "gray" or "brown" or "tan" or "red" or "orange" or
            "yellow" or "gold" or "green" or "cyan" or "blue" or "purple" or "pink" or "black"
            ? token
            : "";
    }

    public static Color Resolve(string? value, Color fallback)
        => NormalizeForRendering(value) switch
        {
            "white" => new Color(235, 235, 235),
            "gray" => new Color(170, 170, 180),
            "brown" => new Color(150, 100, 65),
            "tan" => new Color(225, 190, 120),
            "red" => new Color(255, 85, 85),
            "orange" => new Color(255, 155, 70),
            "yellow" => new Color(255, 235, 90),
            "gold" => new Color(255, 205, 70),
            "green" => new Color(110, 255, 145),
            "cyan" => new Color(90, 235, 255),
            "blue" => new Color(120, 190, 255),
            "purple" => new Color(190, 110, 255),
            "pink" => new Color(255, 145, 215),
            "black" => new Color(25, 25, 30),
            _ => fallback,
        };
}
