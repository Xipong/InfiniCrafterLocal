using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Security.Cryptography;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace IFCWorkbenchDriver;

// Normal tModLoader content. No IFC or third-party classes are enumerated or
// registered here; all mod content is loaded by tModLoader before world entry.
public sealed class WorkbenchSystem : ModSystem
{
    internal static WorkbenchRun? Run;
    private static bool _enabled;
    private static bool _sandboxVerified;
    private static string? _sandbox, _output, _scenario, _token;

    public override void OnWorldLoad()
    {
        _enabled = Environment.GetEnvironmentVariable("IFC_WORKBENCH_ENABLED") == "1";
        _sandboxVerified = false;
        if (!_enabled) return;
        try
        {
            _sandbox = FullEnvironmentPath("IFC_WORKBENCH_SANDBOX");
            _scenario = FullEnvironmentPath("IFC_WORKBENCH_SCENARIO");
            _output = FullEnvironmentPath("IFC_WORKBENCH_OUTPUT");
            _token = Environment.GetEnvironmentVariable("IFC_WORKBENCH_TOKEN");
            ValidateSandbox(); // Must precede all world and player mutations.
            _sandboxVerified = true;
            byte[] scenarioBytes = File.ReadAllBytes(_scenario!);
            if (scenarioBytes.Length > 1024 * 1024) throw new InvalidDataException("Scenario exceeds 1 MiB");
            var request = JsonSerializer.Deserialize<WorkbenchRequest>(scenarioBytes, JsonOptions())
                ?? throw new InvalidDataException("Empty scenario");
            Run = new WorkbenchRun(request, _output!, Convert.ToHexString(SHA256.HashData(scenarioBytes)).ToLowerInvariant());
        }
        catch (Exception e)
        {
            // Only write into a verified sandbox; never trust an arbitrary output path.
            if (_sandboxVerified && _output != null)
                Write(_output, new { status = "error", error = e.Message, scope = "No scene was started" });
            _enabled = false;
        }
    }

    public override void PostUpdateEverything()
    {
        if (!_enabled || Run == null) return;
        try { Run.Tick(); }
        catch (Exception e) { Run.Finish("error", e.ToString()); _enabled = false; }
    }

    public override void OnWorldUnload()
    {
        if (Run != null && !Run.Completed) Run.Finish("error", "World unloaded before the scenario completed");
        Run = null;
        _enabled = false;
    }

    private static string FullEnvironmentPath(string name)
    {
        string value = Environment.GetEnvironmentVariable(name) ?? throw new InvalidDataException(name + " is required");
        if (!Path.IsPathFullyQualified(value)) throw new InvalidDataException(name + " must be absolute");
        return Path.GetFullPath(value);
    }

    private static bool IsInside(string root, string path)
    {
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        string prefix = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root)) + Path.DirectorySeparatorChar;
        return Path.GetFullPath(path).StartsWith(prefix, comparison);
    }

    private static void ValidateSandbox()
    {
        if (string.IsNullOrWhiteSpace(_token) || _token.Length < 32) throw new InvalidDataException("Missing sandbox token");
        if (!IsInside(_sandbox!, _scenario!) || !IsInside(_sandbox!, _output!)) throw new InvalidDataException("Scenario/output must be inside sandbox");
        string markerPath = Path.Combine(_sandbox!, "ifc-workbench-sandbox.json");
        RejectLinks(_sandbox!, _sandbox!);
        RejectLinks(_sandbox!, markerPath);
        RejectLinks(_sandbox!, _scenario!);
        RejectLinks(_sandbox!, _output!);
        var marker = JsonSerializer.Deserialize<SandboxMarker>(File.ReadAllText(markerPath), JsonOptions()) ?? throw new InvalidDataException("Invalid sandbox marker");
        if (marker.Token != _token) throw new InvalidDataException("Sandbox token mismatch");
        if (Main.ActiveWorldFileData?.IsCloudSave != false) throw new InvalidDataException("Cloud worlds are not allowed");
        if (string.IsNullOrWhiteSpace(marker.WorldPath) || !Path.IsPathFullyQualified(marker.WorldPath)) throw new InvalidDataException("Marker worldPath must be absolute");
        string world = Path.GetFullPath(Main.ActiveWorldFileData?.Path ?? throw new InvalidDataException("No active world path"));
        RejectLinks(_sandbox!, world);
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (!IsInside(_sandbox!, world) || !string.Equals(world, Path.GetFullPath(marker.WorldPath), comparison)) throw new InvalidDataException("Active world is not the explicitly authorised sandbox world");
        string save = Path.GetFullPath(Terraria.Program.SavePath);
        if (!string.Equals(Path.TrimEndingDirectorySeparator(save), Path.TrimEndingDirectorySeparator(_sandbox!), comparison) && !IsInside(_sandbox!, save))
            throw new InvalidDataException("tModLoader save path is outside sandbox");
        if (!Main.dedServ) {
            if (Main.ActivePlayerFileData == null || Main.ActivePlayerFileData.IsCloudSave || !IsInside(_sandbox!, Main.ActivePlayerFileData.Path))
                throw new InvalidDataException("Local player save must be a non-cloud file inside sandbox");
            RejectLinks(_sandbox!, Main.ActivePlayerFileData.Path);
        }
    }

    internal static void RejectLinks(string root, string path)
    {
        if (!string.Equals(Path.GetFullPath(root), Path.GetFullPath(path), OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal) && !IsInside(root,path))
            throw new InvalidDataException("Path is outside sandbox");
        string current = Path.GetFullPath(root);
        if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("Sandbox root must not be a link");
        foreach (var part in Path.GetRelativePath(current, Path.GetFullPath(path)).Split(Path.DirectorySeparatorChar)) {
            if (part == ".") continue;
            current = Path.Combine(current, part);
            if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Sandbox path must not traverse a link");
        }
    }
    internal static JsonSerializerOptions JsonOptions() => new() { PropertyNameCaseInsensitive = false, PropertyNamingPolicy = JsonNamingPolicy.CamelCase, UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow };
    internal static void Write(string path, object value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string tmp = path + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(value));
        File.Move(tmp, path, true);
    }
}

