using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static int SelectionSourceExecutions;

    private sealed class SelectionItem : ModItem
    {
        public override bool? UseItem(Player player) { SelectionSourceExecutions++; First(player); return true; }
        private static void First(Player player) => Second(player);
        private static void Second(Player player) => player.statDefense += 7;
    }

    private sealed class SelectionNoise<T> : GlobalItem
    {
        public override bool? UseItem(Item item, Player player) { SelectionSourceExecutions++; player.statDefense += 1; return true; }
    }

    private sealed class SelectionStateItem : ModItem
    {
        public override bool? UseItem(Player player) { player.GetModPlayer<SelectionStatePlayer>().Active = true; return true; }
    }

    private sealed class SelectionStatePlayer : ModPlayer
    {
        public bool Active, Extra;
        public override void PostUpdateEquips()
        {
            if (Active && Player.wet) Player.statDefense += 13;
            if (Extra && Player.lavaWet) Player.statManaMax2 += 17;
        }
    }

    private sealed class SelectionDiamondStateItem : ModItem
    {
        public override bool? UseItem(Player player) { player.GetModPlayer<SelectionDiamondStatePlayer>().Active = true; return true; }
    }

    private sealed class SelectionDiamondStatePlayer : ModPlayer
    {
        public bool Active;
        public override void PostUpdateEquips()
        {
            // Nonconstant alternatives force a value-producing CFG diamond in
            // both optimized and Debug IL, followed by a consumer after its join.
            bool enabled;
            if (Active) enabled = Player.wet;
            else enabled = Player.lavaWet;
            if (enabled) Player.statDefense += 31;
            Player.statManaMax2 += 37;
        }
    }

    private sealed class SelectionExtraGlobal : GlobalItem
    {
        public override bool? UseItem(Item item, Player player) { player.GetModPlayer<SelectionStatePlayer>().Extra = true; return true; }
    }

    private sealed class SelectionCommonStateItem : ModItem
    {
        public override bool? UseItem(Player player) { player.wet = true; return true; }
    }
    private sealed class SelectionCommonStateGlobal : GlobalItem
    {
        public override bool? UseItem(Item item, Player player) { player.lavaWet = true; return true; }
    }
    private sealed class SelectionCommonStatePlayer : ModPlayer
    {
        public override void PostUpdateEquips()
        {
            if (Player.wet) Player.statDefense += 23;
            if (Player.lavaWet) Player.statManaMax2 += 29;
        }
    }

    private static class SelectionStaticState
    {
        public static int Charge;
    }
    private sealed class SelectionStaticReadItem : ModItem
    {
        public override bool? UseItem(Player player) => SelectionStaticState.Charge > 0;
    }
    private sealed class SelectionStaticStatePlayer : ModPlayer
    {
        public override void PostUpdate() { SelectionStaticState.Charge++; }
    }

    private sealed class SelectionMixedStateItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            player.wet = true;
            player.GetModPlayer<SelectionMixedStatePlayer>().Active = true;
            return true;
        }
    }
    private sealed class SelectionMixedStatePlayer : ModPlayer
    {
        public bool Active;
        private bool HasActive() => Active;
        public override void PostUpdateEquips()
        {
            if (Player.wet) Player.statDefense += 31;
            if (HasActive()) Player.lifeRegen += 37;
        }
    }

    private sealed class SelectionPromoteItem : ModItem
    {
        public override bool? UseItem(Player player) { player.GetModPlayer<SelectionPromotePlayer>().A = true; return true; }
    }
    private sealed class SelectionPromoteBGlobal : GlobalItem
    {
        public override bool? UseItem(Item item, Player player) { player.GetModPlayer<SelectionPromotePlayer>().B = true; return true; }
    }
    private sealed class SelectionPromoteDGlobal : GlobalItem
    {
        public override bool? UseItem(Item item, Player player) { player.GetModPlayer<SelectionPromotePlayer>().D = true; return true; }
    }
    private sealed class SelectionPromotePlayer : ModPlayer
    {
        public bool A, B, D;
        public override void PostUpdateEquips()
        {
            if (A) Player.statDefense += 1;
            if (D) B = true;
        }
        public override void PostUpdate() { if (B) Player.statManaMax2 += 2; }
    }

    private sealed class SelectionFanoutItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            FanoutEffect(player, 0, 1, 2, 3, 4, 5, 6, 7);
            FanoutEffect(player, 1, 2, 3, 4, 5, 6, 7, 8);
            FanoutEffect(player, 2, 3, 4, 5, 6, 7, 8, 9);
            FanoutEffect(player, 3, 4, 5, 6, 7, 8, 9, 10);
            FanoutEffect(player, 4, 5, 6, 7, 8, 9, 10, 11);
            FanoutEffect(player, 5, 6, 7, 8, 9, 10, 11, 12);
            FanoutEffect(player, 6, 7, 8, 9, 10, 11, 12, 13);
            FanoutEffect(player, 7, 8, 9, 10, 11, 12, 13, 14);
            FanoutEffect(player, 8, 9, 10, 11, 12, 13, 14, 15);
            FanoutEffect(player, 9, 10, 11, 12, 13, 14, 15, 16);
            FanoutEffect(player, 10, 11, 12, 13, 14, 15, 16, 17);
            FanoutEffect(player, 11, 12, 13, 14, 15, 16, 17, 18);
            FanoutEffect(player, 12, 13, 14, 15, 16, 17, 18, 19);
            FanoutEffect(player, 13, 14, 15, 16, 17, 18, 19, 20);
            FanoutEffect(player, 14, 15, 16, 17, 18, 19, 20, 21);
            FanoutEffect(player, 15, 16, 17, 18, 19, 20, 21, 22);
            FanoutEffect(player, 16, 17, 18, 19, 20, 21, 22, 23);
            FanoutEffect(player, 17, 18, 19, 20, 21, 22, 23, 24);
            FanoutEffect(player, 18, 19, 20, 21, 22, 23, 24, 25);
            FanoutEffect(player, 19, 20, 21, 22, 23, 24, 25, 26);
            FanoutEffect(player, 20, 21, 22, 23, 24, 25, 26, 27);
            FanoutEffect(player, 21, 22, 23, 24, 25, 26, 27, 28);
            FanoutEffect(player, 22, 23, 24, 25, 26, 27, 28, 29);
            FanoutEffect(player, 23, 24, 25, 26, 27, 28, 29, 30);
            FanoutEffect(player, 24, 25, 26, 27, 28, 29, 30, 31);
            FanoutEffect(player, 25, 26, 27, 28, 29, 30, 31, 32);
            FanoutEffect(player, 26, 27, 28, 29, 30, 31, 32, 33);
            FanoutEffect(player, 27, 28, 29, 30, 31, 32, 33, 34);
            FanoutEffect(player, 28, 29, 30, 31, 32, 33, 34, 35);
            FanoutEffect(player, 29, 30, 31, 32, 33, 34, 35, 36);
            FanoutEffect(player, 30, 31, 32, 33, 34, 35, 36, 37);
            FanoutEffect(player, 31, 32, 33, 34, 35, 36, 37, 38);
            FanoutEffect(player, 32, 33, 34, 35, 36, 37, 38, 39);
            FanoutEffect(player, 33, 34, 35, 36, 37, 38, 39, 40);
            FanoutEffect(player, 34, 35, 36, 37, 38, 39, 40, 41);
            FanoutEffect(player, 35, 36, 37, 38, 39, 40, 41, 42);
            FanoutEffect(player, 36, 37, 38, 39, 40, 41, 42, 43);
            FanoutEffect(player, 37, 38, 39, 40, 41, 42, 43, 44);
            FanoutEffect(player, 38, 39, 40, 41, 42, 43, 44, 45);
            FanoutEffect(player, 39, 40, 41, 42, 43, 44, 45, 46);
            FanoutEffect(player, 40, 41, 42, 43, 44, 45, 46, 47);
            FanoutEffect(player, 41, 42, 43, 44, 45, 46, 47, 48);
            FanoutEffect(player, 42, 43, 44, 45, 46, 47, 48, 49);
            FanoutEffect(player, 43, 44, 45, 46, 47, 48, 49, 50);
            FanoutEffect(player, 44, 45, 46, 47, 48, 49, 50, 51);
            FanoutEffect(player, 45, 46, 47, 48, 49, 50, 51, 52);
            FanoutEffect(player, 46, 47, 48, 49, 50, 51, 52, 53);
            FanoutEffect(player, 47, 48, 49, 50, 51, 52, 53, 54);
            FanoutEffect(player, 48, 49, 50, 51, 52, 53, 54, 55);
            FanoutEffect(player, 49, 50, 51, 52, 53, 54, 55, 56);
            FanoutEffect(player, 50, 51, 52, 53, 54, 55, 56, 57);
            FanoutEffect(player, 51, 52, 53, 54, 55, 56, 57, 58);
            FanoutEffect(player, 52, 53, 54, 55, 56, 57, 58, 59);
            FanoutEffect(player, 53, 54, 55, 56, 57, 58, 59, 60);
            FanoutEffect(player, 54, 55, 56, 57, 58, 59, 60, 61);
            FanoutEffect(player, 55, 56, 57, 58, 59, 60, 61, 62);
            FanoutEffect(player, 56, 57, 58, 59, 60, 61, 62, 63);
            FanoutEffect(player, 57, 58, 59, 60, 61, 62, 63, 64);
            FanoutEffect(player, 58, 59, 60, 61, 62, 63, 64, 65);
            FanoutEffect(player, 59, 60, 61, 62, 63, 64, 65, 66);
            FanoutEffect(player, 60, 61, 62, 63, 64, 65, 66, 67);
            FanoutEffect(player, 61, 62, 63, 64, 65, 66, 67, 68);
            FanoutEffect(player, 62, 63, 64, 65, 66, 67, 68, 69);
            FanoutEffect(player, 63, 64, 65, 66, 67, 68, 69, 70);
            FanoutEffect(player, 64, 65, 66, 67, 68, 69, 70, 71);
            FanoutEffect(player, 65, 66, 67, 68, 69, 70, 71, 72);
            FanoutEffect(player, 66, 67, 68, 69, 70, 71, 72, 73);
            FanoutEffect(player, 67, 68, 69, 70, 71, 72, 73, 74);
            FanoutEffect(player, 68, 69, 70, 71, 72, 73, 74, 75);
            FanoutEffect(player, 69, 70, 71, 72, 73, 74, 75, 76);
            FanoutEffect(player, 70, 71, 72, 73, 74, 75, 76, 77);
            FanoutEffect(player, 71, 72, 73, 74, 75, 76, 77, 78);
            FanoutEffect(player, 72, 73, 74, 75, 76, 77, 78, 79);
            FanoutEffect(player, 73, 74, 75, 76, 77, 78, 79, 80);
            FanoutEffect(player, 74, 75, 76, 77, 78, 79, 80, 81);
            FanoutEffect(player, 75, 76, 77, 78, 79, 80, 81, 82);
            FanoutEffect(player, 76, 77, 78, 79, 80, 81, 82, 83);
            FanoutEffect(player, 77, 78, 79, 80, 81, 82, 83, 84);
            FanoutEffect(player, 78, 79, 80, 81, 82, 83, 84, 85);
            FanoutEffect(player, 79, 80, 81, 82, 83, 84, 85, 86);
            FanoutEffect(player, 80, 81, 82, 83, 84, 85, 86, 87);
            FanoutEffect(player, 81, 82, 83, 84, 85, 86, 87, 88);
            FanoutEffect(player, 82, 83, 84, 85, 86, 87, 88, 89);
            FanoutEffect(player, 83, 84, 85, 86, 87, 88, 89, 90);
            FanoutEffect(player, 84, 85, 86, 87, 88, 89, 90, 91);
            FanoutEffect(player, 85, 86, 87, 88, 89, 90, 91, 92);
            FanoutEffect(player, 86, 87, 88, 89, 90, 91, 92, 93);
            FanoutEffect(player, 87, 88, 89, 90, 91, 92, 93, 94);
            FanoutEffect(player, 88, 89, 90, 91, 92, 93, 94, 95);
            FanoutEffect(player, 89, 90, 91, 92, 93, 94, 95, 96);
            FanoutEffect(player, 90, 91, 92, 93, 94, 95, 96, 97);
            FanoutEffect(player, 91, 92, 93, 94, 95, 96, 97, 98);
            FanoutEffect(player, 92, 93, 94, 95, 96, 97, 98, 99);
            FanoutEffect(player, 93, 94, 95, 96, 97, 98, 99, 100);
            FanoutEffect(player, 94, 95, 96, 97, 98, 99, 100, 101);
            FanoutEffect(player, 95, 96, 97, 98, 99, 100, 101, 102);
            FanoutEffect(player, 96, 97, 98, 99, 100, 101, 102, 103);
            FanoutEffect(player, 97, 98, 99, 100, 101, 102, 103, 104);
            FanoutEffect(player, 98, 99, 100, 101, 102, 103, 104, 105);
            FanoutEffect(player, 99, 100, 101, 102, 103, 104, 105, 106);
            FanoutEffect(player, 100, 101, 102, 103, 104, 105, 106, 107);
            FanoutEffect(player, 101, 102, 103, 104, 105, 106, 107, 108);
            FanoutEffect(player, 102, 103, 104, 105, 106, 107, 108, 109);
            FanoutEffect(player, 103, 104, 105, 106, 107, 108, 109, 110);
            FanoutEffect(player, 104, 105, 106, 107, 108, 109, 110, 111);
            FanoutEffect(player, 105, 106, 107, 108, 109, 110, 111, 112);
            FanoutEffect(player, 106, 107, 108, 109, 110, 111, 112, 113);
            FanoutEffect(player, 107, 108, 109, 110, 111, 112, 113, 114);
            FanoutEffect(player, 108, 109, 110, 111, 112, 113, 114, 115);
            FanoutEffect(player, 109, 110, 111, 112, 113, 114, 115, 116);
            FanoutEffect(player, 110, 111, 112, 113, 114, 115, 116, 117);
            FanoutEffect(player, 111, 112, 113, 114, 115, 116, 117, 118);
            FanoutEffect(player, 112, 113, 114, 115, 116, 117, 118, 119);
            FanoutEffect(player, 113, 114, 115, 116, 117, 118, 119, 120);
            FanoutEffect(player, 114, 115, 116, 117, 118, 119, 120, 121);
            FanoutEffect(player, 115, 116, 117, 118, 119, 120, 121, 122);
            FanoutEffect(player, 116, 117, 118, 119, 120, 121, 122, 123);
            FanoutEffect(player, 117, 118, 119, 120, 121, 122, 123, 124);
            FanoutEffect(player, 118, 119, 120, 121, 122, 123, 124, 125);
            FanoutEffect(player, 119, 120, 121, 122, 123, 124, 125, 126);
            FanoutEffect(player, 120, 121, 122, 123, 124, 125, 126, 127);
            FanoutEffect(player, 121, 122, 123, 124, 125, 126, 127, 128);
            FanoutEffect(player, 122, 123, 124, 125, 126, 127, 128, 129);
            FanoutEffect(player, 123, 124, 125, 126, 127, 128, 129, 130);
            FanoutEffect(player, 124, 125, 126, 127, 128, 129, 130, 131);
            FanoutEffect(player, 125, 126, 127, 128, 129, 130, 131, 132);
            FanoutEffect(player, 126, 127, 128, 129, 130, 131, 132, 133);
            FanoutEffect(player, 127, 128, 129, 130, 131, 132, 133, 134);
            FanoutEffect(player, 128, 129, 130, 131, 132, 133, 134, 135);
            FanoutEffect(player, 129, 130, 131, 132, 133, 134, 135, 136);
            FanoutEffect(player, 130, 131, 132, 133, 134, 135, 136, 137);
            FanoutEffect(player, 131, 132, 133, 134, 135, 136, 137, 138);
            FanoutEffect(player, 132, 133, 134, 135, 136, 137, 138, 139);
            FanoutEffect(player, 133, 134, 135, 136, 137, 138, 139, 140);
            FanoutEffect(player, 134, 135, 136, 137, 138, 139, 140, 141);
            FanoutEffect(player, 135, 136, 137, 138, 139, 140, 141, 142);
            FanoutEffect(player, 136, 137, 138, 139, 140, 141, 142, 143);
            FanoutEffect(player, 137, 138, 139, 140, 141, 142, 143, 144);
            FanoutEffect(player, 138, 139, 140, 141, 142, 143, 144, 145);
            FanoutEffect(player, 139, 140, 141, 142, 143, 144, 145, 146);
            FanoutEffect(player, 140, 141, 142, 143, 144, 145, 146, 147);
            FanoutEffect(player, 141, 142, 143, 144, 145, 146, 147, 148);
            FanoutEffect(player, 142, 143, 144, 145, 146, 147, 148, 149);
            FanoutEffect(player, 143, 144, 145, 146, 147, 148, 149, 150);
            FanoutEffect(player, 144, 145, 146, 147, 148, 149, 150, 151);
            FanoutEffect(player, 145, 146, 147, 148, 149, 150, 151, 152);
            FanoutEffect(player, 146, 147, 148, 149, 150, 151, 152, 153);
            FanoutEffect(player, 147, 148, 149, 150, 151, 152, 153, 154);
            FanoutEffect(player, 148, 149, 150, 151, 152, 153, 154, 155);
            FanoutEffect(player, 149, 150, 151, 152, 153, 154, 155, 156);
            FanoutEffect(player, 150, 151, 152, 153, 154, 155, 156, 157);
            FanoutEffect(player, 151, 152, 153, 154, 155, 156, 157, 158);
            FanoutEffect(player, 152, 153, 154, 155, 156, 157, 158, 159);
            FanoutEffect(player, 153, 154, 155, 156, 157, 158, 159, 160);
            FanoutEffect(player, 154, 155, 156, 157, 158, 159, 160, 161);
            FanoutEffect(player, 155, 156, 157, 158, 159, 160, 161, 162);
            FanoutEffect(player, 156, 157, 158, 159, 160, 161, 162, 163);
            FanoutEffect(player, 157, 158, 159, 160, 161, 162, 163, 164);
            FanoutEffect(player, 158, 159, 160, 161, 162, 163, 164, 165);
            FanoutEffect(player, 159, 160, 161, 162, 163, 164, 165, 166);
            FanoutEffect(player, 160, 161, 162, 163, 164, 165, 166, 167);
            FanoutEffect(player, 161, 162, 163, 164, 165, 166, 167, 168);
            FanoutEffect(player, 162, 163, 164, 165, 166, 167, 168, 169);
            FanoutEffect(player, 163, 164, 165, 166, 167, 168, 169, 170);
            FanoutEffect(player, 164, 165, 166, 167, 168, 169, 170, 171);
            FanoutEffect(player, 165, 166, 167, 168, 169, 170, 171, 172);
            FanoutEffect(player, 166, 167, 168, 169, 170, 171, 172, 173);
            FanoutEffect(player, 167, 168, 169, 170, 171, 172, 173, 174);
            FanoutEffect(player, 168, 169, 170, 171, 172, 173, 174, 175);
            FanoutEffect(player, 169, 170, 171, 172, 173, 174, 175, 176);
            FanoutEffect(player, 170, 171, 172, 173, 174, 175, 176, 177);
            FanoutEffect(player, 171, 172, 173, 174, 175, 176, 177, 178);
            FanoutEffect(player, 172, 173, 174, 175, 176, 177, 178, 179);
            FanoutEffect(player, 173, 174, 175, 176, 177, 178, 179, 180);
            FanoutEffect(player, 174, 175, 176, 177, 178, 179, 180, 181);
            FanoutEffect(player, 175, 176, 177, 178, 179, 180, 181, 182);
            FanoutEffect(player, 176, 177, 178, 179, 180, 181, 182, 183);
            FanoutEffect(player, 177, 178, 179, 180, 181, 182, 183, 184);
            FanoutEffect(player, 178, 179, 180, 181, 182, 183, 184, 185);
            FanoutEffect(player, 179, 180, 181, 182, 183, 184, 185, 186);
            FanoutEffect(player, 180, 181, 182, 183, 184, 185, 186, 187);
            FanoutEffect(player, 181, 182, 183, 184, 185, 186, 187, 188);
            FanoutEffect(player, 182, 183, 184, 185, 186, 187, 188, 189);
            FanoutEffect(player, 183, 184, 185, 186, 187, 188, 189, 190);
            FanoutEffect(player, 184, 185, 186, 187, 188, 189, 190, 191);
            FanoutEffect(player, 185, 186, 187, 188, 189, 190, 191, 192);
            FanoutEffect(player, 186, 187, 188, 189, 190, 191, 192, 193);
            FanoutEffect(player, 187, 188, 189, 190, 191, 192, 193, 194);
            FanoutEffect(player, 188, 189, 190, 191, 192, 193, 194, 195);
            FanoutEffect(player, 189, 190, 191, 192, 193, 194, 195, 196);
            FanoutEffect(player, 190, 191, 192, 193, 194, 195, 196, 197);
            FanoutEffect(player, 191, 192, 193, 194, 195, 196, 197, 198);
            FanoutEffect(player, 192, 193, 194, 195, 196, 197, 198, 199);
            FanoutEffect(player, 193, 194, 195, 196, 197, 198, 199, 200);
            FanoutEffect(player, 194, 195, 196, 197, 198, 199, 200, 201);
            FanoutEffect(player, 195, 196, 197, 198, 199, 200, 201, 202);
            FanoutEffect(player, 196, 197, 198, 199, 200, 201, 202, 203);
            FanoutEffect(player, 197, 198, 199, 200, 201, 202, 203, 204);
            FanoutEffect(player, 198, 199, 200, 201, 202, 203, 204, 205);
            FanoutEffect(player, 199, 200, 201, 202, 203, 204, 205, 206);
            return true;
        }
        private static void FanoutEffect(Player player, int a, int b, int c, int d, int e, int f, int g, int h)
            => player.statDefense += a + b + c + d + e + f + g + h;
    }

    private sealed class SelectionCycleItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            CycleA(player, 0);
            CycleA(player, 1);
            CycleA(player, 2);
            CycleA(player, 3);
            CycleA(player, 4);
            CycleA(player, 5);
            CycleA(player, 6);
            CycleA(player, 7);
            CycleA(player, 8);
            CycleA(player, 9);
            CycleA(player, 10);
            CycleA(player, 11);
            CycleA(player, 12);
            CycleA(player, 13);
            CycleA(player, 14);
            CycleA(player, 15);
            CycleA(player, 16);
            CycleA(player, 17);
            CycleA(player, 18);
            CycleA(player, 19);
            CycleA(player, 20);
            CycleA(player, 21);
            CycleA(player, 22);
            CycleA(player, 23);
            CycleA(player, 24);
            CycleA(player, 25);
            CycleA(player, 26);
            CycleA(player, 27);
            CycleA(player, 28);
            CycleA(player, 29);
            CycleA(player, 30);
            CycleA(player, 31);
            CycleA(player, 32);
            CycleA(player, 33);
            CycleA(player, 34);
            CycleA(player, 35);
            CycleA(player, 36);
            CycleA(player, 37);
            CycleA(player, 38);
            CycleA(player, 39);
            CycleA(player, 40);
            CycleA(player, 41);
            CycleA(player, 42);
            CycleA(player, 43);
            CycleA(player, 44);
            CycleA(player, 45);
            CycleA(player, 46);
            CycleA(player, 47);
            CycleA(player, 48);
            CycleA(player, 49);
            CycleA(player, 50);
            CycleA(player, 51);
            CycleA(player, 52);
            CycleA(player, 53);
            CycleA(player, 54);
            CycleA(player, 55);
            CycleA(player, 56);
            CycleA(player, 57);
            CycleA(player, 58);
            CycleA(player, 59);
            CycleA(player, 60);
            CycleA(player, 61);
            CycleA(player, 62);
            CycleA(player, 63);
            CycleA(player, 64);
            CycleA(player, 65);
            CycleA(player, 66);
            CycleA(player, 67);
            CycleA(player, 68);
            CycleA(player, 69);
            CycleA(player, 70);
            CycleA(player, 71);
            CycleA(player, 72);
            CycleA(player, 73);
            CycleA(player, 74);
            CycleA(player, 75);
            CycleA(player, 76);
            CycleA(player, 77);
            CycleA(player, 78);
            CycleA(player, 79);
            CycleA(player, 80);
            CycleA(player, 81);
            CycleA(player, 82);
            CycleA(player, 83);
            CycleA(player, 84);
            CycleA(player, 85);
            CycleA(player, 86);
            CycleA(player, 87);
            CycleA(player, 88);
            CycleA(player, 89);
            CycleA(player, 90);
            CycleA(player, 91);
            CycleA(player, 92);
            CycleA(player, 93);
            CycleA(player, 94);
            CycleA(player, 95);
            CycleA(player, 96);
            CycleA(player, 97);
            CycleA(player, 98);
            CycleA(player, 99);
            CycleA(player, 100);
            CycleA(player, 101);
            CycleA(player, 102);
            CycleA(player, 103);
            CycleA(player, 104);
            CycleA(player, 105);
            CycleA(player, 106);
            CycleA(player, 107);
            CycleA(player, 108);
            CycleA(player, 109);
            CycleA(player, 110);
            CycleA(player, 111);
            CycleA(player, 112);
            CycleA(player, 113);
            CycleA(player, 114);
            CycleA(player, 115);
            CycleA(player, 116);
            CycleA(player, 117);
            CycleA(player, 118);
            CycleA(player, 119);
            CycleA(player, 120);
            CycleA(player, 121);
            CycleA(player, 122);
            CycleA(player, 123);
            CycleA(player, 124);
            CycleA(player, 125);
            CycleA(player, 126);
            CycleA(player, 127);
            CycleA(player, 128);
            CycleA(player, 129);
            CycleA(player, 130);
            CycleA(player, 131);
            CycleA(player, 132);
            CycleA(player, 133);
            CycleA(player, 134);
            CycleA(player, 135);
            CycleA(player, 136);
            CycleA(player, 137);
            CycleA(player, 138);
            CycleA(player, 139);
            CycleA(player, 140);
            CycleA(player, 141);
            CycleA(player, 142);
            CycleA(player, 143);
            CycleA(player, 144);
            CycleA(player, 145);
            CycleA(player, 146);
            CycleA(player, 147);
            CycleA(player, 148);
            CycleA(player, 149);
            CycleA(player, 150);
            CycleA(player, 151);
            CycleA(player, 152);
            CycleA(player, 153);
            CycleA(player, 154);
            CycleA(player, 155);
            CycleA(player, 156);
            CycleA(player, 157);
            CycleA(player, 158);
            CycleA(player, 159);
            CycleA(player, 160);
            CycleA(player, 161);
            CycleA(player, 162);
            CycleA(player, 163);
            CycleA(player, 164);
            CycleA(player, 165);
            CycleA(player, 166);
            CycleA(player, 167);
            CycleA(player, 168);
            CycleA(player, 169);
            CycleA(player, 170);
            CycleA(player, 171);
            CycleA(player, 172);
            CycleA(player, 173);
            CycleA(player, 174);
            CycleA(player, 175);
            CycleA(player, 176);
            CycleA(player, 177);
            CycleA(player, 178);
            CycleA(player, 179);
            CycleA(player, 180);
            CycleA(player, 181);
            CycleA(player, 182);
            CycleA(player, 183);
            CycleA(player, 184);
            CycleA(player, 185);
            CycleA(player, 186);
            CycleA(player, 187);
            CycleA(player, 188);
            CycleA(player, 189);
            CycleA(player, 190);
            CycleA(player, 191);
            CycleA(player, 192);
            CycleA(player, 193);
            CycleA(player, 194);
            CycleA(player, 195);
            CycleA(player, 196);
            CycleA(player, 197);
            CycleA(player, 198);
            CycleA(player, 199);
            return true;
        }
        private static void CycleA(Player player, int value) { if (player.wet) CycleB(player, value + 1); }
        private static void CycleB(Player player, int value) { if (player.lavaWet) CycleA(player, value + 1); }
    }

    private sealed class SelectionHugeGlobal<T> : GlobalItem
    {
        public override bool? UseItem(Item item, Player player) { SelectionSharedEffect(player); return true; }
    }
    private sealed class SelectionSmallGlobal : GlobalItem
    {
        public override bool? UseItem(Item item, Player player) { SelectionSharedEffect(player); return true; }
    }
    private static void SelectionSharedEffect(Player player) => player.lifeRegen += 19;

    private sealed class SelectionLargeItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            SelectionSourceExecutions++;
            if (player.wet && player.statLife > player.statLifeMax2 / 2)
            {
                player.statDefense += 1;
                player.statDefense += 2;
                player.statDefense += 3;
                player.statDefense += 4;
                player.statDefense += 5;
                player.statDefense += 6;
                player.statDefense += 7;
                player.statDefense += 8;
                player.statDefense += 9;
                player.statDefense += 10;
                player.statDefense += 11;
                player.statDefense += 12;
                player.statDefense += 13;
                player.statDefense += 14;
                player.statDefense += 15;
                player.statDefense += 16;
                player.statDefense += 17;
                player.statDefense += 18;
                player.statDefense += 19;
                player.statDefense += 20;
                player.statDefense += 21;
                player.statDefense += 22;
                player.statDefense += 23;
                player.statDefense += 24;
                player.statDefense += 25;
                player.statDefense += 26;
                player.statDefense += 27;
                player.statDefense += 28;
                player.statDefense += 29;
                player.statDefense += 30;
                player.statDefense += 31;
                player.statDefense += 32;
                player.statDefense += 33;
                player.statDefense += 34;
                player.statDefense += 35;
                player.statDefense += 36;
                player.statDefense += 37;
                player.statDefense += 38;
                player.statDefense += 39;
                player.statDefense += 40;
                player.statDefense += 41;
                player.statDefense += 42;
                player.statDefense += 43;
                player.statDefense += 44;
                player.statDefense += 45;
                player.statDefense += 46;
                player.statDefense += 47;
                player.statDefense += 48;
                player.statDefense += 49;
                player.statDefense += 50;
                player.statDefense += 51;
                player.statDefense += 52;
                player.statDefense += 53;
                player.statDefense += 54;
                player.statDefense += 55;
                player.statDefense += 56;
                player.statDefense += 57;
                player.statDefense += 58;
                player.statDefense += 59;
                player.statDefense += 60;
                player.statDefense += 61;
                player.statDefense += 62;
                player.statDefense += 63;
                player.statDefense += 64;
                player.statDefense += 65;
                player.statDefense += 66;
                player.statDefense += 67;
                player.statDefense += 68;
                player.statDefense += 69;
                player.statDefense += 70;
                player.statDefense += 71;
                player.statDefense += 72;
                player.statDefense += 73;
                player.statDefense += 74;
                player.statDefense += 75;
                player.statDefense += 76;
                player.statDefense += 77;
                player.statDefense += 78;
                player.statDefense += 79;
                player.statDefense += 80;
                player.statDefense += 81;
                player.statDefense += 82;
                player.statDefense += 83;
                player.statDefense += 84;
                player.statDefense += 85;
                player.statDefense += 86;
                player.statDefense += 87;
                player.statDefense += 88;
                player.statDefense += 89;
                player.statDefense += 90;
                player.statDefense += 91;
                player.statDefense += 92;
                player.statDefense += 93;
                player.statDefense += 94;
                player.statDefense += 95;
                player.statDefense += 96;
                LateHelper(player);
            }
            return true;
        }
        private static void LateHelper(Player player) => player.lifeRegen += 11;
    }

    private static JsonObject SelectionCapture(Type item, int noise = 0, Type? consumer = null, Type? extraGlobal = null, Type[]? extraGlobals = null, Action<object>? inspect = null)
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        Type itemType = typeof(GeneratorClient).GetNestedType("SourceGraphItem", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        graphType.GetField("rosterRead", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(graph, true);
        if (consumer is not null)
            ((IList)graphType.GetField("consumers", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(graph)!)
                .Add((consumer, typeof(ModPlayer)));
        // Distinct closed generic source owners exercise the loaded-roster
        // cardinality without generating or executing gameplay code.
        Type[] tags = { typeof(int), typeof(long), typeof(float), typeof(double), typeof(byte), typeof(short), typeof(bool), typeof(char) };
        Type Noise(int index)
        {
            Type tag = tags[index % tags.Length];
            for (int n = 0; n < index / tags.Length; n++) tag = typeof(Tuple<>).MakeGenericType(tag);
            return typeof(SelectionNoise<>).MakeGenericType(tag);
        }
        object input = Activator.CreateInstance(itemType, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
            binder: null, args: new object?[] { item, Enumerable.Range(0, noise).Select(Noise).Concat(extraGlobal is null ? Type.EmptyTypes : new[] { extraGlobal }).Concat(extraGlobals ?? Type.EmptyTypes).ToArray(), false, 0, 0, null, Type.EmptyTypes, false }, culture: null)!;
        graphType.GetMethod("Item", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, new[] { input });
        var result = (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
        inspect?.Invoke(graph);
        return result;
    }

    private static JsonObject? SelectionNode(JsonObject graph, string name)
        => graph["nodes"]!.AsArray().OfType<JsonObject>().FirstOrDefault(row =>
            graph["members"]![row["method"]!.GetValue<int>()]!["name"]!.GetValue<string>().Contains(name, StringComparison.Ordinal));

    private static void ParentSourceGraphPrioritizesCausalPathsOverGeneralHooks()
    {
        SelectionSourceExecutions = 0;
        JsonObject plain = SelectionCapture(typeof(SelectionItem));
        JsonObject crowded = SelectionCapture(typeof(SelectionItem), 80);
        foreach (string name in new[] { "SelectionItem.UseItem(", "SelectionItem.First(", "SelectionItem.Second(" })
        {
            Equal(true, SelectionNode(plain, name)?["values"] is JsonObject, "uncrowded causal body is present: " + name);
            Equal(true, SelectionNode(crowded, name)?["values"] is JsonObject, "general hooks cannot evict a causal body: " + name);
        }
        Equal(0, SelectionSourceExecutions, "source selection never invokes root/helper/global hooks");
        Equal(true, crowded["omittedNodeCount"]!.GetValue<int>() > 0, "excluded dispatch candidates are counted");
        AssertSelectionReferences(crowded);
        Equal(crowded.ToJsonString(), SelectionCapture(typeof(SelectionItem), 80).ToJsonString(), "selection is deterministic for an identical roster");
    }

    private static void ParentSourceGraphDiscoversBeforeExportAndPreservesGuards()
    {
        SelectionSourceExecutions = 0;
        JsonObject graph = SelectionCapture(typeof(SelectionLargeItem));
        JsonObject root = SelectionNode(graph, "SelectionLargeItem.UseItem(")!;
        Equal(true, root["omittedStatementCount"] is JsonValue, "large source requires a bounded export slice");
        Equal(true, SelectionNode(graph, "SelectionLargeItem.LateHelper(")?["values"] is JsonObject,
            "a helper after many writes is discovered independently of the caller's export bound");
        string[] sourceMembers = root["values"]!.AsObject().Select(value => value.Value?[1]).OfType<JsonObject>()
            .Where(value => value["member"] is JsonValue).Select(value => graph["members"]![value["member"]!.GetValue<int>()]!["name"]!.GetValue<string>()).ToArray();
        Equal(true, sourceMembers.Any(name => name.EndsWith(".wet", StringComparison.Ordinal)), "selected effect retains wet gate");
        Equal(true, sourceMembers.Any(name => name.EndsWith(".statLife", StringComparison.Ordinal)), "selected effect retains life gate");
        Equal(false, root["unresolvedEnclosingBranchCount"] is JsonValue, "small complete gates are not discarded to satisfy character budget");
        var values = root["values"]!.AsObject();
        var call = values.First(value => value.Value?[1] is JsonObject operand && operand["member"] is JsonNode member
            && graph["members"]![member.GetValue<int>()]!["name"]!.GetValue<string>().Contains(".LateHelper(", StringComparison.Ordinal));
        int callBlock = call.Value![3]!.GetValue<int>();
        var block = root["blocks"]!.AsArray().OfType<JsonArray>().Single(value => value[0]!.GetValue<int>() == callBlock);
        var seen = new System.Collections.Generic.HashSet<string>();
        var work = new System.Collections.Generic.Stack<string>(block[3]!.AsArray().Select(value => value!.GetValue<string>()));
        while (work.Count > 0)
        {
            string id = work.Pop();
            if (!seen.Add(id)) continue;
            foreach (var input in values[id]![2]!.AsArray()) work.Push(input!.GetValue<string>());
            // A short-circuit condition can reach this guard through a local
            // or stack phi. Its alternatives carry their own block guards.
            int definitionBlock = values[id]![3]!.GetValue<int>();
            foreach (var guard in root["blocks"]!.AsArray().OfType<JsonArray>()
                .Single(row => row[0]!.GetValue<int>() == definitionBlock)[3]!.AsArray())
                work.Push(guard!.GetValue<string>());
        }
        string[] guards = seen.Select(id => values[id]?[1]).OfType<JsonObject>().Where(operand => operand["member"] is JsonNode)
            .Select(operand => graph["members"]![operand["member"]!.GetValue<int>()]!["name"]!.GetValue<string>()).ToArray();
        Equal(true, guards.Any(name => name.EndsWith(".wet", StringComparison.Ordinal))
            && guards.Any(name => name.EndsWith(".statLife", StringComparison.Ordinal)), "wet/life gates control the retained helper call, not merely another statement");
        Equal(0, SelectionSourceExecutions, "large source is never executed");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphRetainsConditionalStateConsumers()
    {
        JsonObject graph = SelectionCapture(typeof(SelectionStateItem), 80, typeof(SelectionStatePlayer), typeof(SelectionExtraGlobal));
        JsonObject consumer = SelectionNode(graph, "SelectionStatePlayer.PostUpdateEquips(")!;
        Equal(true, consumer?["values"] is JsonObject, "state-linked equipment consumer precedes unrelated globals");
        Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge => edge["kind"]?.GetValue<string>() == "registered_field_consumer_candidate"
            && edge["to"]?.GetValue<int>() == consumer!["id"]!.GetValue<int>()), "conditional consumer remains a source candidate, not a derived stat");
        string text = graph.ToJsonString();
        Equal(true, text.Contains(".Active", StringComparison.Ordinal) && text.Contains(".wet", StringComparison.Ordinal), "both state and runtime conditions are retained");
        Equal(true, text.Contains(".Extra", StringComparison.Ordinal) && text.Contains(".statManaMax2", StringComparison.Ordinal),
            "a field discovered in a deferred global expands an already focused consumer");
        AssertSelectionReferences(graph);

        JsonObject diamond = SelectionCapture(typeof(SelectionDiamondStateItem), consumer: typeof(SelectionDiamondStatePlayer));
        JsonObject diamondConsumer = SelectionNode(diamond, "SelectionDiamondStatePlayer.PostUpdateEquips(")!;
        string[] diamondMembers = diamondConsumer["values"]!.AsObject().Select(value => value.Value?[1]).OfType<JsonObject>()
            .Where(operand => operand["member"] is JsonNode)
            .Select(operand => diamond["members"]![operand["member"]!.GetValue<int>()]!["name"]!.GetValue<string>()).ToArray();
        Equal(true, diamondMembers.Any(name => name.EndsWith(".statDefense", StringComparison.Ordinal)),
            "materialized condition carries focus through a value-producing diamond to its guarded effect");
        Equal(true, diamondMembers.Any(name => name.EndsWith(".wet", StringComparison.Ordinal))
            && diamondMembers.Any(name => name.EndsWith(".lavaWet", StringComparison.Ordinal)),
            "materialized condition retains both guarded alternatives");
        Equal(false, diamondMembers.Any(name => name.EndsWith(".statManaMax2", StringComparison.Ordinal)),
            "focused control closure stops at the join before unrelated effects");
        AssertSelectionReferences(diamond);
    }

    private static void ParentSourceGraphBudgetsFanoutWithoutDroppingBodies()
    {
        JsonObject graph = SelectionCapture(typeof(SelectionFanoutItem));
        Equal(true, SelectionNode(graph, "SelectionFanoutItem.UseItem(")?["values"] is JsonObject, "edge-heavy discovery retains the root body");
        Equal(true, SelectionNode(graph, "SelectionFanoutItem.FanoutEffect(")?["values"] is JsonObject, "edge-heavy discovery retains a causally linked helper body");
        Equal(true, graph["omittedEdgeCount"]!.GetValue<int>() > 0, "edge omission is explicit and independently bounded");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphUsesAlternativeRetainedParent()
    {
        Type tag = typeof(int);
        for (int index = 0; index < 192; index++) tag = typeof(Tuple<>).MakeGenericType(tag);
        Type huge = typeof(SelectionHugeGlobal<>).MakeGenericType(tag);
        JsonObject graph = SelectionCapture(typeof(SelectionItem), extraGlobals: new[] { huge, typeof(SelectionSmallGlobal) });
        Equal(true, SelectionNode(graph, "SelectionSmallGlobal.UseItem(")?["values"] is JsonObject, "smaller general root is retained");
        Equal(true, SelectionNode(graph, ".SelectionSharedEffect(")?["values"] is JsonObject,
            "shared helper uses a retained later caller when its first oversized caller is omitted");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphKeepsCyclesRootedUnderEdgePressure()
    {
        JsonObject graph = SelectionCapture(typeof(SelectionCycleItem));
        Equal(true, SelectionNode(graph, "SelectionCycleItem.CycleA(")?["values"] is JsonObject, "cycle entry body is retained");
        Equal(true, SelectionNode(graph, "SelectionCycleItem.CycleB(")?["values"] is JsonObject, "cyclic helper body is retained");
        Equal(true, graph["omittedEdgeCount"]!.GetValue<int>() > 0, "cycle fixture reaches the edge export budget");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphRefreshesDeferredConsumerFocus()
    {
        JsonObject graph = SelectionCapture(typeof(SelectionCommonStateItem), consumer: typeof(SelectionCommonStatePlayer), extraGlobal: typeof(SelectionCommonStateGlobal));
        JsonObject consumer = SelectionNode(graph, "SelectionCommonStatePlayer.PostUpdateEquips(")!;
        Equal(true, consumer?["values"] is JsonObject, "general state consumer source is retained when there is space");
        string[] fields = consumer!["values"]!.AsObject().Select(value => value.Value?[1]).OfType<JsonObject>()
            .Where(value => value["member"] is JsonValue).Select(value => graph["members"]![value["member"]!.GetValue<int>()]!["name"]!.GetValue<string>()).ToArray();
        Equal(true, fields.Any(name => name.EndsWith(".statDefense", StringComparison.Ordinal))
            && fields.Any(name => name.EndsWith(".statManaMax2", StringComparison.Ordinal)), "a queued common-state consumer receives newly watched fields before admission");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphFollowsMutableStaticReads()
    {
        JsonObject graph = SelectionCapture(typeof(SelectionStaticReadItem), 80, typeof(SelectionStaticStatePlayer));
        JsonObject? consumer = SelectionNode(graph, "SelectionStaticStatePlayer.PostUpdate(");
        Equal(true, consumer?["values"] is JsonObject, "mutable mod static reads preserve the registered state updater before unrelated globals");
        Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge => edge["kind"]?.GetValue<string>() == "registered_field_consumer_candidate"
            && edge["to"]?.GetValue<int>() == consumer!["id"]!.GetValue<int>()), "mutable static lifecycle remains an explicit source candidate");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphCombinesDirectAndHelperStateReads()
    {
        JsonObject graph = SelectionCapture(typeof(SelectionMixedStateItem), 80, typeof(SelectionMixedStatePlayer));
        JsonObject? consumer = SelectionNode(graph, "SelectionMixedStatePlayer.PostUpdateEquips(");
        Equal(true, consumer?["values"] is JsonObject, "specific helper state gives the consumer causal priority despite a direct common-field read");
        string[] fields = consumer!["values"]!.AsObject().Select(value => value.Value?[1]).OfType<JsonObject>()
            .Where(value => value["member"] is JsonValue).Select(value => graph["members"]![value["member"]!.GetValue<int>()]!["name"]!.GetValue<string>()).ToArray();
        Equal(true, fields.Any(name => name.EndsWith(".statDefense", StringComparison.Ordinal))
            && fields.Any(name => name.EndsWith(".lifeRegen", StringComparison.Ordinal)), "direct and helper-driven branches both survive focus selection");
        Equal(true, SelectionNode(graph, "SelectionMixedStatePlayer.HasActive(")?["values"] is JsonObject, "the actual helper body remains evidence for its state condition");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphRevisitsSpecificStatePromotions()
    {
        bool inspected = false;
        JsonObject graph = SelectionCapture(typeof(SelectionPromoteItem), consumer: typeof(SelectionPromotePlayer),
            extraGlobals: new[] { typeof(SelectionPromoteBGlobal), typeof(SelectionPromoteDGlobal) }, inspect: source =>
            {
                Type type = source.GetType();
                var admitted = (System.Collections.Generic.Dictionary<string, int>)type.GetField("admitted", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(source)!;
                var priorities = (System.Collections.Generic.Dictionary<int, int>)type.GetField("priorities", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(source)!;
                var specific = (System.Collections.Generic.HashSet<FieldInfo>)type.GetField("specificState", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(source)!;
                FieldInfo b = typeof(SelectionPromotePlayer).GetField(nameof(SelectionPromotePlayer.B))!;
                Equal(true, specific.Contains(b), "the previously generic watched field becomes specific through a retained producer");
                int id = admitted.Single(entry => entry.Key.Contains("SelectionPromotePlayer.PostUpdate(", StringComparison.Ordinal)).Value;
                Equal(1, priorities[id], "specific state promotion reclassifies a consumer even when watched field count stays unchanged");
                inspected = true;
            });
        Equal(true, inspected, "priority assertion inspects the completed production graph");
        AssertSelectionReferences(graph);
    }

    private static void AssertSelectionReferences(JsonObject graph)
    {
        Equal(true, graph.ToJsonString().Length <= graph["limits"]!["characters"]!.GetValue<int>(), "complete serialized graph obeys character budget");
        JsonObject envelope = graph.DeepClone().AsObject();
        const string longestCoverage = "native_binary_or_method_certificate_unavailable";
        envelope["nativeCatalogCoverage"] = new JsonObject
        {
            ["shoot"] = longestCoverage, ["contactStatus"] = longestCoverage,
            ["equipment"] = longestCoverage, ["environment"] = longestCoverage,
        };
        Equal(true, envelope.ToJsonString().Length <= graph["limits"]!["characters"]!.GetValue<int>(),
            "the final production catalog-coverage envelope also obeys the graph budget");
        var nodes = graph["nodes"]!.AsArray(); var members = graph["members"]!.AsArray(); var modules = graph["modules"]!.AsArray();
        Equal(true, nodes.Count <= graph["limits"]!["nodes"]!.GetValue<int>(), "export node budget");
        Equal(true, graph["edges"]!.AsArray().Count <= graph["limits"]!["edges"]!.GetValue<int>(), "export edge budget");
        foreach (JsonObject row in nodes.OfType<JsonObject>())
        {
            Equal(true, row["id"]!.GetValue<int>() >= 0 && row["id"]!.GetValue<int>() < nodes.Count, "export node IDs are dense");
            Equal(true, row["method"]!.GetValue<int>() >= 0 && row["method"]!.GetValue<int>() < members.Count, "method reference is in range");
            if (row["values"] is not JsonObject values) continue;
            foreach (var statement in row["statements"]!.AsArray()) Equal(true, values.ContainsKey(statement!.GetValue<string>()), "statement reference exists");
            foreach (var block in row["blocks"]!.AsArray().OfType<JsonArray>())
            {
                if (block[2] is JsonNode branch) Equal(true, values.ContainsKey(branch.GetValue<int>().ToString(System.Globalization.CultureInfo.InvariantCulture)), "block branch reference exists");
                foreach (var guard in block[3]!.AsArray()) Equal(true, values.ContainsKey(guard!.GetValue<string>()), "enclosing guard reference exists");
            }
            foreach (var value in values)
            {
                foreach (var input in value.Value![2]!.AsArray()) Equal(true, values.ContainsKey(input!.GetValue<string>()), "source data closure is intact");
                if (value.Value?[1] is JsonObject operand && operand["member"] is JsonNode member)
                    Equal(true, member.GetValue<int>() >= 0 && member.GetValue<int>() < members.Count, "operand member reference is in range");
            }
        }
        foreach (var member in members.OfType<JsonObject>())
            Equal(true, member["module"]!.GetValue<int>() >= 0 && member["module"]!.GetValue<int>() < modules.Count, "module reference is in range");
        var reached = graph["roots"]!.AsArray().OfType<JsonObject>().Select(root => root["node"]!.GetValue<int>()).ToHashSet();
        var edges = graph["edges"]!.AsArray().OfType<JsonObject>().ToArray();
        foreach (var edge in edges)
            if (edge["from"] is null && edge["to"] is JsonNode to) reached.Add(to.GetValue<int>());
        var queue = new System.Collections.Generic.Queue<int>(reached);
        while (queue.Count > 0)
        {
            int source = queue.Dequeue();
            foreach (var edge in edges)
                if (edge["from"]?.GetValue<int>() == source && edge["to"] is JsonNode to && reached.Add(to.GetValue<int>())) queue.Enqueue(to.GetValue<int>());
        }
        Equal(nodes.Count, reached.Count, "every exported node is reachable from a retained dispatch/field root, including cycles");
        foreach (var root in graph["roots"]!.AsArray().OfType<JsonObject>())
            Equal(true, root["node"]!.GetValue<int>() >= 0 && root["node"]!.GetValue<int>() < nodes.Count, "root node reference is in range");
        foreach (var edge in graph["edges"]!.AsArray().OfType<JsonObject>())
        {
            foreach (string key in new[] { "from", "to" })
                if (edge[key] is JsonNode id) Equal(true, id.GetValue<int>() >= 0 && id.GetValue<int>() < nodes.Count, "edge reference is in range");
            if (edge["context"] is JsonArray arguments && edge["from"] is JsonNode from && edge["sourceCoverage"] is null
                && edge["kind"]?.GetValue<string>() is "helper_source" or "declared_virtual_helper_candidate")
                foreach (var argument in arguments)
                    Equal(true, nodes[from.GetValue<int>()]!["values"]!.AsObject().ContainsKey(argument!.GetValue<string>()), "helper call argument is retained or explicitly marked omitted");
        }
    }
}
