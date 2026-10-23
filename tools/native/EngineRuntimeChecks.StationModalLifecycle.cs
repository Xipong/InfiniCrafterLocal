#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks { private static void StationModalLifecycle() {
var type = typeof(InfiniCraftStationUISystem);
        type.GetField("_pickerSlot", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!.SetValue(null, 0);
        type.GetField("_pickerSearchFocus", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!.SetValue(null, true);
        Terraria.Main.blockInput = true; Terraria.GameInput.PlayerInput.WritingText = true;
        Equal(true, InfiniCraftStationUISystem.StationModalVisible, "Picker owns station modal routing.");
        var mouse = (Terraria.Main.mouseLeft, Terraria.Main.mouseLeftRelease, Terraria.Main.mouseRight, Terraria.Main.mouseRightRelease);
        Terraria.Main.mouseLeft = Terraria.Main.mouseLeftRelease = Terraria.Main.mouseRight = Terraria.Main.mouseRightRelease = true;
        InfiniCraftStationUISystem.ReserveStationModalMouse();
        Equal(false, Terraria.Main.mouseLeft && Terraria.Main.mouseLeftRelease, "native inventory left-click condition is suppressed before draw");
        Equal(false, Terraria.Main.mouseRight && Terraria.Main.mouseRightRelease, "native right-click suppressed");
        Equal(true, InfiniCraftStationUISystem.RestoreStationModalMouse(), "modal receives reserved click after native inventory");
        Equal(true, Terraria.Main.mouseLeft && Terraria.Main.mouseLeftRelease, "modal retains exact original click");
        Equal(false, InfiniCraftStationUISystem.RestoreStationModalMouse(), "reserved input cannot replay twice");
        (Terraria.Main.mouseLeft, Terraria.Main.mouseLeftRelease, Terraria.Main.mouseRight, Terraria.Main.mouseRightRelease) = mouse;
        InfiniCraftStationUISystem.CloseStationModals();
        InfiniCraftStationUISystem.ReserveStationModalMouse();
        Equal(false, InfiniCraftStationUISystem.RestoreStationModalMouse(), "input outside station stays native");
        InfiniCraftStationUISystem.ReserveStationModalMouse(stationPanelHit: true);
        Equal(true, InfiniCraftStationUISystem.RestoreStationModalMouse(), "overlapping visible station gets pre-native protection");
        Equal(true, !InfiniCraftStationUISystem.StationModalVisible && !Terraria.Main.blockInput
            && !Terraria.GameInput.PlayerInput.WritingText, "Closing releases only picker-owned text focus and all modal state.");
        Equal(true, !InfiniCraftStationUISystem.StationInteractionAvailable(null), "Missing player cannot interact.");
} }