public sealed class SandboxMarker { [JsonRequired] public string Token { get; set; } = ""; [JsonRequired] public string WorldPath { get; set; } = ""; }
public sealed class PointSpec { [JsonRequired] public float X { get; set; } [JsonRequired] public float Y { get; set; } }
public sealed class WorkbenchRequest
{
    [JsonRequired] public string Mode { get; set; } = "";
    public string Item { get; set; } = "";
    public string Adapter { get; set; } = "";
    public JsonElement? ItemData { get; set; }
    public string ItemBoundary { get; set; } = "fresh";
    public string Projectile { get; set; } = "";
    [JsonRequired] public string Npc { get; set; } = "";
    public string Input { get; set; } = "primary";
    [JsonRequired] public int Ticks { get; set; }
    public int HoldTicks { get; set; }
    public int Damage { get; set; }
    public float Knockback { get; set; }
    public float Speed { get; set; }
    [JsonRequired] public PointSpec? Spawn { get; set; }
    [JsonRequired] public PointSpec? Target { get; set; }
    [JsonRequired] public PointSpec? Aim { get; set; }
    [JsonRequired] public int MinHits { get; set; }
    public int MinDamage { get; set; } = 1;
}

internal sealed class WorkbenchRun
{
    internal readonly WorkbenchRequest Request;
    private readonly string _output;
    private readonly string _scenarioSha256;
    private readonly List<object> _events = new();
    private readonly List<object> _frames = new();
    private readonly HashSet<(int slot, int identity, int owner)> _itemProjectiles = new();
    private int _tick, _wait, _npc = -1, _owner = -1, _itemType, _projectileType, _rootProjectile = -1, _rootIdentity = -1, _rootOwner = -1;
    private bool _started;
    private bool _targetRetired;
    private bool _rootRetired;
    internal bool Completed { get; private set; }
    internal int TickIndex => _tick;
    internal int Owner => _owner;
    internal int Target => _npc;
    internal bool ControlsActive => _started && !Completed && Request.Mode == "item_use" && _tick < Request.HoldTicks;
    private int _hits, _totalDamage;
    private readonly Mod? _itemAdapter;

