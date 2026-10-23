#nullable enable
using System;
using System.Collections.Generic;
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
    private GeneratedChargeStatus? _status;

    // Called from the update hook, never Draw. An observation cannot publish an
    // authored channel_complete event or change damage, release, or charge clocks.
    internal static bool ObserveReady(GeneratedChargeStatus status, HashSet<object> announced)
        => status.Ready && announced.Add(status.Source);

    private static bool Visible()
        => !Main.gameMenu && !Main.hideUI && !Main.ingameOptionsWindow && !Main.inFancyUI
            && !Main.mapFullscreen && !Main.playerInventory;

    public override void PostUpdateEverything()
    {
        _status = null;
        if (Main.dedServ || Main.netMode == NetmodeID.Server || Main.gameMenu
            || Main.LocalPlayer is not { active: true, dead: false } player)
        {
            _announced.Clear();
            return;
        }
        var live = new HashSet<object>();
        bool readySound = false;
        foreach (Projectile projectile in Main.ActiveProjectiles)
        {
            if (projectile.ModProjectile is not GeneratedProjectile generated
                || !generated.TryCaptureChargeStatus(player, out var status)) continue;
            live.Add(status.Source);
            // Consume even while hidden so reopening a menu cannot replay a cue.
            readySound |= ObserveReady(status, _announced);
            if (_status is not { } current || status.Progress > current.Progress)
                _status = status;
        }
        _announced.RemoveWhere(source => !live.Contains(source));
        if (readySound && Visible() && ModContent.GetInstance<Common.Config.InfiniGameplayQolConfig>().PlayChargeReadySound) SoundEngine.PlaySound(SoundID.MaxMana, player.Center);
    }

    public override void OnWorldUnload() { _status = null; _announced.Clear(); }

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
        if (_status is not { } status || !Visible() || Main.LocalPlayer is not { active: true, dead: false })
            return true;
        Rectangle bar = Bounds(Main.mouseX, Main.mouseY, Main.screenWidth, Main.screenHeight);
        var sb = Main.spriteBatch;
        sb.Draw(TextureAssets.MagicPixel.Value, bar, new Color(12, 20, 29, 220));
        int fill = (int)MathF.Round((bar.Width - 2) * status.Progress);
        if (fill > 0) sb.Draw(TextureAssets.MagicPixel.Value,
            new Rectangle(bar.X + 1, bar.Y + 1, fill, bar.Height - 2), status.Ready ? Color.Gold : Color.Cyan);
        string label = Language.GetTextValue("Mods.InfiniCrafterLocal.ChargeUI." + (status.Ready ? "Ready" : "Progress"),
            (int)MathF.Floor(status.Progress * 100f));
        Utils.DrawBorderString(sb, label, new Vector2(bar.Center.X, bar.Bottom + 2), Color.White,
            .65f, anchorx: .5f);
        return true;
    }
}
