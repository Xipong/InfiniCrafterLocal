#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.GameContent;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.UI;

[Autoload(Side = ModSide.Client)]
public sealed class RecipeObjectiveUISystem : ModSystem
{
    private string[] _lines = Array.Empty<string>();
    private uint _tick = uint.MaxValue;
    public override void OnWorldUnload() { _lines = Array.Empty<string>(); _tick = uint.MaxValue; }
    public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
    {
        int index = layers.FindIndex(l => l.Name == "Vanilla: Mouse Text");
        if (index >= 0) layers.Insert(index, new LegacyGameInterfaceLayer("InfiniCrafterLocal: Fusion Objectives", Draw, InterfaceScaleType.UI));
    }
    private bool Draw()
    {
        if (Main.gameMenu || Main.hideUI || Main.playerInventory || Main.mapFullscreen || Main.ingameOptionsWindow
            || Main.inFancyUI || Main.LocalPlayer is not { active: true, dead: false }) return true;
        if (_tick == uint.MaxValue || unchecked(Main.GameUpdateCount - _tick) >= 30)
        {
            _tick = Main.GameUpdateCount;
            var player = Main.LocalPlayer; var owner = player.GetModPlayer<InfiniCraftPlayer>();
            var known = InfiniCrafterLocalMod.GeneratedItems?.Snapshot() ?? Array.Empty<GeneratedItemData>();
            var stock = RecipeInventoryView.Capture(player, Main.worldID.ToString());
            var rows = new List<string>();
            foreach (var data in RecipeJournalView.Entries(known, Main.worldID.ToString(), "", owner.IsJournalPinned, true).Take(3))
            {
                var objective = owner.JournalObjective(data.Id);
                var plan = RecipePlanView.Build(data, objective.Quantity, known, stock, objective.Storage);
                rows.Add(data.Name + " · " + plan.OwnedTarget + "/" + plan.Quantity);
                rows.Add(RecipeJournalUISystem.Text(objective.Storage ? "PlanBanks" : "PlanCarried"));
                if (plan.Truncated) rows.Add(RecipeJournalUISystem.Text("PlanTruncated"));
                else if (plan.Completed) rows.Add(RecipeJournalUISystem.Text("GoalCompleted"));
                else if (plan.Missing.Count == 0) rows.Add(RecipeJournalUISystem.Text("GoalReady"));
                else
                {
                    foreach (var need in plan.Missing.Take(2)) rows.Add("  " + need.Count + " × " + need.Name);
                    if (plan.Missing.Count > 2) rows.Add(RecipeJournalUISystem.Text("GoalMore", plan.Missing.Count - 2));
                }
            }
            _lines = rows.ToArray();
        }
        if (_lines.Length == 0 || Main.screenWidth < 480 || Main.screenHeight < 360) return true;
        int width = Math.Min(300, Main.screenWidth / 3), height = _lines.Length * 22 + 12;
        var box = new Rectangle(12, Math.Max(160, Main.screenHeight - height - 16), width, height);
        Main.spriteBatch.Draw(TextureAssets.MagicPixel.Value, box, new Color(12, 18, 27, 175));
        for (int i = 0; i < _lines.Length; i++)
        {
            string text = _lines[i];
            while (text.Length > 0 && FontAssets.MouseText.Value.MeasureString(text).X * .65f > width - 16) text = text[..^1];
            Utils.DrawBorderString(Main.spriteBatch, text, new Vector2(box.X + 8, box.Y + 6 + i * 22), Color.LightGoldenrodYellow, .65f);
        }
        return true;
    }
}
