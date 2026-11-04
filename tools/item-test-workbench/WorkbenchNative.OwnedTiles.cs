using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Tiles;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ObjectData;

internal static partial class EngineRuntimeChecks
{
    // The partial graphics host loads only this production content owner. Mod.AddContent
    // allocates genuine mod tile IDs; neither the resolver nor a vanilla tile is replaced.
    // Tile registration is scoped even though the CLI normally runs one scene per process.
    private sealed class WOwnedTileRegistration : IDisposable
    {
        private readonly Mod mod = new InfiniCrafterLocalMod();
        private readonly int previousCount=TileLoader.TileCount;
        private readonly object? previousLoaded=typeof(TileLoader).GetField("loaded",PersistenceStatic)!.GetValue(null);
        private readonly IList<ModTile> nativeTiles=(IList<ModTile>)typeof(TileLoader).GetField("tiles",PersistenceStatic)!.GetValue(null)!;
        private readonly Dictionary<string,ModTile> lookup=(Dictionary<string,ModTile>)typeof(ModTypeLookup<ModTile>).GetField("dict",PersistenceStatic)!.GetValue(null)!;
        private readonly Dictionary<string,Dictionary<string,ModTile>> tiered=(Dictionary<string,Dictionary<string,ModTile>>)typeof(ModTypeLookup<ModTile>).GetField("tieredDict",PersistenceStatic)!.GetValue(null)!;
        private readonly IDictionary<string,Mod> mods=(IDictionary<string,Mod>)typeof(ModLoader).GetField("modsByName",PersistenceStatic)!.GetValue(null)!;
        private readonly Mod? previousMod;
        private readonly IList<TileObjectData>? previousData=(IList<TileObjectData>?)typeof(TileObjectData).GetField("_data",PersistenceStatic)!.GetValue(null);
        private readonly TileObjectData[]? previousRows;
        private bool resized,disposed;
        internal WOwnedTileRegistration()
        {
            if(previousCount!=TileID.Count || GeneratedOwnedTiles.Resolve("GeneratedOwned_1x1_open_floor")>=0)
                throw new InvalidOperationException("Partial owned tile bootstrap requires no existing mod tile registrations");
            previousRows=previousData?.ToArray();
            string root = Environment.GetEnvironmentVariable("INFINI_MOD_SOURCE_ROOT")
                ?? Path.Combine(AppContext.BaseDirectory,"native-mod");
            WNativeLoader.PrepareSourceMod(mod,typeof(InfiniCrafterLocalMod).Assembly,root,Terraria.Program.SavePath,true);
            mods.TryGetValue(mod.Name,out previousMod);mods[mod.Name]=mod;
            var loading = typeof(Mod).GetField("loading",PersistenceInstance)!;
            loading.SetValue(mod,true);
            try { GeneratedOwnedTiles.Register(mod); }
            catch { Dispose();throw; }
            finally { loading.SetValue(mod,false); }
        }
        internal int Setup()
        {
            resized=true;
            foreach (var tile in mod.GetContent<GeneratedOwnedTile>()) tile.SetupContent();
            return WCheckOwnedTileRegistrations(mod);
        }
        public void Dispose()
        {
            if(disposed)return;disposed=true;
            // Undo only actual registrations owned by this scope. No success path
            // installs fake tiles or edits the production symbolic registry.
            foreach(var tile in mod.GetContent<GeneratedOwnedTile>().ToArray()) {
                nativeTiles.Remove(tile);lookup.Remove(tile.FullName);
                if(tiered.TryGetValue(mod.Name,out var names)) {
                    names.Remove(tile.Name);if(names.Count==0)tiered.Remove(mod.Name);
                }
            }
            typeof(TileLoader).GetField("nextTile",PersistenceStatic)!.SetValue(null,previousCount);
            GeneratedOwnedTiles.Clear();
            if(resized) {
                SetFactory.ResizeArrays(true);
                typeof(TileLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,new object[]{true});
            }
            typeof(TileLoader).GetField("loaded",PersistenceStatic)!.SetValue(null,previousLoaded);
            if(previousData is not null) {previousData.Clear();foreach(var row in previousRows!)previousData.Add(row);}
            typeof(TileObjectData).GetField("_data",PersistenceStatic)!.SetValue(null,previousData);
            if(previousMod is null)mods.Remove(mod.Name);else mods[mod.Name]=previousMod;
            mod.Assets?.Dispose();
            if(TileLoader.TileCount!=previousCount || nativeTiles.Count!=0
                || GeneratedOwnedTiles.Resolve("GeneratedOwned_1x1_open_floor")>=0)
                throw new InvalidOperationException("Owned tile registration leaked after scope disposal");
        }
    }

