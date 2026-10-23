#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.Audio;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.UI;

[Autoload(Side = ModSide.Client)]
public sealed class GeneratedChargeUISystem : ModSystem
{
    private readonly HashSet<object> _announced = new();
    private GeneratedChargeStatus[] _statuses = Array.Empty<GeneratedChargeStatus>();
    internal static GeneratedChargeStatus[] Dashboard(IEnumerable<GeneratedChargeStatus> statuses)
        => statuses.GroupBy(s => s.Source).Select(g => g.First()).OrderByDescending(s => s.Ready)
            .ThenByDescending(s => s.Progress).ThenBy(s => s.Name, StringComparer.Ordinal).ToArray();

    // Called from the update hook, never Draw. An observation cannot publish an
    // authored channel_complete event or change damage, release, or charge clocks.
    internal static bool ObserveReady(GeneratedChargeStatus status, HashSet<object> announced)
        => status.Ready && announced.Add(status.Source);

    private static bool Visible()
        => !Main.gameMenu && !Main.hideUI && !Main.ingameOptionsWindow && !Main.inFancyUI
            && !Main.mapFullscreen && !Main.playerInventory;

    public override void PostUpdateEverything()
    {
        _statuses = Array.Empty<GeneratedChargeStatus>();
        if (Main.dedServ || Main.netMode == NetmodeID.Server || Main.gameMenu
            || Main.LocalPlayer is not { active: true, dead: false } player)
        {
            _announced.Clear();
            return;
        }
        var live = new HashSet<object>();
        var observed = new List<GeneratedChargeStatus>();
        bool readySound = false;
        foreach (Projectile projectile in Main.ActiveProjectiles)
        {
            if (projectile.ModProjectile is not GeneratedProjectile generated
                || !generated.TryCaptureChargeStatus(player, out var status)) continue;
            live.Add(status.Source);
            // Consume even while hidden so reopening a menu cannot replay a cue.
            readySound |= ObserveReady(status, _announced);
            observed.Add(status);
        }
        _statuses = Dashboard(observed);
        _announced.RemoveWhere(source => !live.Contains(source));
        if (readySound && Visible() && (ModContent.GetInstance<Common.Config.InfiniGameplayQolConfig>()?.PlayChargeReadySound ?? true)) SoundEngine.PlaySound(SoundID.MaxMana, player.Center);
    }

    public override void OnWorldUnload() { _statuses = Array.Empty<GeneratedChargeStatus>(); _announced.Clear(); }

    public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
    {
        int index = layers.FindIndex(layer => layer.Name == "Vanilla: Mouse Text");
        if (index >= 0) layers.Insert(index, new LegacyGameInterfaceLayer(
            "InfiniCrafterLocal: Charge", DrawCharge, InterfaceScaleType.UI));
    }

    internal static Rectangle Bounds(int mouseX, int mouseY, int screenWidth, int screenHeight)
    {
        int width = Math.Max(1, Math.Min(112, screenWidth - 8));
        return new Rectangle(Math.Clamp(mouseX - width / 2, 0, Math.Max(0, screenWidth - width)),
            Math.Clamp(mouseY + 28, 0, Math.Max(0, screenHeight - 36)), width, 7);
    }

    private bool DrawCharge()
    {
        if (_statuses.Length == 0 || !Visible() || Main.LocalPlayer is not { active: true, dead: false }) return true;
        var config = ModContent.GetInstance<Common.Config.InfiniGameplayQolConfig>();
        int count = Math.Min(4, _statuses.Length);
        float scale = Math.Clamp(config?.ChargeHudScalePercent ?? 100, 75, 150) / 100f;
        int width = Math.Min(Math.Max(1, Main.screenWidth - 16), (int)(220 * scale));
        int rowHeight = (int)(43 * scale), height = rowHeight * count + (_statuses.Length > count ? 22 : 0);
        bool anchored = config?.AnchorChargeHud == true;
        int x = Math.Clamp(anchored ? Main.screenWidth - width - 18 : Main.mouseX - width / 2, 0, Math.Max(0, Main.screenWidth - width));
        int y = Math.Clamp(anchored ? Main.screenHeight - height - 70 : Main.mouseY + 28, 0, Math.Max(0, Main.screenHeight - height));
        var sb = Main.spriteBatch;
        for (int i = 0; i < count; i++)
        {
            var status = _statuses[i]; var box = new Rectangle(x, y + i * rowHeight, width, rowHeight - 3);
            sb.Draw(TextureAssets.MagicPixel.Value, box, new Color(12, 20, 29, 220));
            int fill = (int)MathF.Round((width - 4) * status.Progress);
            if (fill > 0) sb.Draw(TextureAssets.MagicPixel.Value, new Rectangle(x + 2, box.Bottom - 6, fill, 4), status.Ready ? Color.Gold : Color.Cyan);
            string name = GeneratedStatusTooltipView.LiteralName(status.Name);
            while (name.Length > 0 && FontAssets.MouseText.Value.MeasureString(name).X * .55f * scale > width - 12) name = name[..^1];
            Utils.DrawBorderString(sb, name, new Vector2(x + 6, box.Y + 2), Color.White, .55f * scale);
            string label = Language.GetTextValue("Mods.InfiniCrafterLocal.ChargeUI." + (status.Ready ? "Ready" : "Remaining"),
                (int)MathF.Floor(status.Progress * 100f), MathF.Ceiling(status.RemainingSeconds * 10) / 10);
            Utils.DrawBorderString(sb, label, new Vector2(x + 6, box.Y + 17 * scale), status.Ready ? Color.Gold : Color.White, .55f * scale);
        }
        if (_statuses.Length > count) Utils.DrawBorderString(sb,
            Language.GetTextValue("Mods.InfiniCrafterLocal.ChargeUI.More", _statuses.Length - count),
            new Vector2(x + 6, y + count * rowHeight), Color.White, .55f * scale);
        return true;
    }
}
