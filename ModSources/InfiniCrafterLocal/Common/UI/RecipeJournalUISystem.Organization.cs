#nullable enable
using System;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class RecipeJournalUISystem
{
    private static void DrawOrganization(SpriteBatch sb, Rectangle area, bool click, Vector2 cursor)
    {
        var owner = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
        Label(sb, Text("BatchCount", BatchSelection.Count), area.TopLeft(), Ink, .65f, area.Width);
        var actions = new (string Label, bool Enabled, Action Execute)[] {
            (Text("BatchSelectFiltered", _filteredEntries.Length), _filteredEntries.Length > 0, () => { foreach (var d in _filteredEntries) if (BatchSelection.Count < 4096) BatchSelection.Add(d.Id); }),
            (Text("BatchClear"), BatchSelection.Count > 0, () => BatchSelection.Clear()),
            (Text("BatchFavorite"), BatchSelection.Count > 0, () => { foreach (string id in BatchSelection) owner.SetJournalFavorite(id, true); }),
            (Text("BatchUnfavorite"), BatchSelection.Count > 0, () => { foreach (string id in BatchSelection) owner.SetJournalFavorite(id, false); }),
            (Text("Collection" + _collectionChoice), true, () => _collectionChoice = (_collectionChoice + 1) % 5),
            (Text("BatchCollection"), BatchSelection.Count > 0, () => { foreach (string id in BatchSelection) owner.SetJournalCollection(id, _collectionChoice); }),
        };
        int visible = Math.Max(0, (area.Height - 55) / 30);
        _detailScroll = Math.Clamp(_detailScroll, 0, Math.Max(0, actions.Length - visible));
        for (int i = _detailScroll; i < Math.Min(actions.Length, _detailScroll + visible); i++)
        {
            var action = actions[i];
            if (Button(sb, new Rectangle(area.X, area.Y + 26 + (i - _detailScroll) * 30, area.Width, 26), action.Label, click, cursor, action.Enabled)) action.Execute();
        }
        if (area.Height >= 55) Label(sb, Text("BatchHint"), new Vector2(area.X, area.Bottom - 24), Muted, .55f, area.Width);
    }
}
