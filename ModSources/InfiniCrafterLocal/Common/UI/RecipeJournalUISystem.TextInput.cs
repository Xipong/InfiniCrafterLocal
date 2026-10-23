#nullable enable
using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework.Input;
using Terraria;
using Terraria.GameInput;
namespace InfiniCrafterLocal.Common.UI;
public sealed partial class RecipeJournalUISystem
{
    private static bool _priorBlockInput, _priorWritingText;
    private static readonly List<string> RecentQueries = new();
    private static int _queryRecall = -1;
    private static string _queryDraft = "";
    internal static void SetTextFocus(int target)
    {
        bool owned = _searchFocus || _noteFocus;
        if (target != 0 && !owned)
        {
            if (Main.blockInput || PlayerInput.WritingText || Main.drawingPlayerChat || PlayerInput.CurrentlyRebinding) return;
            _priorBlockInput = Main.blockInput; _priorWritingText = PlayerInput.WritingText;
        }
        _searchFocus = target == 1; _noteFocus = target == 2;
        if (target != 0) { Main.blockInput = true; PlayerInput.WritingText = true; }
        else if (owned) { Main.blockInput = _priorBlockInput; PlayerInput.WritingText = _priorWritingText; }
    }
    internal static string RemoveLastQueryTerm(string query)
    {
        query = query.TrimEnd(); bool quoted = false; int start = 0;
        for (int i = 0; i < query.Length; i++)
        {
            if (query[i] == '\\' && i + 1 < query.Length && query[i + 1] == '"') { i++; continue; }
            if (query[i] == '"') quoted = !quoted;
            if (!quoted && char.IsWhiteSpace(query[i])) start = i + 1;
        }
        return query[..start].TrimEnd();
    }
    internal static void RememberQuery(string query)
    {
        query = query.Trim();
        if (query.Length == 0 || RecipeJournalView.QueryIssue(query).Length > 0) return;
        RecentQueries.Remove(query); RecentQueries.Insert(0, query);
        if (RecentQueries.Count > 12) RecentQueries.RemoveAt(12);
        _queryRecall = -1;
    }
    internal static string RecallQuery(int direction, string current)
    {
        if (RecentQueries.Count == 0) return current;
        if (_queryRecall < 0) _queryDraft = current;
        _queryRecall = Math.Clamp(_queryRecall + direction, -1, RecentQueries.Count - 1);
        return _queryRecall < 0 ? _queryDraft : RecentQueries[_queryRecall];
    }
    private static string EditSearchText()
    {
        if (ControlDown && KeyPressed(Keys.Up)) return RecallQuery(1, _query);
        if (ControlDown && KeyPressed(Keys.Down)) return RecallQuery(-1, _query);
        if (ControlDown && KeyPressed(Keys.Back)) return RemoveLastQueryTerm(_query);
        if (ControlDown && KeyPressed(Keys.L)) { _queryRecall = -1; return ""; }
        string next = Main.GetInputText(_query);
        if (next != _query) _queryRecall = -1;
        return next;
    }
}
