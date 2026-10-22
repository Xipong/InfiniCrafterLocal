using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static void JournalHotkeyAndCompactControlsStayScoped()
    {
        Equal(true, RecipeJournalUISystem.CanToggleFromKey(true, false, false, false, false, false, false), "ordinary gameplay can toggle");
        for (int blocked = 0; blocked < 7; blocked++)
        {
            bool[] flags = { true, false, false, false, false, false, false };
            flags[blocked] = blocked != 0;
            Equal(false, RecipeJournalUISystem.CanToggleFromKey(flags[0], flags[1], flags[2], flags[3], flags[4], flags[5], flags[6]), "focus/menu/death/text/chat/block/rebind refuse toggle");
        }
        // UI-space dimensions also model high UI scales. Every visible detail
        // area keeps both controls contained and non-overlapping, including <200px.
        foreach (int width in new[] { 60, 96, 160, 240, 360, 640 })
        foreach (int height in new[] { 40, 60, 90, 120, 199, 200, 300 })
        {
            var area = new Rectangle(17, 31, width, height);
            var controls = RecipeJournalView.DetailControls(area);
            Equal(true, area.Contains(controls.Back), "back inside short detail");
            Equal(true, area.Contains(controls.Save), "save inside short detail");
            Equal(false, controls.Back.Intersects(controls.Save), "controls do not overlap");
            Equal(true, controls.Back.Width > 0 && controls.Save.Width > 0 && controls.Save.Height >= 20, "usable controls stay visible");
        }
    }
}
