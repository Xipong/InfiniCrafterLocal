#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void AtlasTextInput()
 {
        bool blocked = Terraria.Main.blockInput, writing = Terraria.GameInput.PlayerInput.WritingText;
        try {
            Terraria.Main.blockInput = false; Terraria.GameInput.PlayerInput.WritingText = false;
            RecipeJournalUISystem.SetTextFocus(1);
            Equal(true, Terraria.Main.blockInput, "search owns input");
            RecipeJournalUISystem.SetTextFocus(2);
            Equal(true, Terraria.GameInput.PlayerInput.WritingText, "note handoff retains ownership");
            RecipeJournalUISystem.SetTextFocus(0);
            Equal(false, Terraria.Main.blockInput, "release restores block state");
            Equal(false, Terraria.GameInput.PlayerInput.WritingText, "release restores text state");
            Terraria.Main.blockInput = true;
            RecipeJournalUISystem.SetTextFocus(0);
            Equal(true, Terraria.Main.blockInput, "unfocused journal cannot unblock external UI");
            RecipeJournalUISystem.SetTextFocus(1);
            RecipeJournalUISystem.SetTextFocus(0);
            Equal(true, Terraria.Main.blockInput, "external owner cannot be stolen");
        } finally { RecipeJournalUISystem.SetTextFocus(0); Terraria.Main.blockInput = blocked; Terraria.GameInput.PlayerInput.WritingText = writing; }
        Equal("kind:weapon", RecipeJournalUISystem.RemoveLastQueryTerm("kind:weapon name:\"fire blade\""), "delete whole quoted term");
        RecipeJournalUISystem.RememberQuery("kind:weapon");
        RecipeJournalUISystem.RememberQuery("depth:>2");
        Equal("depth:>2", RecipeJournalUISystem.RecallQuery(1, "draft"), "recall newest");
        Equal("kind:weapon", RecipeJournalUISystem.RecallQuery(1, ""), "recall older");
        RecipeJournalUISystem.RecallQuery(-1, "");
        Equal("draft", RecipeJournalUISystem.RecallQuery(-1, ""), "restore unfinished search");
 }
}