    internal static void CheckWorkbenchOwnedRegistration()
    {
        Terraria.Main.SceneMetrics=new SceneMetrics();
        var field=typeof(Terraria.Main).GetField("PylonSystem",PersistenceStatic)!;
        if(field.GetValue(null) is null)field.SetValue(null,Activator.CreateInstance(field.FieldType));
        var pylons=field.GetValue(null)!;
        var metrics=pylons.GetType().GetField("_sceneMetrics",TestInstance)!;
        if(metrics.GetValue(pylons) is null)metrics.SetValue(pylons,new SceneMetrics());
        WInitializeNestedStatics(typeof(TileID));
        TileObjectData.Initialize();
        object? initial=typeof(TileObjectData).GetField("_data",PersistenceStatic)!.GetValue(null);
        int initialCount=TileLoader.TileCount;
        for(int attempt=0;attempt<2;attempt++) {
            using(var registration=new WOwnedTileRegistration()) {
                SetFactory.ResizeArrays(false);
                typeof(TileLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,new object[]{false});
                registration.Setup();
                if(TileLoader.TileCount!=initialCount+1536)throw new InvalidOperationException("Duplicate owned registrations");
            }
            if(TileLoader.TileCount!=initialCount || !ReferenceEquals(initial,typeof(TileObjectData).GetField("_data",PersistenceStatic)!.GetValue(null))
                || ModContent.TryFind<ModTile>("InfiniCrafterLocal/GeneratedOwned_1x1_open_floor",out _))
                throw new InvalidOperationException("Owned native registry or TileObjectData leaked across repeated scopes");
        }
        Console.WriteLine("PASS: two complete production owned tile registrations and disposals restore native count, lookup, TileObjectData and symbolic resolver");
    }

    private static RuntimeOwnedTileSpec WOwnedShapeForKey(string key)
    {
        string[] parts=key.Split('_');
        string[] size=parts.Length==4?parts[1].Split('x'):Array.Empty<string>();
        if(parts.Length!=4 || parts[0]!="GeneratedOwned" || size.Length!=2
            || !int.TryParse(size[0],NumberStyles.None,CultureInfo.InvariantCulture,out int width)
            || !int.TryParse(size[1],NumberStyles.None,CultureInfo.InvariantCulture,out int height))
            throw new ArgumentException("ownedTileKey must name an exact registered owned structure");
        var shape=new RuntimeOwnedTileSpec { Width=width,Height=height,Collision=parts[2],Support=parts[3] };
        try { shape.Validate(); }
        catch(InvalidDataException ex) { throw new ArgumentException("Invalid ownedTileKey structure",ex); }
        if(shape.Key!=key)throw new ArgumentException("ownedTileKey must use the canonical symbolic name");
        return shape;
    }

    private static int WCheckOwnedTileRegistrations(Mod mod)
    {
        var tiles=mod.GetContent<GeneratedOwnedTile>().ToArray();
        if(tiles.Length!=1536 || tiles.Select(t=>t.Name).Distinct(StringComparer.Ordinal).Count()!=1536)
            throw new InvalidOperationException("Production owned tile registration is incomplete");
        foreach(var tile in tiles) {
            var shape=WOwnedShapeForKey(tile.Name);
            var data=TileObjectData.GetTileData(tile.Type,0);
            if(tile.Type<TileID.Count || !ReferenceEquals(TileLoader.GetTile(tile.Type),tile)
                || GeneratedOwnedTiles.Resolve(tile.Name)!=tile.Type || data is null
                || data.Width!=shape.Width || data.Height!=shape.Height
                || Terraria.Main.tileSolid[tile.Type]!=(shape.Collision=="solid")
                || Terraria.Main.tileNoSunLight[tile.Type]!=(shape.Collision=="solid")
                || !Terraria.Main.tileFrameImportant[tile.Type] || !Terraria.Main.tileNoAttach[tile.Type]
                || data.AnchorBottom.tileCount!=(shape.Support=="floor"?shape.Width:0)
                || data.AnchorWall!=(shape.Support=="wall")
                || tile.PreDraw(0,0,null!) || tile.Slope(0,0) || tile.GetItemDrops(0,0).Any())
                throw new InvalidOperationException("Owned native registration differs from authored structure: "+tile.Name);
        }
        return tiles.Length;
    }
}
