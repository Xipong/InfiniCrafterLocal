using System;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private const BindingFlags TestInstance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

    // Association only: no native defaults, normalization, hydration, prefix or
    // new optional fields. Legacy/unhydrated cases supply their exact objects.
    private static T AttachItem<T>(T generated, Item item, GeneratedItemData data) where T : GeneratedItem
    {
        typeof(ModType<Item>).GetProperty("Entity", TestInstance)!.SetValue(generated, item);
        typeof(Item).GetProperty("ModItem", TestInstance)!.SetValue(item, generated);
        typeof(GeneratedItem).GetProperty("Data", TestInstance)!.SetValue(generated, data);
        return generated;
    }

    // Restore both array identity and entries: some consumers replace a whole
    // array, others reuse a slot. No actors or gameplay fields are manufactured.
    private sealed class NativeActorState : IDisposable
    {
        private readonly Player[] players = Terraria.Main.player, savedPlayers = (Player[])Terraria.Main.player.Clone();
        private readonly NPC[] npcs = Terraria.Main.npc, savedNpcs = (NPC[])Terraria.Main.npc.Clone();
        private readonly Projectile[] projectiles = Terraria.Main.projectile, savedProjectiles = (Projectile[])Terraria.Main.projectile.Clone();
        private readonly int mode = Terraria.Main.netMode, local = Terraria.Main.myPlayer;
        private readonly bool dedicated = Terraria.Main.dedServ;
        private readonly uint tick = Terraria.Main.GameUpdateCount;
        private readonly Terraria.Utilities.UnifiedRandom random = Terraria.Main.rand;
        private readonly bool goodWorld = Terraria.Main.getGoodWorld;
        private readonly SceneMetrics metrics = Terraria.Main.SceneMetrics;
        public void Dispose()
        {
            RuntimeDelayedActionScheduler.Clear(); RuntimeHitPullBridge.Clear();
            Array.Copy(savedPlayers, players, players.Length); Array.Copy(savedNpcs, npcs, npcs.Length); Array.Copy(savedProjectiles, projectiles, projectiles.Length);
            Terraria.Main.player = players; Terraria.Main.npc = npcs; Terraria.Main.projectile = projectiles;
            Terraria.Main.netMode = mode; Terraria.Main.myPlayer = local; Terraria.Main.dedServ = dedicated; MaterialClock(tick);
            Terraria.Main.rand = random; Terraria.Main.getGoodWorld = goodWorld; Terraria.Main.SceneMetrics = metrics;
        }
    }

    private sealed class NativeItemPoolState : IDisposable
    {
        private readonly Item[] items = Terraria.Main.item;
        private readonly int[] timers = Terraria.Main.timeItemSlotCannotBeReusedFor;
        private readonly CombatText[] combat = Terraria.Main.combatText;
        private readonly int mode = Terraria.Main.netMode;
        private readonly bool inventory = Terraria.Main.playerInventory, generating = Terraria.WorldGen.gen;
        public void Dispose()
        {
            Terraria.Main.item = items; Terraria.Main.timeItemSlotCannotBeReusedFor = timers; Terraria.Main.combatText = combat;
            Terraria.Main.netMode = mode; Terraria.Main.playerInventory = inventory; Terraria.WorldGen.gen = generating;
        }
    }

    // Constructor-bypassed CPU shells. Each caller still owns its flush hook,
    // queue capacity, Begin/End and drain/resource-lifetime assertions.
    private static MethodInfo NativeProjectileEntry() => typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect),
        new[] { typeof(Terraria.DataStructures.IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int),
            typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!;

    private static SpriteBatch CpuSpriteBatch(int capacity)
    {
        var batch = (SpriteBatch)RuntimeHelpers.GetUninitializedObject(typeof(SpriteBatch));
        GC.SuppressFinalize(batch);
        foreach (string name in new[] { "vertexInfo", "textureInfo", "spriteInfos", "sortedSpriteInfos" })
        {
            var field = typeof(SpriteBatch).GetField(name, TestInstance)!;
            field.SetValue(batch, Array.CreateInstance(field.FieldType.GetElementType()!, capacity));
        }
        return batch;
    }
    private static Texture2D CpuTexture(int width, int height)
    {
        var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
        GC.SuppressFinalize(texture);
        typeof(Texture2D).GetProperty("Width")!.SetValue(texture, width);
        typeof(Texture2D).GetProperty("Height")!.SetValue(texture, height);
        return texture;
    }

    private sealed class BorrowedSpriteCache : IDisposable
    {
        internal readonly InfiniCrafterLocal.Common.Services.RuntimeSpriteCache Cache = new();
        internal readonly System.Collections.IDictionary Textures;
        internal readonly Type Record;
        private readonly PropertyInfo sprites = typeof(InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
        private readonly object? previous;
        internal BorrowedSpriteCache()
        {
            previous = sprites.GetValue(null);
            Textures = (System.Collections.IDictionary)Cache.GetType().GetField("_textures", TestInstance)!.GetValue(Cache)!;
            Record = Cache.GetType().GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            sprites.SetValue(null, Cache);
        }
        public void Dispose()
        {
            // Borrowed CPU shells have no GraphicsDevice. Clear associations
            // before disposing only the cache owner, never a queued GPU texture.
            Textures.Clear(); Cache.Dispose(); sprites.SetValue(null, previous);
        }
    }

    private static T[] CpuVertexValues<T>(object value)
    {
        var result = new System.Collections.Generic.List<T>();
        void Visit(object current)
        {
            if (current is T typed) { result.Add(typed); return; }
            foreach (var field in current.GetType().GetFields(TestInstance))
                if (field.FieldType == typeof(T) || field.FieldType.IsValueType && !field.FieldType.IsPrimitive && !field.FieldType.IsEnum)
                    Visit(field.GetValue(current)!);
        }
        Visit(value); return result.ToArray();
    }

    private static void SpriteGpuBoundaries(Action<MonoMod.RuntimeDetour.ILHook> add,
        Action<Texture2D, Color[]> read, Action<Texture2D, Color[]> upload, Action<GraphicsResource> dispose)
    {
        foreach (var method in typeof(InfiniCrafterLocal.Common.Services.RuntimeSpriteCache).GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly))
            add(new MonoMod.RuntimeDetour.ILHook(method, il => {
                var cursor = new MonoMod.Cil.ILCursor(il);
                while (cursor.TryGotoNext(i => i.Operand is Mono.Cecil.MethodReference m &&
                    ((m.DeclaringType.FullName == typeof(Texture2D).FullName && (m.Name == "GetData" || m.Name == "SetData") && m.Parameters.Count == 1)
                    || (m.Name == "Dispose" && m.Parameters.Count == 0 && m.DeclaringType.FullName == typeof(GraphicsResource).FullName)))) {
                    string name = ((Mono.Cecil.MethodReference)cursor.Next!.Operand).Name; cursor.Remove();
                    if (name == "Dispose") cursor.EmitDelegate<Action<GraphicsResource>>(dispose);
                    else cursor.EmitDelegate<Action<Texture2D, Color[]>>(name == "GetData" ? read : upload);
                }
            }));
    }

    private static ReLogic.Content.Asset<Texture2D> CpuTextureAsset(Texture2D texture)
    {
        var asset = (ReLogic.Content.Asset<Texture2D>)RuntimeHelpers.GetUninitializedObject(typeof(ReLogic.Content.Asset<Texture2D>));
        foreach (var field in asset.GetType().GetFields(TestInstance))
            if (field.FieldType == typeof(Texture2D)) field.SetValue(asset, texture);
        asset.GetType().GetProperty("State")!.SetValue(asset, ReLogic.Content.AssetState.Loaded);
        return asset;
    }

    private static byte[] PlacementPacket(bool intent, ulong sequence, int x, int y, byte layer = 2,
        bool includePacketId = false, int? version = null, ulong retiredSequence = 0)
    {
        using var stream = new System.IO.MemoryStream();
        using (var writer = new System.IO.BinaryWriter(stream, System.Text.Encoding.UTF8, true))
        {
            if (includePacketId) writer.Write(intent ? InfiniCrafterLocal.Common.InfiniNetPacketIds.RequestGeneratedPlacementIntent : InfiniCrafterLocal.Common.InfiniNetPacketIds.NotifyGeneratedPlacement);
            writer.Write(version ?? (int)typeof(InfiniCrafterLocal.Common.Systems.GeneratedPlacementLedgerSystem).GetField("PlacementProtocolVersion", PersistenceStatic)!.GetRawConstantValue()!);
            writer.Write(sequence); writer.Write(intent ? (byte)0 : layer); writer.Write(x); writer.Write(y);
            if (intent) writer.Write(retiredSequence);
        }
        return stream.ToArray();
    }
    private static void ReceivePlacementPacket(bool intent, ulong sequence, int x = 40, int y = 40, byte layer = 2)
    {
        using var reader = new System.IO.BinaryReader(new System.IO.MemoryStream(PlacementPacket(intent, sequence, x, y, layer)));
        if (intent) InfiniCrafterLocal.Common.Systems.GeneratedPlacementLedgerSystem.HandlePlacementIntentPacket(reader, 0);
        else InfiniCrafterLocal.Common.Systems.GeneratedPlacementLedgerSystem.HandlePlacementPacket(reader, 0);
    }

    // Set precisely the fields supplied by a case, not a second craft state
    // model. Primary total/animation clocks and extra elapsed clock differ.
    private static object CraftLane(InfiniCraftPlayer owner, int lane, params (string Primary, string Extra, object? Value)[] fields)
    {
        if (lane == 0)
        {
            foreach (var field in fields) typeof(InfiniCraftPlayer).GetField(field.Primary, CraftFields)!.SetValue(owner, field.Value);
            return owner;
        }
        var type = typeof(InfiniCraftPlayer).GetNestedType("MultiDevCraftJob", BindingFlags.NonPublic)!;
        object job = Activator.CreateInstance(type, nonPublic: true)!;
        type.GetField("LaneIndex", CraftFields)!.SetValue(job, lane);
        foreach (var field in fields) type.GetField(field.Extra, CraftFields)!.SetValue(job, field.Value);
        ((Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", CraftFields)!.GetValue(owner)!).SetValue(job, lane - 1);
        return job;
    }
}
