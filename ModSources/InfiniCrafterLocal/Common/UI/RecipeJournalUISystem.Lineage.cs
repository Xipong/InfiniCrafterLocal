#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class RecipeJournalUISystem
{
    private static bool DrawLineagePage(SpriteBatch sb, GeneratedItemData data, Rectangle area, bool click, Vector2 cursor)
    {
        var rows = RecipeLineageView.Build(data, _known, _detailPage == DetailPage.Descendants);
        var stock = RecipeInventoryView.Capture(Main.LocalPlayer, data.RecipeMeta.WorldId);
        var owner = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
        int visible = Math.Max(0, (area.Height - 32) / 36);
        _detailScroll = Math.Clamp(_detailScroll, 0, Math.Max(0, rows.Count - visible));
        Label(sb, Text("LineageLimit"), area.TopLeft(), Muted, .55f, area.Width);
        if (rows.Count == 0) Label(sb, Text("NoRelations"), area.TopLeft() + new Vector2(0, 32), Muted, .65f, area.Width);
        for (int i = _detailScroll; i < Math.Min(rows.Count, _detailScroll + visible); i++)
        {
            var row = rows[i];
            var rect = new Rectangle(area.X, area.Y + 30 + (i - _detailScroll) * 36, Math.Max(0, area.Width - 40), 32);
            var icon = new Rectangle(rect.X + 3, rect.Y + 3, 26, 26);
            bool hover = rect.Contains(cursor.ToPoint());
            Chassis(sb, rect, hover ? Panel : Inset);
            var related = row.Id.Length == 0 ? null : _known.FirstOrDefault(d => d.Id == row.Id && d.RecipeMeta.WorldId == data.RecipeMeta.WorldId);
            if (related is not null) Sprite(sb, related, icon);
            else if (row.NativeType > 0)
            {
                Main.instance.LoadItem(row.NativeType);
                Texture2D texture = TextureAssets.Item[row.NativeType].Value;
                Rectangle frame = Main.itemAnimations[row.NativeType]?.GetFrame(texture) ?? texture.Bounds;
                float scale = Math.Min(icon.Width / (float)frame.Width, icon.Height / (float)frame.Height);
                sb.Draw(texture, icon.Center.ToVector2(), frame, Color.White, 0, frame.Size() * .5f, scale, SpriteEffects.None, 0);
            }
            else CenterLabel(sb, "?", icon, Muted, .7f);
            Label(sb, row.Depth + ". " + row.Name + (row.Repeated ? " ↩" : row.Unknown ? " ?" : ""),
                new Vector2(rect.X + 34, rect.Y + 3), related is null ? Muted : Ink, .6f, Math.Max(0, rect.Width - 38));
            Label(sb, Text("LineageVia", row.ViaName), new Vector2(rect.X + 34, rect.Y + 18), Muted, .45f, Math.Max(0, rect.Width - 38));
            if (hover)
            {
                var held = RecipeInventoryView.Find(stock, row.Identity);
                _hoverText = row.Name + "\n" + Text("LineageVia", row.ViaName) + "\n" + Text("StockRow", held.Carried, held.Stored, held.Protected)
                    + "\n" + Text(row.Unknown ? "UnknownAncestor" : row.Repeated ? "RepeatedAncestor" : "OpenParent");
                if (click && related is not null) { Select(row.Id, revealOutsideFilters: true); return true; }
            }
            if (related is not null)
            {
                var pin = new Rectangle(area.Right - 34, rect.Y, 32, 32);
                if (Button(sb, pin, owner.IsJournalPinned(row.Id) ? "★" : "+", click, cursor)) owner.ToggleJournalPin(row.Id);
                if (pin.Contains(cursor.ToPoint())) _hoverText = Text("LineagePin");
            }
        }
        return true;
    }
}