    internal WorkbenchRun(WorkbenchRequest request, string output, string scenarioSha256)
    {
        Request = request; _output = output; _scenarioSha256 = scenarioSha256;
        if (request.Mode is not ("projectile" or "item_use")) throw new InvalidDataException("mode must be projectile or item_use");
        if (request.Ticks is < 1 or > 3600 || request.MinHits is < 1 or > 10000 || request.MinDamage is < 1 or > 100000000) throw new InvalidDataException("ticks, minHits or minDamage is outside allowed bounds");
        if (request.Mode == "item_use" && (request.HoldTicks < 1 || request.HoldTicks > request.Ticks)) throw new InvalidDataException("holdTicks must be within scenario ticks");
        if (request.Input is not ("primary" or "alt")) throw new InvalidDataException("input must be primary or alt");
        ValidatePoint(request.Spawn, "spawn"); ValidatePoint(request.Target, "target"); ValidatePoint(request.Aim, "aim");
        if (request.Mode == "projectile" && Vector2.DistanceSquared(new Vector2(request.Spawn!.X,request.Spawn.Y),new Vector2(request.Aim!.X,request.Aim.Y)) < 0.0001f)
            throw new InvalidDataException("aim must differ from projectile spawn");
        if (!float.IsFinite(request.Knockback) || !float.IsFinite(request.Speed)) throw new InvalidDataException("knockback and speed must be finite");
        if (request.Mode == "projectile" && (request.Damage is < 1 or > 100000 || request.Knockback is < 0 or > 100 || request.Speed is < 0 or > 100))
            throw new InvalidDataException("projectile damage, knockback or speed is outside allowed bounds");
        if (request.Mode == "item_use" && (request.Damage != 0 || request.Knockback != 0 || request.Speed != 0))
            throw new InvalidDataException("item_use uses native item stats; do not supply damage, speed or knockback");
        if (request.ItemBoundary is not ("fresh" or "local_cache")) throw new InvalidDataException("itemBoundary must be fresh or local_cache");
        if (request.Mode == "projectile" && (!string.IsNullOrEmpty(request.Adapter) || request.ItemData.HasValue || !string.IsNullOrEmpty(request.Item)))
            throw new InvalidDataException("projectile mode does not accept an item or item adapter");
        NpcType = ResolveNpc(request.Npc);
        if (request.Mode == "projectile") {
            _projectileType = ResolveProjectile(request.Projectile);
        } else {
            if (Main.dedServ) throw new NotSupportedException("item_use requires an actual local client player; dedicated server mode cannot test it");
            if (!string.IsNullOrEmpty(request.Adapter)) {
                if (!string.IsNullOrEmpty(request.Item) || !request.ItemData.HasValue || request.ItemData.Value.ValueKind != JsonValueKind.Object)
                    throw new InvalidDataException("An item adapter needs itemData as an object and no item name");
                if (!ModLoader.TryGetMod(request.Adapter, out var adapter)) throw new InvalidDataException("Item adapter mod not loaded: " + request.Adapter);
                _itemAdapter = adapter;
            } else {
                if (request.ItemData.HasValue || request.ItemBoundary != "fresh") throw new InvalidDataException("itemData/itemBoundary require an adapter");
                _itemType = ResolveItem(request.Item);
            }
        }
    }
    private int NpcType { get; }

    private static int ResolveNpc(string fullName)
    {
        if (fullName.StartsWith("Terraria/", StringComparison.Ordinal)) {
            string value = fullName.Substring("Terraria/".Length);
            if ((!int.TryParse(value, out int id) && !NPCID.Search.TryGetId(value, out id)) || id <= 0 || id >= NPCID.Count)
                throw new InvalidDataException("Vanilla NPC not found: " + fullName);
            return id;
        }
        if (!ModContent.TryFind<ModNPC>(fullName, out var npc)) throw new InvalidDataException("Mod NPC not found: " + fullName);
        return npc.Type;
    }

    private static int ResolveProjectile(string fullName)
    {
        if (fullName.StartsWith("Terraria/", StringComparison.Ordinal)) {
            string value = fullName.Substring("Terraria/".Length);
            if ((!int.TryParse(value, out int id) && !ProjectileID.Search.TryGetId(value, out id)) || id <= 0 || id >= ProjectileID.Count)
                throw new InvalidDataException("Vanilla projectile not found: " + fullName);
            return id;
        }
        if (!ModContent.TryFind<ModProjectile>(fullName, out var projectile)) throw new InvalidDataException("Mod projectile not found: " + fullName);
        return projectile.Type;
    }

    private static int ResolveItem(string fullName)
    {
        if (fullName.StartsWith("Terraria/", StringComparison.Ordinal)) {
            string value = fullName.Substring("Terraria/".Length);
            if ((!int.TryParse(value, out int id) && !ItemID.Search.TryGetId(value, out id)) || id <= 0 || id >= ItemID.Count)
                throw new InvalidDataException("Vanilla item not found: " + fullName);
            return id;
        }
        if (!ModContent.TryFind<ModItem>(fullName, out var item)) throw new InvalidDataException("Mod item not found: " + fullName);
        return item.Type;
    }

