using System;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Native CPU world/player initialization. No update, buff, movement, resource,
    // or collision implementation is replaced. Rendering objects have no GPU.
    private static void WPrepareFullWorld()
    {
        Terraria.Main.maxTilesY = 600;
        Terraria.Main.tile = (Tilemap)Activator.CreateInstance(typeof(Tilemap), PersistenceInstance,
            null, new object[] { (ushort)100, (ushort)600 }, null)!;
        Terraria.Main.worldSurface = 80;
        Terraria.Main.rockLayer = 200;
        Terraria.Main.leftWorld = Terraria.Main.topWorld = 0;
        Terraria.Main.rightWorld = 1600;
        Terraria.Main.bottomWorld = 9600;
    }

    private static void WPrepareFullPlayer(Player owner, InfiniCraftPlayer modPlayer, int manaCrystals)
    {
        owner.isControlledByFilm = true; // Native scripted-control source; not keyboard input.
        Terraria.GameContent.Creative.CreativePowerManager.Initialize();
        Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1).Select(_ => new Item()).ToArray();
        Terraria.Main.dust = Enumerable.Range(0, Terraria.Main.maxDust + 1).Select(_ => new Dust()).ToArray();
        Terraria.GameInput.PlayerInput.Triggers.Initialize();
        Terraria.Main.autoSave = false; // This isolated temporary world is never persisted.
        Terraria.Main.instance = (Terraria.Main)RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Main));
        typeof(Terraria.Main).GetField("_achievements", TestInstance)!
            .SetValue(Terraria.Main.instance, new Terraria.Achievements.AchievementManager());
        Terraria.Initializers.AchievementInitializer.Load();
        foreach (string key in new[] { "Stardust", "Nebula", "Vortex", "Solar", "MoonLord", "BloodMoon", "Blizzard",
            "HeatDistortion", "Graveyard", "Sepia", "WaterDistortion", "Sandstorm" })
            Terraria.Graphics.Effects.Filters.Scene[key] = new Terraria.Graphics.Effects.Filter(
                new Terraria.Graphics.Shaders.ScreenShaderData("headless-no-render"), Terraria.Graphics.Effects.EffectPriority.Low);
        Terraria.Main.WaveQuality = 0;
        typeof(PlayerLoader).GetMethod("Add", PersistenceStatic)!.Invoke(null, new object[] { modPlayer });
        var slots = new Terraria.ModLoader.Default.ModAccessorySlotPlayer();
        typeof(ModType<Player>).GetProperty("Entity", TestInstance)!.SetValue(slots, owner);
        typeof(ContentInstance<Terraria.ModLoader.Default.ModAccessorySlotPlayer>).GetProperty("Instance")!.SetValue(null, slots);
        typeof(PlayerLoader).GetMethod("Add", PersistenceStatic)!.Invoke(null, new object[] { slots });
        typeof(Player).GetField("modPlayers", TestInstance)!.SetValue(owner, new ModPlayer[] { modPlayer, slots });
        typeof(ExtraJumpLoader).GetMethod("ResizeArrays", PersistenceStatic)!.Invoke(null, null);
        typeof(PlayerLoader).GetMethod("ResizeArrays", PersistenceStatic)!.Invoke(null, null);
        modPlayer.Initialize();
        slots.Initialize();
        owner.fallStart = (int)(owner.position.Y / 16f); // Native spawn fall-distance origin.
        owner.ownedProjectileCounts = new int[ProjectileLoader.ProjectileCount];
        owner.ConsumedManaCrystals = manaCrystals;
    }

    private static int WBuffTicks(Player owner) => (int)typeof(InfiniCraftPlayer)
        .GetField("_generatedBuffTicks", TestInstance)!.GetValue(owner.GetModPlayer<InfiniCraftPlayer>())!;
}
