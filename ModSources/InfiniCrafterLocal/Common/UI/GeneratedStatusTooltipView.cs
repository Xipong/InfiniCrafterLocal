#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.UI;

// Display-only copies: never edit source definitions, aggregate entries or clocks.
internal static class GeneratedStatusTooltipView
{
    // A display-only bound in Unicode scalars. Names cannot inject Terraria chat
    // markup, control characters or a second status label; owner prose is untouched.
    internal static string LiteralName(string value)
    {
        var result = new StringBuilder(96);
        int count = 0;
        foreach (Rune rune in (value ?? "").EnumerateRunes())
        {
            UnicodeCategory category = Rune.GetUnicodeCategory(rune);
            if (rune.Value is '[' or ']' || category is UnicodeCategory.Control
                or UnicodeCategory.Format or UnicodeCategory.LineSeparator or UnicodeCategory.ParagraphSeparator)
                continue;
            if (count++ >= 96) break;
            result.Append(rune.ToString());
        }
        return result.ToString();
    }

    internal static string CountdownSeconds(int ticks, CultureInfo culture)
        // Ceiling prevents an active last tick from reading "0 s". Use long to
        // avoid overflow even for a malformed diagnostic input, without clamping it.
        => (Math.Max(0L, ticks) / 60 + (ticks > 0 && ticks % 60 != 0 ? 1 : 0)).ToString(culture);

    internal static string Number(double value, CultureInfo culture)
        // Three fractional places remove float32 display noise. Small nonzero
        // authored contributions keep significant digits instead of becoming "0".
        => value.ToString(value != 0d && Math.Abs(value) < .001d ? "G3" : "0.###", culture);

    internal static string Wrap(string label, string tooltip, int screenWidth, int screenHeight,
        Func<string, Vector2> measure)
    {
        // InterfaceScaleType.UI has already applied PlayerInput.SetZoom_UI to
        // Main.screenWidth/Height. Dividing by UIScale again would shrink twice.
        float width = Math.Max(1, Math.Min(480, screenWidth - 48));
        float height = Math.Max(1, screenHeight - 48);
        var rows = new List<string>(GeneratedItem.WrapRuntimeTooltipLines(
            label + "\n" + tooltip, width, text => measure(text).X));
        string text = string.Join("\n", rows);
        if (measure(text).Y <= height) return text;
        // A pathological 32-entry contribution table can exceed even a wrapped
        // viewport. Bound only this display copy and disclose omitted tail rows.
        // Owner snapshots and per-entry exact durations remain complete.
        while (rows.Count > 0)
        {
            rows.RemoveAt(rows.Count - 1);
            text = string.Join("\n", rows) + (rows.Count > 0 ? "\n…" : "…");
            if (measure(text).Y <= height) break;
        }
        return text;
    }
}