    private static void ValidatePoint(PointSpec? point, string name)
    {
        if (point == null || !float.IsFinite(point.X) || !float.IsFinite(point.Y) || point.X < 160 || point.Y < 160 || point.X > Main.maxTilesX * 16 - 160 || point.Y > Main.maxTilesY * 16 - 160)
            throw new InvalidDataException(name + " must be inside world margins");
    }

    internal void Tick()
    {
        if (Completed) return;
        if (!_started)
        {
            if (Request.Mode == "item_use" && (Main.myPlayer < 0 || Main.myPlayer >= Main.maxPlayers || !Main.player[Main.myPlayer].active)) {
                if (++_wait > 300) Finish("unsupported", "No active local client player appeared");
                return;
            }
            Start();
            _started = true;
            return; // Do not count the setup frame as an executed combat update.
        }
        NPC npc = Main.npc[_npc];
        _frames.Add(new { tick = _tick, npcActive = npc.active, npcLife = npc.life, npcType = npc.type,
            npcX = npc.position.X, npcY = npc.position.Y, owner = _owner,
            itemAnimation = _owner >= 0 ? Main.player[_owner].itemAnimation : (int?)null,
            projectileCount = CountProjectiles() });
        _tick++;
        if (_tick >= Request.Ticks) {
            bool passed = _hits >= Request.MinHits && _totalDamage >= Request.MinDamage;
            Finish(passed ? "passed" : "failed", passed ? null : "Observed hit count or damage below requested minimum");
        }
    }

    private int CountProjectiles()
    {
        int count = 0;
        for (int i = 0; i < Main.maxProjectiles; i++) if (Main.projectile[i].active && (_owner < 0 || Main.projectile[i].owner == _owner)) count++;
        return count;
    }

    private void Start()
    {
        if (Request.Mode == "item_use") {
            _owner = Main.myPlayer;
            Player player = Main.player[_owner];
            player.position = new Vector2(Request.Spawn!.X, Request.Spawn.Y);
            player.selectedItem = 0;
            if (_itemAdapter == null) player.inventory[0].SetDefaults(_itemType);
            else {
                // Generic optional adapter. The item JSON is part of the already
                // verified sandbox scenario; this driver never opens its paths.
                object result = _itemAdapter.Call("PrepareItem", player.inventory[0], Request.ItemData!.Value.GetRawText(), Request.ItemBoundary == "local_cache");
                if (result is not true || player.inventory[0].ModItem == null || player.inventory[0].type <= 0)
                    throw new InvalidOperationException("Item adapter did not prepare a native registered item");
                _itemType = player.inventory[0].type;
            }
        }
        var source = new EntitySource_Misc("IFCWorkbenchDriver");
        _npc = NPC.NewNPC(source, (int)Request.Target!.X, (int)Request.Target.Y, NpcType);
        if (_npc < 0 || _npc >= Main.maxNPCs || !Main.npc[_npc].active || Main.npc[_npc].type != NpcType)
            throw new InvalidOperationException("Native NPC.NewNPC failed");
        if (Request.Mode == "projectile") {
            Vector2 pos = new(Request.Spawn!.X, Request.Spawn.Y);
            Vector2 direction = new Vector2(Request.Aim!.X, Request.Aim.Y) - pos;
            if (direction.LengthSquared() < 0.0001f) throw new InvalidDataException("aim must differ from projectile spawn");
            direction.Normalize();
            int slot = Projectile.NewProjectile(source, pos, direction * Request.Speed, _projectileType, Request.Damage, Request.Knockback, Main.myPlayer);
            if (slot < 0 || slot >= Main.maxProjectiles || !Main.projectile[slot].active || Main.projectile[slot].type != _projectileType)
                throw new InvalidOperationException("Native Projectile.NewProjectile failed");
            _rootProjectile = slot; _rootIdentity = Main.projectile[slot].identity; _rootOwner = Main.projectile[slot].owner;
            _events.Add(new { tick = -1, kind = "projectile_spawn", slot, type = _projectileType, owner = Main.projectile[slot].owner });
        }
        _events.Add(new { tick = -1, kind = "npc_spawn", slot = _npc, type = NpcType });
    }

