#nullable enable
using System;
using System.Globalization;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.Localization;
using Terraria.GameInput;
using Microsoft.Xna.Framework.Input;
using InfiniCrafterLocal.Common.Players;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class RecipeJournalUISystem
{
    private static int _preparationLane;
    private static Content.Items.GeneratedItem.GuideSection _guideSection;
    private static string _guideQuery = "";
    private static bool DrawAnalysisPage(SpriteBatch sb, GeneratedItemData data, Rectangle area, bool click, Vector2 cursor)
    {
        if (_detailPage == DetailPage.Recipe) return false;
        if (_detailPage == DetailPage.Filters) { DrawFilterPresets(sb, area, click, cursor); return true; }
        if (_detailPage is DetailPage.Ancestors or DetailPage.Descendants)
        {
            return DrawLineagePage(sb, data, area, click, cursor);
        }

        if (_detailPage == DetailPage.Notebook)
        {
            var owner = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
            int collection = owner.JournalCollection(data.Id);
            if (Button(sb, new Rectangle(area.X, area.Y, area.Width, 26), Text("Collection" + collection), click, cursor))
                owner.SetJournalCollection(data.Id, (collection + 1) % 5);
            var box = new Rectangle(area.X, area.Y + 34, area.Width, Math.Min(100, Math.Max(0, area.Height - 65)));
            if (box.Width < 40 || box.Height < 28) { SetNoteFocus(false); return true; }
            Chassis(sb, box, _noteFocus ? Panel : Inset);
            if (click) SetNoteFocus(box.Contains(cursor.ToPoint()));
            string note = owner.JournalNote(data.Id);
            if (_noteFocus)
            {
                PlayerInput.WritingText = true; Main.blockInput = true; Main.instance.HandleIME();
                owner.SetJournalNote(data.Id, Main.GetInputText(note)); note = owner.JournalNote(data.Id);
                if (Main.keyState.IsKeyDown(Keys.Enter)) SetNoteFocus(false);
            }
            Paragraph(sb, note.Length == 0 && !_noteFocus ? Text("NoteHint") : note + (_noteFocus ? "|" : ""),
                new Rectangle(box.X + 8, box.Y + 6, Math.Max(0, box.Width - 16), Math.Max(0, box.Height - 12)), Ink, .65f);
            if (area.Height > 150) Paragraph(sb, Text("NotePrivacy"), new Rectangle(area.X, box.Bottom + 8, area.Width, area.Bottom - box.Bottom - 8), Muted, .55f);
            return true;
        }
        if (_detailPage == DetailPage.Discovery)
        {
            var owner = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
            var discoveries = RecipeJournalView.Entries(_known, data.RecipeMeta.WorldId, "", _ => false, false);
            int unseen = discoveries.Count(d => owner.JournalLastVisited(d.Id) == 0);
            Label(sb, Text("DiscoverySummary", discoveries.Length, unseen, discoveries.Count(d => owner.IsJournalFavorite(d.Id))), area.TopLeft(), Ink, .6f, area.Width);
            if (Button(sb, new Rectangle(area.X, area.Y + 28, area.Width, 25), Text(_unreadOnly ? "ShowVisited" : "OnlyUnvisited"), click, cursor))
            { _unreadOnly = !_unreadOnly; _page = 0; }
            var recent = discoveries.Where(d => owner.JournalLastVisited(d.Id) > 0).OrderByDescending(d => owner.JournalLastVisited(d.Id)).Take(32).ToArray();
            int visible = Math.Max(0, (area.Height - 62) / 28); _detailScroll = Math.Clamp(_detailScroll, 0, Math.Max(0, recent.Length - visible));
            for (int i = _detailScroll; i < Math.Min(recent.Length, _detailScroll + visible); i++)
                if (Button(sb, new Rectangle(area.X, area.Y + 60 + (i - _detailScroll) * 28, area.Width, 25), recent[i].Name, click, cursor))
                { Select(recent[i].Id, revealOutsideFilters: true); return true; }
            return true;
        }
        if (_detailPage == DetailPage.Organize)
        {
            DrawOrganization(sb, area, click, cursor); return true;
        }
        string content = "";
        if (_detailPage == DetailPage.Help)
            content = Text("HelpBrowse") + "\n" + Text("KeyboardBrowse") + "\n\n" + Text("HelpSearch") + "\n\n" + Text("HelpPlan") + "\n\n" + Text("HelpOwnership");
        if (_detailPage == DetailPage.Guide)
        {
            if (area.Height < 100) { SetNoteFocus(false); return true; }
            int copyWidth = Math.Min(75, area.Width / 3);
            if (Button(sb, new Rectangle(area.X, area.Y, area.Width - copyWidth - 4, 25), Text("GuideSection" + _guideSection), click, cursor))
            { _guideSection = (Content.Items.GeneratedItem.GuideSection)(((int)_guideSection + 1) % Enum.GetValues<Content.Items.GeneratedItem.GuideSection>().Length); _detailScroll = 0; }
            var facts = Content.Items.GeneratedItem.RuntimeGuide(data, _guideSection, _guideQuery);
            if (Button(sb, new Rectangle(area.Right - copyWidth, area.Y, copyWidth, 25), Text("GuideCopy"), click, cursor))
            {
                try { ReLogic.OS.Platform.Get<ReLogic.OS.IClipboard>().Value = data.Name + "\n" + string.Join("\n", facts); _hoverText = Text("GuideCopied"); }
                catch { _hoverText = Text("GuideCopyUnavailable"); }
            }
            var search = new Rectangle(area.X, area.Y + 30, area.Width, 26);
            Chassis(sb, search, _noteFocus ? Panel : Inset);
            if (click) SetNoteFocus(search.Contains(cursor.ToPoint()));
            if (_noteFocus)
            {
                PlayerInput.WritingText = true; Main.blockInput = true; Main.instance.HandleIME();
                string typed = Main.GetInputText(_guideQuery).Replace('\n', ' ').Replace('\r', ' ');
                _guideQuery = typed.Length > 80 ? typed[..80] : typed;
                if (Main.keyState.IsKeyDown(Keys.Enter)) SetNoteFocus(false);
            }
            Label(sb, _guideQuery.Length == 0 && !_noteFocus ? Text("GuideSearchHint") : _guideQuery + (_noteFocus ? "|" : ""), search.TopLeft() + new Vector2(5, 3), Ink, .6f, search.Width - 10);
            area.Y += 62; area.Height -= 62;
            content = data.Name + "\n" + Text("GuideHint") + "\n\n"
                + (facts.Count == 0 ? Text("GuideNoMatches") : string.Join("\n", facts));
        }
        if (_detailPage == DetailPage.Plan)
        {
            if (area.Height < 92) return true;
            var owner = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
            var objective = owner.JournalObjective(data.Id);
            int _planQuantity = objective.Quantity;
            bool _planIncludeStorage = objective.Storage;
            if (Button(sb, new Rectangle(area.X, area.Y, 30, 24), "−", click, cursor, enabled: _planQuantity > 1)) _planQuantity--;
            if (Button(sb, new Rectangle(area.X + 34, area.Y, 70, 24), _planQuantity + " +", click, cursor, enabled: _planQuantity < 999)) _planQuantity++;
            if (Button(sb, new Rectangle(area.X + 110, area.Y, Math.Max(0, area.Width - 110), 24), Text(_planIncludeStorage ? "PlanBanks" : "PlanCarried"), click, cursor)) _planIncludeStorage = !_planIncludeStorage;
            owner.SetJournalObjective(data.Id, _planQuantity, _planIncludeStorage);
            if (Button(sb, new Rectangle(area.X, area.Y + 29, area.Width / 2, 24), Text(owner.IsJournalPinned(data.Id) ? "UnpinObjective" : "PinObjective"), click, cursor))
                owner.ToggleJournalPin(data.Id);
            if (Button(sb, new Rectangle(area.X + area.Width / 2 + 4, area.Y + 29, Math.Max(0, area.Width / 2 - 4), 24), Text("GoalBatch"), click, cursor))
            { _planQuantity = Math.Clamp(_planQuantity + Math.Max(1, data.Gameplay.CraftYield), 1, 999); owner.SetJournalObjective(data.Id, _planQuantity, _planIncludeStorage); }
            area.Y += 60; area.Height -= 60;
            var plan = RecipePlanView.Build(data, _planQuantity, _known,
                RecipeInventoryView.Capture(Main.LocalPlayer, data.RecipeMeta.WorldId), _planIncludeStorage);
            content = Text("GoalProgress", plan.OwnedTarget, plan.Quantity) + "\n" + Text("PlanNotice") + "\n" + (plan.Truncated ? Text("PlanTruncated") + "\n" : "") + Text("PlanMissing");
            foreach (var row in plan.Missing) content += "\n" + row.Count + " × " + row.Name;
            if (!plan.Truncated && plan.Missing.Count == 0) content += "\n" + Text(plan.Completed ? "GoalCompleted" : "PlanStockReady");
            content += "\n\n" + Text("PlanSteps");
            foreach (var row in plan.Steps) content += "\n" + Text("PlanStep", row.Crafts, row.Name, row.Produced);
            content += "\n\n" + Text("PlanAllocationTitle", plan.TotalCrafts);
            foreach (var row in plan.Allocations.Where(r => r.Used > 0 || r.Surplus > 0))
                content += "\n" + Text("PlanAllocation", row.Name, row.Used, row.Surplus);
            content += "\n" + Text("PlanProtection");
        }
        if (_detailPage == DetailPage.Inventory)
        {
            var owner = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
            _preparationLane = Math.Clamp(_preparationLane, 0, owner.MultiDevWindowCount - 1);
            if (area.Height > 65)
            {
                int laneWidth = Math.Min(85, area.Width / 3);
                if (Button(sb, new Rectangle(area.X, area.Y, laneWidth, 25), Text("PrepareLane", _preparationLane + 1), click, cursor))
                    _preparationLane = (_preparationLane + 1) % owner.MultiDevWindowCount;
                if (Button(sb, new Rectangle(area.X + laneWidth + 6, area.Y, area.Width - laneWidth - 6, 25), Text("PrepareRecipe"), click, cursor, enabled: owner.GetRecipePreparationReadiness(data, _preparationLane) == InfiniCraftPlayer.RecipePreparationReadiness.Ready))
                {
                    if (owner.PrepareKnownRecipe(data, _preparationLane)) { Close(); return true; }
                    _hoverText = Text("PrepareRefused");
                }
                area.Y += 32; area.Height -= 32;
            }
            var stock = RecipeInventoryView.Capture(Main.LocalPlayer, data.RecipeMeta.WorldId);
            var output = RecipeInventoryView.Find(stock, "generated:" + data.Id);
            content = owner.RecipePreparationGuidance(data, _preparationLane) + "\n\n" + data.Name + "\n" + Text("StockRow", output.Carried, output.Stored, output.Protected) + "\n\n" + Text("Ingredients");
            for (int i = 0; i < data.RecipeMeta.ParentIdentities.Length; i++)
            {
                var row = RecipeInventoryView.Find(stock, data.RecipeMeta.ParentIdentities[i]);
                content += "\n" + (i == 0 ? data.ParentA : data.ParentB) + "\n" + Text("StockRow", row.Carried, row.Stored, row.Protected);
            }
            content += "\n\n" + Text("StockScope");
        }
        if (_detailPage == DetailPage.Comparison)
        {
            var reference = _known.FirstOrDefault(d => d.Id == _comparisonId && d.RecipeMeta.WorldId == data.RecipeMeta.WorldId
                && !GeneratedItemData.IsPlayerSaveReferenceOnly(d));
            if (reference is null) content = Text("ComparisonHelp");
            else
            {
                var culture = Language.ActiveCulture.CultureInfo;
                content = data.Name + " ↔ " + reference.Name + "\n" + Text("BaseStatsHint") + "\n"
                    + Text("DamageClasses", data.Gameplay.DamageClass, reference.Gameplay.DamageClass);
                foreach (var row in RecipeComparisonView.Compare(data, reference))
                    content += "\n" + Text("Stat" + row.Key) + ": " + row.Value.ToString("0.##", culture)
                        + " / " + row.Reference.ToString("0.##", culture)
                        + " (" + row.Delta.ToString("+0.##;-0.##;0", culture) + ")";
            }
        }
        Paragraph(sb, content, area, Ink, .65f, true);
        return true;
    }
}