    internal void Hit(string source, int target, int damage, int projectileType, int owner, int projectileSlot, int projectileIdentity, int itemType)
    {
        if (Completed || !_started || _targetRetired || target != _npc || Main.npc[target].type != NpcType) return;
        if (Request.Mode == "item_use" && (owner != _owner || source == "item" && itemType != _itemType)) return;
        if (Request.Mode == "item_use" && source == "projectile" && !_itemProjectiles.Contains((projectileSlot, projectileIdentity, owner))) return;
        if (Request.Mode == "projectile" && (_rootRetired || source != "projectile" || projectileType != _projectileType || projectileSlot != _rootProjectile || projectileIdentity != _rootIdentity || owner != _rootOwner)) return;
        _hits++;
        _totalDamage += Math.Max(0, damage);
        _events.Add(new { tick = _tick, kind = "hit", source, target, damage, projectileType, owner });
    }

    internal void ProjectileSpawn(Projectile projectile, IEntitySource source)
    {
        if (Completed || !_started) return;
        if (Request.Mode == "projectile") {
            if (projectile.whoAmI == _rootProjectile) _rootRetired = true;
            return;
        }
        // Reusing a slot must retire its old identity before provenance checks.
        _itemProjectiles.RemoveWhere(entry => entry.slot == projectile.whoAmI);
        if (projectile.owner != _owner) return;
        bool fromItem = source is EntitySource_ItemUse itemSource && ReferenceEquals(itemSource.Entity, Main.player[_owner]) && ReferenceEquals(itemSource.Item, Main.player[_owner].inventory[0]);
        bool fromChild = source is EntitySource_Parent parent && parent.Entity is Projectile parentProjectile && _itemProjectiles.Contains((parentProjectile.whoAmI, parentProjectile.identity, parentProjectile.owner));
        if (!fromItem && !fromChild) return;
        _itemProjectiles.Add((projectile.whoAmI, projectile.identity, projectile.owner));
        _events.Add(new { tick = _tick, kind = "tracked_projectile_spawn", slot = projectile.whoAmI, identity = projectile.identity, owner = projectile.owner, source = fromItem ? "item_use" : "parent_projectile" });
    }

    internal void NpcSpawn(NPC npc)
    {
        if (_started && npc.whoAmI == _npc) _targetRetired = true;
    }

    internal void Finish(string status, string? error)
    {
        if (Completed) return;
        Completed = true;
        if (_owner >= 0 && _owner < Main.maxPlayers) Main.player[_owner].controlUseItem = false;
        WorkbenchSystem.Write(_output, new { schemaVersion = 1, status, error, mode = Request.Mode,
            scope = Request.Mode == "item_use" ? "Actual local client and scripted controls; no rendering or multiplayer certification" : "Actual tModLoader world tick and the selected root projectile/NPC; server sentinel owner, no player-use, child-projectile or client rendering certification",
            scenarioSha256 = _scenarioSha256, requested = Request, completedTicks = _tick, requestedTicks = Request.Ticks, hits = _hits, minHits = Request.MinHits, totalDamage = _totalDamage, minDamage = Request.MinDamage, targetRetired = _targetRetired, events = _events, snapshots = _frames });
    }
}

public sealed class WorkbenchInput : ModPlayer
{
    public override void SetControls()
    {
        var run = WorkbenchSystem.Run;
        if (run == null || run.Completed || Player.whoAmI != Main.myPlayer || Player.whoAmI != run.Owner) return;
        Player.controlUseItem = run.ControlsActive;
        if (run.ControlsActive && run.Request.Input == "alt") Player.altFunctionUse = 1;
        if (!run.ControlsActive && Player.altFunctionUse == 1) Player.altFunctionUse = 0;
        Main.mouseX = (int)(run.Request.Aim!.X - Main.screenPosition.X);
        Main.mouseY = (int)(run.Request.Aim.Y - Main.screenPosition.Y);
    }
}

public sealed class WorkbenchProjectileObserver : GlobalProjectile
{
    public override void OnSpawn(Projectile projectile, IEntitySource source) => WorkbenchSystem.Run?.ProjectileSpawn(projectile, source);
    public override void OnHitNPC(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        => WorkbenchSystem.Run?.Hit("projectile", target.whoAmI, damageDone, projectile.type, projectile.owner, projectile.whoAmI, projectile.identity, 0);
}

public sealed class WorkbenchNpcObserver : GlobalNPC
{
    public override void OnSpawn(NPC npc, IEntitySource source) => WorkbenchSystem.Run?.NpcSpawn(npc);
}

public sealed class WorkbenchItemObserver : GlobalItem
{
    public override void OnHitNPC(Item item, Player player, NPC target, NPC.HitInfo hit, int damageDone)
    {
        if (ReferenceEquals(item, player.inventory[0]))
            WorkbenchSystem.Run?.Hit("item", target.whoAmI, damageDone, 0, player.whoAmI, -1, -1, item.type);
    }
}
