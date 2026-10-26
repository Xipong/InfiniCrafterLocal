#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

// Request-local parent observations and their explicit wire/fingerprint projections.
// Native facts are captured once; player-dependent ammo remains a separate observation.
public sealed partial class GeneratorClient
{
    // Read-only source certificate, not generated behavior or AI dispatch. A
    // different native method declines the observation instead of guessing it.
    private const string MotionSourceMethodSha256 = "5ce22f6374b8b786ee332454aa0bb136ebd20c57520929b41fe4f328dca56d9b";
    private const string InstalledMotionSourceMethodSha256 = "cf0488832f92e43e699ae307df6f73d90f88f17194250f0a39ca5715a9e0631b";
    private static readonly Lazy<string?> MotionSourceCertificate = new(() =>
    {
        try
        {
            byte[]? il = typeof(Projectile).GetMethod("AI_001", System.Reflection.BindingFlags.Instance
                | System.Reflection.BindingFlags.NonPublic)?.GetMethodBody()?.GetILAsByteArray();
            if (il is null) return null;
            string hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(il)).ToLowerInvariant();
            // Both exact implementations were independently executed through
            // native AI (delay/increment/cap). This is not an inferred IL alias.
            return hash is MotionSourceMethodSha256 or InstalledMotionSourceMethodSha256 ? hash : null;
        }
        catch { return null; }
    });

    private static object ToWireItem(Item item, Player? player = null)
    {
        GeneratedItemData? existing = item.ModItem is GeneratedItem generated ? generated.Data : null;
        if (GeneratedItemData.IsPlayerSaveReferenceOnly(existing))
        {
            string generatedParentId = existing!.Id;
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (registry is null
                || !registry.TryGet(generatedParentId, out GeneratedItemData canonical)
                || !GeneratedItemRegistryService.IsCurrentWorldData(canonical))
                throw new InvalidOperationException($"Generated parent '{generatedParentId}' is not hydrated for the current world");
            existing = canonical;
        }
        Item craftItem = CraftIdentityItem(item, existing);
        int originalPrefix = SafePrefix(item);
        bool prefixIgnored = originalPrefix != InfiniTerrariaSentinels.NoPrefix;
        var autoFeatures = AutoFeaturesFromItem(craftItem).ToArray();
        var nameTokens = NameTokens(craftItem).ToArray();
        string sourceMod = SourceModName(craftItem);
        string internalName = InternalName(craftItem);
        var tooltip = CaptureLiteralParentTooltip(craftItem, existing, sourceMod + "/" + internalName);
        ParentNativeFacts native = CaptureParentNativeFacts(craftItem, existing);
        // The three historical envelopes share one observed native snapshot. Only
        // these explicit shape differences belong here; no native field is read
        // again by an envelope projection. Copies preserve null and number types.
        JsonObject snapshot = (JsonObject)native.RuntimeFacts.DeepClone();
        snapshot.Remove("type");
        snapshot.Remove("buffType");
        snapshot.Remove("buffTime");
        snapshot["id"] = native.RuntimeFacts["type"]!.DeepClone();
        snapshot["name"] = existing?.Name ?? craftItem.Name;
        snapshot["sourceMod"] = sourceMod;
        snapshot["internalName"] = internalName;
        snapshot["fullName"] = sourceMod + "/" + internalName;
        snapshot["tooltipLines"] = JsonSerializer.SerializeToNode(tooltip.Lines, WireJsonOptions);
        snapshot["tooltipSource"] = JsonSerializer.SerializeToNode(tooltip.Source, WireJsonOptions);
        snapshot["prefix"] = InfiniTerrariaSentinels.NoPrefix;
        snapshot["originalPrefix"] = originalPrefix;
        snapshot["prefixIgnored"] = prefixIgnored;
        snapshot["stack"] = item.stack;
        snapshot["moddedOrigin"] = sourceMod != "Terraria";
        snapshot["directProjectileRaw"] = native.DirectProjectileRaw?.DeepClone();
        // Player-aware ammo observations intentionally differ from fingerprint's
        // player-free reference candidates and must remain separate captures.
        snapshot["effectiveProjectileRaw"] = JsonSerializer.SerializeToNode(EffectiveProjectileRawFromItem(craftItem, player), WireJsonOptions);
        snapshot["ammoRaw"] = JsonSerializer.SerializeToNode(AmmoRawFromItem(craftItem, player), WireJsonOptions);
        // Only generated parents carry authored design tags.
        snapshot["tags"] = JsonSerializer.SerializeToNode(existing?.Tags is { Length: > 0 } ? existing.Tags : Array.Empty<string>(), WireJsonOptions);
        snapshot["runtimeFacts"] = native.RuntimeFacts.DeepClone();
        snapshot["autoFeatures"] = JsonSerializer.SerializeToNode(autoFeatures, WireJsonOptions);
        snapshot["nameTokens"] = JsonSerializer.SerializeToNode(nameTokens, WireJsonOptions);
        snapshot["fingerprint"] = FingerprintFromFacts(sourceMod, internalName, autoFeatures, nameTokens, native, originalPrefix,
            craftItem.ModItem is null, existing?.Name ?? craftItem.Name,
            JsonSerializer.SerializeToNode(EffectiveProjectileRawFromItem(craftItem, null), WireJsonOptions),
            JsonSerializer.SerializeToNode(AmmoRawFromItem(craftItem, null), WireJsonOptions));
        snapshot["generatedData"] = JsonSerializer.SerializeToNode(existing, WireJsonOptions);
        snapshot["craftInput"] = JsonSerializer.SerializeToNode(new
        {
            prefixIgnored,
            originalPrefix,
            normalizedStats = "base_item_defaults_without_reforge_prefix",
            note = "Terraria reforges/prefixes are intentionally ignored for InfiniCraft recipes; original items/refunds keep their prefix."
        }, WireJsonOptions);
        ParentSpriteReference? spriteReference = TryCaptureNativeSpriteReference(craftItem, existing);
        // Preserve every historical field/null; only an observed request-local
        // fact adds spriteReferenceRaw. No global null omission.
        if (spriteReference is not null)
            snapshot["spriteReferenceRaw"] = JsonSerializer.SerializeToNode(spriteReference, WireJsonOptions);
        // Shared design vocabulary, deliberately outside native mechanics and
        // fingerprint. Python factors the two request observations once for Author.
        JsonObject? buffIdentities = CaptureLoadedBuffIdentities();
        if (buffIdentities is not null)
            snapshot["loadedBuffIdentitiesRaw"] = buffIdentities;
        return snapshot;
    }

    private static (string[] Lines, object? Source) CaptureLiteralParentTooltip(Item item, GeneratedItemData? existing, string fullName)
    {
        // Request-only source text, never semantic parsing or a native-AI certificate.
        // A generated proxy's static tooltip describes the host, not its accepted definition.
        if (existing is not null || item.IsAir)
            return (Array.Empty<string>(), null);
        try
        {
            var tooltip = Lang.GetTooltip(item.type);
            if (tooltip is null || tooltip.Lines == 0)
                return (Array.Empty<string>(), null);
            // Preserve literal lines and whitespace. Refuse the optional whole source
            // observation on a bound, never publish a clipped sentence as verbatim.
            if (tooltip.Lines > 64)
                return (Array.Empty<string>(), new { source = "Lang.GetTooltip", fullName,
                    language = Language.ActiveCulture.Name, status = "refused_line_bound" });
            var lines = Enumerable.Range(0, tooltip.Lines).Select(tooltip.GetLine).ToArray();
            if (lines.Sum(line => line.Length) > 16_384)
                return (Array.Empty<string>(), new { source = "Lang.GetTooltip", fullName,
                    language = Language.ActiveCulture.Name, status = "refused_character_bound" });
            return (lines, new { source = "Lang.GetTooltip", fullName,
                language = Language.ActiveCulture.Name, status = "observed_literal" });
        }
        catch
        {
            return (Array.Empty<string>(), null);
        }
    }

    private sealed record ParentSpriteFrameReference(string Source,
        [property: JsonPropertyName("xPx")] int XPx,
        [property: JsonPropertyName("yPx")] int YPx, int WidthPx, int HeightPx);

    private sealed record ParentSpriteReference(string Source, int TextureWidthPx, int TextureHeightPx,
        [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] ParentSpriteFrameReference? CurrentFrame);

    private static ParentSpriteReference? TryCaptureNativeSpriteReference(Item? item, GeneratedItemData? existing)
    {
        // This is a loaded native texture/UI-frame observation, not alpha bounds,
        // held/world display size or a child-size prescription. Absence is unknown.
        // Generated parents own different PNGs; their shared native host is not art.
        if (item is null || item.IsAir || existing is not null || item.ModItem is GeneratedItem
            || Main.dedServ || Main.netMode == NetmodeID.Server)
            return null;
        try
        {
            var assets = Terraria.GameContent.TextureAssets.Item;
            if (assets is null || item.type < ItemID.None || item.type >= assets.Length)
                return null;
            var asset = assets[item.type];
            // Installed ReLogic returns a default 1px Value for unloaded assets.
            // Accept genuine loaded 1px textures, but never touch unloaded Value.
            if (asset is null || asset.IsDisposed || !asset.IsLoaded)
                return null;
            var texture = asset.Value;
            if (texture is null || texture.IsDisposed)
                return null;
            int width = texture.Width, height = texture.Height;
            if (width <= 0 || height <= 0)
                return null;
            ParentSpriteFrameReference? frame = null;
            try
            {
                // Installed tML 2026.6.3.6 has itemAnimations, not drawAnimations.
                // GetFrame(Texture2D, int frameCounterOverride=-1) reads current
                // native state without Update; copy its literal returned rectangle.
                var animations = Main.itemAnimations;
                if (animations is not null && item.type < animations.Length)
                {
                    var animation = animations[item.type];
                    Rectangle rectangle = animation is null ? texture.Bounds : animation.GetFrame(texture);
                    if (rectangle.X >= 0 && rectangle.Y >= 0 && rectangle.Width > 0 && rectangle.Height > 0
                        && (long)rectangle.X + rectangle.Width <= width
                        && (long)rectangle.Y + rectangle.Height <= height)
                        frame = new ParentSpriteFrameReference(animation is null ? "texture_bounds" : "draw_animation",
                            rectangle.X, rectangle.Y, rectangle.Width, rectangle.Height);
                }
            }
            catch
            {
                // An unavailable/malformed frame cannot invalidate observed dimensions.
            }
            return new ParentSpriteReference("TextureAssets.Item", width, height, frame);
        }
        catch
        {
            // A retired/missing native resource is optional context, never a recipe failure.
            return null;
        }
    }

    private static RuntimePlacementSpec? CanonicalParentPlacement(GeneratedItemData? definition)
    {
        // Generated Item placement fields are reset outside an active place_item use.
        // Only one explicit canonical placement can be represented as item facts;
        // multiple bindings remain independently visible in generatedData.
        if (definition is null)
            return null;
        var placements = definition.RuntimeProgram.Bindings
            .Where(binding => binding.UsePolicy.Action.Kind == RuntimeBindingAction.PlaceItem)
            .Select(binding => binding.UsePolicy.Action.Placement)
            .Take(2).ToArray();
        return placements.Length == 1 ? placements[0] : null;
    }

    private static string CraftParentName(Item item)
    {
        GeneratedItemData? existing = item.ModItem is GeneratedItem generated ? generated.Data : null;
        if (!string.IsNullOrWhiteSpace(existing?.Name))
            return existing!.Name;
        return CraftIdentityItem(item, existing).Name;
    }

    private static int SafePrefix(Item item)
    {
        try { return item?.prefix ?? InfiniTerrariaSentinels.NoPrefix; } catch { return InfiniTerrariaSentinels.NoPrefix; }
    }

    private static Item CraftIdentityItem(Item item, GeneratedItemData? existing = null)
    {
        // InfiniCraft recipes use the base item identity/stats. Terraria prefixes/reforges
        // (Legendary, Zealous/Пылкий, Godly, etc.) are per-instance modifiers and must not
        // bias the LLM, balance tier, recipe cache key, or parent display name.
        // The real consumed/refunded Item clone is kept elsewhere, so this normalization is
        // request-only and does not delete the player's reforge.
        if (item is null || item.IsAir)
        {
            var air = new Item();
            air.TurnToAir();
            return air;
        }

        if (existing is not null)
        {
            Item clone = item.Clone();
            // Prefix(0) is a no-op. CloneDefaults clears all prefixed fields
            // (including crit/size) while retaining this clone's ModItem identity.
            // Unlike ResetPrefix it does not serialize reference-only data through
            // ItemIO/NetReceive. Reapply the exact resolved authored definition.
            clone.CloneDefaults(item.type);
            existing.ApplyToItem(clone);
            clone.stack = item.stack;
            return clone;
        }

        // If defaults cannot be obtained, abort instead of claiming that the
        // original prefixed instance represents base_item_stats_ignore_prefixes.
        Item baseItem = new();
        baseItem.SetDefaults(item.type);
        baseItem.stack = item.stack;
        return baseItem;
    }

    private static JsonObject FingerprintFromFacts(string sourceMod, string internalName,
        string[] autoFeatures, string[] nameTokens, ParentNativeFacts native, int originalPrefix,
        bool isVanilla, string name, JsonNode? effectiveProjectileRaw, JsonNode? ammoRaw)
    {
        JsonObject fingerprint = (JsonObject)native.RuntimeFacts.DeepClone();
        fingerprint.Remove("material");
        fingerprint.Remove("reuseDelay");
        fingerprint.Remove("shootProjectileFullName");
        fingerprint["sourceMod"] = sourceMod;
        fingerprint["internalName"] = internalName;
        fingerprint["fullName"] = sourceMod + "/" + internalName;
        fingerprint["isVanilla"] = isVanilla;
        fingerprint["name"] = name;
        fingerprint["prefix"] = InfiniTerrariaSentinels.NoPrefix;
        fingerprint["originalPrefix"] = originalPrefix;
        fingerprint["prefixIgnored"] = originalPrefix != InfiniTerrariaSentinels.NoPrefix;
        fingerprint["directProjectileRaw"] = native.DirectProjectileRaw?.DeepClone();
        fingerprint["effectiveProjectileRaw"] = effectiveProjectileRaw;
        fingerprint["ammoRaw"] = ammoRaw;
        fingerprint["runtimeFacts"] = native.RuntimeFacts.DeepClone();
        fingerprint["autoFeatures"] = JsonSerializer.SerializeToNode(autoFeatures, WireJsonOptions);
        fingerprint["nameTokens"] = JsonSerializer.SerializeToNode(nameTokens, WireJsonOptions);
        return fingerprint;
    }

    private sealed record ParentNativeFacts(JsonObject RuntimeFacts, JsonNode? DirectProjectileRaw);

    // Sole native-fact field map for root, runtimeFacts and fingerprint. Read the
    // unprefixed request-local Item once; authored placement replaces native proxy
    // defaults only when an exact canonical placement exists. Absence stays null.
    private static ParentNativeFacts CaptureParentNativeFacts(Item item, GeneratedItemData? existing)
    {
        RuntimePlacementSpec? placement = CanonicalParentPlacement(existing);
        var facts = new JsonObject
        {
            ["type"] = item.type,
            ["damage"] = item.damage,
            // Base Item.crit only: CraftIdentityItem already removed the reforge.
            // Player/equipment-effective crit remains a separate observation.
            ["crit"] = item.crit,
            ["damageClass"] = DamageClassName(item),
            ["shootProjectileFullName"] = ProjectileFullName(item.shoot),
            ["useStyle"] = item.useStyle,
            ["useStyleName"] = TerrariaRuntimeVocabulary.CanonicalItemUseStyleToken(item.useStyle),
            ["useTime"] = item.useTime,
            ["useAnimation"] = item.useAnimation,
            ["reuseDelay"] = item.reuseDelay,
            ["channel"] = item.channel,
            ["noMelee"] = item.noMelee,
            ["noUseGraphic"] = item.noUseGraphic,
            ["autoReuse"] = item.autoReuse,
            ["useTurn"] = item.useTurn,
            ["rare"] = item.rare,
            ["rarityDetails"] = JsonSerializer.SerializeToNode(RarityDetailsFromItem(item), WireJsonOptions),
            ["value"] = item.value,
            ["maxStack"] = item.maxStack,
            ["consumable"] = item.consumable,
            ["potion"] = item.potion,
            ["accessory"] = item.accessory,
            ["defense"] = item.defense,
            ["headSlot"] = item.headSlot,
            ["bodySlot"] = item.bodySlot,
            ["legSlot"] = item.legSlot,
            ["createTile"] = existing is null ? (int?)item.createTile : placement?.TileId,
            ["createWall"] = existing is null ? (int?)item.createWall : placement?.WallId,
            ["placeStyle"] = existing is null ? (int?)item.placeStyle : placement?.PlaceStyle,
            ["pickPower"] = item.pick,
            ["axePower"] = item.axe,
            ["hammerPower"] = item.hammer,
            ["bait"] = item.bait,
            ["fishingPole"] = item.fishingPole,
            ["healLife"] = item.healLife,
            ["lifeRegen"] = item.lifeRegen,
            ["healMana"] = item.healMana,
            ["manaCost"] = item.mana,
            ["ammo"] = item.ammo,
            ["ammoCategoryName"] = TerrariaRuntimeVocabulary.CanonicalAmmoCategoryToken(item.ammo),
            ["notAmmo"] = item.notAmmo,
            ["useAmmo"] = item.useAmmo,
            ["useAmmoCategoryName"] = TerrariaRuntimeVocabulary.CanonicalAmmoCategoryToken(item.useAmmo),
            // Literal native inventory flag, not a generated capability or inheritance rule.
            ["dropSeedsIfInInventory"] = item.type >= ItemID.None && item.type < ItemID.Sets.DropSeedsIfInInventory.Length
                && ItemID.Sets.DropSeedsIfInInventory[item.type],
            ["shoot"] = item.shoot,
            ["shootSpeed"] = item.shootSpeed,
            ["knockback"] = item.knockBack,
            ["buffType"] = item.buffType,
            ["buffTime"] = item.buffTime,
            ["material"] = item.material,
        };
        if (existing is null && CaptureNativeContactHitStatusReference(item) is object contactReference)
            facts["nativeContactHitStatusReference"] = JsonSerializer.SerializeToNode(contactReference, WireJsonOptions);
        if (existing is null && CaptureNativeEnvironmentReference(item) is JsonObject environmentReference)
            facts["nativeEnvironmentReference"] = environmentReference;
        if (existing is null && CaptureNativeEquipmentReference(item) is JsonObject equipmentReference)
            facts["nativeEquipmentReference"] = equipmentReference;
        if (existing is null && CaptureNativeShootReference(item) is JsonObject shootReference)
            facts["nativeShootReference"] = shootReference;
        if (NativeTileStateFacts.Capture(facts["createTile"]?.GetValue<int>(), facts["placeStyle"]?.GetValue<int>()) is JsonObject tileState)
            facts["nativeTileState"] = tileState;
        return new(facts, JsonSerializer.SerializeToNode(DirectProjectileRawFromItem(item), WireJsonOptions));
    }

    private static IEnumerable<string> NameTokens(Item item)
    {
        string raw = InternalName(item);
        string spaced = Regex.Replace(raw, "([a-z0-9])([A-Z])", "$1 $2");
        spaced += " " + item.Name;
        foreach (Match m in Regex.Matches(spaced.ToLowerInvariant(), "[a-z0-9]+"))
        {
            string token = m.Value.Trim();
            if (token.Length >= 2) yield return token;
        }
    }

    private static string SourceModName(Item item)
    {
        try { return item.ModItem?.Mod?.Name ?? "Terraria"; }
        catch { return "Terraria"; }
    }

    private static string InternalName(Item item)
    {
        try
        {
            if (item.ModItem is not null)
                return item.ModItem.Name;
            string? name = ItemID.Search.GetName(item.type);
            return string.IsNullOrWhiteSpace(name) ? item.type.ToString() : name;
        }
        catch
        {
            return item.type.ToString();
        }
    }

    private static string DamageClassName(Item item)
        => TerrariaRuntimeVocabulary.CanonicalDamageClassToken(item?.DamageType);

    private static string DamageClassName(DamageClass? damageClass, int damage = 1)
        => TerrariaRuntimeVocabulary.CanonicalDamageClassToken(damageClass);

    private static string ProjectileFullName(int projectileType)
    {
        if (projectileType <= ProjectileID.None) return "";
        try
        {
            Projectile p = new();
            p.SetDefaults(projectileType);
            if (p.ModProjectile is not null)
                return (p.ModProjectile.Mod?.Name ?? "UnknownMod") + "/" + p.ModProjectile.Name;
            string? vanilla = ProjectileID.Search.GetName(projectileType);
            return string.IsNullOrWhiteSpace(vanilla) ? "Terraria/Projectile_" + projectileType : "Terraria/" + vanilla;
        }
        catch { return ""; }
    }

    private sealed class AmmoCandidate
    {
        public Item Item { get; set; } = new();
        public string Source { get; set; } = "runtime_scan";
        public int InventorySlot { get; set; } = -1;
        public int Score { get; set; } = 0;
    }

    private static object? DirectProjectileRawFromItem(Item item)
    {
        if (item.shoot <= ProjectileID.None)
            return null;
        return ProjectileRawSnapshot(item.shoot, item.shootSpeed, "item.shoot", item, -1);
    }

    private static object? EffectiveProjectileRawFromItem(Item item, Player? player)
    {
        // Effective projectile is no longer allowed to silently replace a weapon's own
        // shoot field with the "best" ammo candidate.  Ammo examples are context, not
        // the parent weapon identity: many Terraria/modded weapons have their own shoot
        // mechanics even when useAmmo is set.
        if (item.ammo > AmmoID.None && item.shoot > ProjectileID.None)
            return ProjectileRawSnapshot(item.shoot, item.shootSpeed, "this_ammo_item.shoot", item, -1);

        if (item.shoot > ProjectileID.None)
            return ProjectileRawSnapshot(item.shoot, item.shootSpeed, item.useAmmo > AmmoID.None ? "weapon_item.shoot_field" : "item.shoot", item, -1);

        // No own shoot field means unknown here. Inventory/representative ammo
        // remain observations in ammoRaw, never a replacement weapon identity.

        return null;
    }

    private static object? AmmoRawFromItem(Item item, Player? player)
    {
        if (item.ammo > AmmoID.None)
        {
            return new
            {
                mode = "this_item_is_ammo",
                ammoId = item.ammo,
                ammoItemRaw = AmmoItemRawSnapshot(item, "parent_item", -1),
                projectileRaw = item.shoot > ProjectileID.None ? ProjectileRawSnapshot(item.shoot, item.shootSpeed, "this_ammo_item.shoot", item, -1) : null
            };
        }

        if (item.useAmmo <= AmmoID.None)
            return null;

        var inventory = FindPlayerAmmoCandidates(item.useAmmo, player, 3, out string inventoryStatus);
        var fallback = FindRepresentativeAmmoCandidates(item.useAmmo, 3);
        var semantics = CaptureAmmoProjectileSemantics(item);
        var bindings = (inventory ?? new List<AmmoCandidate>()).Concat(fallback)
            .ToDictionary(candidate => candidate, candidate => BindAmmoCandidateProjectile(item, candidate, semantics));
        bool KeepInputProfile(AmmoCandidate candidate) => bindings[candidate]["includeInputProjectileProfile"]!.GetValue<bool>();
        var replacementTypes = bindings.Values.Where(binding => binding["includeReplacementProjectileProfile"]!.GetValue<bool>())
            .Select(binding => binding["sourceRuleOutputProjectileId"]!.GetValue<int>()).Distinct().Take(3).ToArray();
        return new
        {
            mode = "weapon_uses_ammo",
            ammoId = item.useAmmo,
            projectileSemanticsReference = semantics,
            candidateProjectileBindings = bindings.Values.ToArray(),
            nativeReplacementProjectileRaw = replacementTypes.Select(type => SourceReplacementProjectileRaw(type, item)).ToArray(),
            playerInventoryObservation = new
            {
                source = "Player.inventory",
                status = inventoryStatus == "observed" ? "observed" : "unavailable",
                reason = inventoryStatus == "observed" ? null : inventoryStatus,
                candidateLimit = 3,
                selection = "inventory_order_category_match_not_native_PickAmmo"
            },
            // This is the weapon's own shoot field.  It may be a default ammo placeholder,
            // or it may be a custom mechanic.  The LLM gets it separately from ammo candidates.
            weaponShootFieldProjectileRaw = item.shoot > ProjectileID.None ? ProjectileRawSnapshot(item.shoot, item.shootSpeed, "weapon_item.shoot_field", item, -1) : null,
            // Null means the inventory was not observed. Only a completed scan
            // can publish [] as an observed lack of matching candidates.
            playerInventoryAmmoRaw = inventory?.Select(c => AmmoItemRawSnapshot(c.Item, c.Source, c.InventorySlot)).ToArray(),
            playerInventoryProjectileRaw = inventory?.Where(c => c.Item.shoot > ProjectileID.None && KeepInputProfile(c)).Select(c => ProjectileRawSnapshot(c.Item.shoot, c.Item.shootSpeed, c.Source + ".shoot", c.Item, c.InventorySlot)).ToArray(),
            fallbackAmmoRaw = fallback.Select(c => AmmoItemRawSnapshot(c.Item, c.Source, c.InventorySlot)).ToArray(),
            fallbackProjectileRaw = fallback.Where(c => c.Item.shoot > ProjectileID.None && KeepInputProfile(c)).Select(c => ProjectileRawSnapshot(c.Item.shoot, c.Item.shootSpeed, c.Source + ".shoot", c.Item, c.InventorySlot)).ToArray()
        };
    }

    private static List<AmmoCandidate>? FindPlayerAmmoCandidates(int ammoId, Player? player, int maxCount, out string status)
    {
        status = player is null ? "no_player" : "inventory_scan_failed";
        var outList = new List<AmmoCandidate>();
        if (player is null || ammoId <= AmmoID.None)
            return null;
        try
        {
            for (int i = 0; i < player.inventory.Length; i++)
            {
                Item ammo = player.inventory[i];
                if (ammo is null || ammo.IsAir || ammo.stack <= 0)
                    continue;
                if (ammo.ammo == ammoId)
                {
                    outList.Add(new AmmoCandidate
                    {
                        // Generated ammo shares one proxy type; its instance definition
                        // must accompany request-only normalization, just like a parent.
                        Item = CraftIdentityItem(ammo, ammo.ModItem is GeneratedItem generatedAmmo ? generatedAmmo.Data : null),
                        Source = "player_inventory_ammo_candidate_base_no_prefix",
                        InventorySlot = i,
                        Score = i
                    });
                    if (outList.Count >= Math.Max(1, maxCount))
                        break;
                }
            }
            status = "observed";
        }
        catch { return null; }
        return outList;
    }

    private static List<AmmoCandidate> FindRepresentativeAmmoCandidates(int ammoId, int maxCount)
    {
        var outList = new List<AmmoCandidate>();
        if (ammoId <= AmmoID.None)
            return outList;
        try
        {
            for (int type = InfiniTerrariaSentinels.FirstValidItemType; type < ItemLoader.ItemCount; type++)
            {
                try
                {
                    Item ammo = new();
                    ammo.SetDefaults(type);
                    if (ammo.IsAir || ammo.ammo != ammoId)
                        continue;
                    outList.Add(new AmmoCandidate
                    {
                        Item = ammo,
                        Source = "fallback_basic_ammo_scan",
                        InventorySlot = -1,
                        Score = AmmoCandidateScore(ammo)
                    });
                }
                catch { }
            }
        }
        catch { }
        return outList.OrderBy(c => c.Score).ThenBy(c => c.Item.type).Take(Math.Max(1, maxCount)).ToList();
    }

    private static int AmmoCandidateScore(Item ammo)
    {
        int score = 0;
        string internalName = InternalName(ammo).ToLowerInvariant();
        string displayName = (ammo.Name ?? "").ToLowerInvariant();
        // Fallback ammo is only a neutral raw example for the LLM, not an "ideal" ammo choice.
        // Prefer simple cheap vanilla ammo; avoid endless/infinite and high-tier/modded examples
        // unless no simpler candidates exist.
        if (internalName.Contains("endless") || internalName.Contains("infinite") || displayName.Contains("endless") || displayName.Contains("infinite")) score += 100000;
        if (ammo.ModItem is not null) score += 5000;
        score += Math.Max(0, ammo.rare) * 1000;
        score += Math.Clamp(ammo.value / 5, 0, 20000);
        score += Math.Max(0, ammo.damage) * 25;
        return score;
    }

    private static object AmmoItemRawSnapshot(Item ammo, string source, int inventorySlot)
    {
        return new
        {
            source,
            inventorySlot,
            type = ammo.type,
            name = ammo.Name,
            internalName = InternalName(ammo),
            sourceMod = SourceModName(ammo),
            fullName = SourceModName(ammo) + "/" + InternalName(ammo),
            pickAmmoHookReference = CaptureAmmoInputHookReference(ammo),
            damage = ammo.damage,
            damageClass = DamageClassName(ammo),
            ammo = ammo.ammo,
            ammoCategoryName = TerrariaRuntimeVocabulary.CanonicalAmmoCategoryToken(ammo.ammo),
            notAmmo = ammo.notAmmo,
            useAmmo = ammo.useAmmo,
            shoot = ammo.shoot,
            shootSpeed = ammo.shootSpeed,
            knockback = ammo.knockBack,
            rare = ammo.rare,
            value = ammo.value,
            maxStack = ammo.maxStack,
            stack = ammo.stack,
            consumable = ammo.consumable,
            potion = ammo.potion,
            material = ammo.material
        };
    }

    private static object? VerifiedSourceMotionReference(Projectile source)
    {
        // This exact source identity was observed through real native AI, with
        // its method bytes pinned. No name/aiStyle -> generated movement rule.
        // Sampling arbitrary native AI during crafting would have world effects.
        if (source.ModProjectile is not null || source.type != ProjectileID.WoodenArrowFriendly
            || MotionSourceCertificate.Value is not string certificate)
            return null;
        return new
        {
            source = "verified_native_AI_001_reference", fullName = "Terraria/WoodenArrowFriendly",
            sourceMethodSha256 = certificate, firstGravityUpdate = 15,
            verticalVelocityIncrementPerUpdate = 0.1f, maxDownwardVelocityPxPerUpdate = 16f,
            units = "velocity in pixels/projectile update; start counts native AI invocations",
            scope = "Native dry initial flight with default AI state; not collision/liquid/global-mod behavior. Read-only reference, not inherited execution. Generated move_gravity_arc starts immediately and is not an exact delayed native-AI replica. Author chooses the trajectory explicitly."
        };
    }

    private static object? ProjectileRawSnapshot(int projectileType, float itemShootSpeed, string source, Item? sourceItem, int inventorySlot)
    {
        if (projectileType <= ProjectileID.None)
            return null;
        try
        {
            Projectile p = new();
            p.SetDefaults(projectileType);
            string sourceMod = "Terraria";
            string internalName = projectileType.ToString();
            try
            {
                ModProjectile? modProjectile = p.ModProjectile;
                if (modProjectile is not null)
                {
                    sourceMod = modProjectile.Mod?.Name ?? "UnknownMod";
                    internalName = modProjectile.Name;
                }
                else
                {
                    string? vanilla = ProjectileID.Search.GetName(projectileType);
                    if (!string.IsNullOrWhiteSpace(vanilla)) internalName = vanilla;
                }
            }
            catch { }

            return new
            {
                source,
                inventorySlot,
                type = projectileType,
                sourceMod,
                internalName,
                fullName = sourceMod + "/" + internalName,
                sourceItemType = sourceItem?.type ?? ItemID.None,
                sourceItemName = sourceItem?.Name ?? "",
                sourceItemInternalName = sourceItem is null ? "" : InternalName(sourceItem),
                sourceItemSourceMod = sourceItem is null ? "" : SourceModName(sourceItem),
                sourceItemAmmo = sourceItem?.ammo ?? AmmoID.None,
                sourceItemUseAmmo = sourceItem?.useAmmo ?? AmmoID.None,
                sourceItemDamage = sourceItem?.damage ?? 0,
                sourceItemDamageClass = sourceItem is null ? "" : DamageClassName(sourceItem),
                sourceItemShoot = sourceItem?.shoot ?? ProjectileID.None,
                sourceItemShootSpeed = sourceItem?.shootSpeed ?? 0f,
                sourceItemKnockback = sourceItem?.knockBack ?? 0f,
                itemShootSpeed,
                ai0 = p.ai.Length > 0 ? p.ai[0] : 0f,
                ai1 = p.ai.Length > 1 ? p.ai[1] : 0f,
                ai2 = p.ai.Length > 2 ? p.ai[2] : 0f,
                localAI0 = p.localAI.Length > 0 ? p.localAI[0] : 0f,
                localAI1 = p.localAI.Length > 1 ? p.localAI[1] : 0f,
                collisionReference = CaptureNativeCollisionReference(p),
                armorPenetration = p.ArmorPenetration,
                width = p.width,
                height = p.height,
                scale = p.scale,
                aiStyle = p.aiStyle,
                penetrate = p.penetrate,
                maxPenetrate = p.maxPenetrate,
                timeLeft = p.timeLeft,
                extraUpdates = p.extraUpdates,
                tileCollide = p.tileCollide,
                ignoreWater = p.ignoreWater,
                friendly = p.friendly,
                hostile = p.hostile,
                arrow = p.arrow,
                minion = p.minion,
                sentry = p.sentry,
                minionSlots = p.minionSlots,
                ownerHitCheck = p.ownerHitCheck,
                usesLocalNPCImmunity = p.usesLocalNPCImmunity,
                localNPCHitCooldown = p.localNPCHitCooldown,
                usesIDStaticNPCImmunity = p.usesIDStaticNPCImmunity,
                idStaticNPCHitCooldown = p.idStaticNPCHitCooldown,
                stopsDealingDamageAfterPenetrateHits = p.stopsDealingDamageAfterPenetrateHits,
                light = p.light,
                alpha = p.alpha,
                netImportant = p.netImportant,
                damageClass = DamageClassName(p.DamageType),
                framesRaw = SafeProjFrames(projectileType),
                setsRaw = ProjectileSetsRaw(projectileType),
                motionReference = VerifiedSourceMotionReference(p),
                onHitStatusReference = CaptureNativeHitStatusReference(p)
            };
        }
        catch
        {
            return new
            {
                source,
                inventorySlot,
                type = projectileType,
                itemShootSpeed,
                unavailable = true
            };
        }
    }

    private static object ProjectileSetsRaw(int projectileType)
    {
        return new
        {
            trailCacheLength = SafeArrayValue(ProjectileID.Sets.TrailCacheLength, projectileType, 0),
            trailingMode = SafeArrayValue(ProjectileID.Sets.TrailingMode, projectileType, 0),
            // Reflection keeps this compatible across tModLoader versions and modded sets.
            lightPet = SafeProjectileSetValue("LightPet", projectileType),
            minionSacrificable = SafeProjectileSetValue("MinionSacrificable", projectileType),
            homing = SafeProjectileSetValue("Homing", projectileType),
            dontAttachHideToAlpha = SafeProjectileSetValue("DontAttachHideToAlpha", projectileType),
            usesOldTargeting = SafeProjectileSetValue("UsesOldTargeting", projectileType),
            noLiquidDistortion = SafeProjectileSetValue("NoLiquidDistortion", projectileType)
        };
    }

    private static int SafeProjFrames(int projectileType)
    {
        try
        {
            if (projectileType >= ProjectileID.None && projectileType < Main.projFrames.Length)
                return Main.projFrames[projectileType];
        }
        catch { }
        return 0;
    }

    private static int SafeArrayValue(int[] values, int index, int fallback)
    {
        try
        {
            if (index >= 0 && index < values.Length)
                return values[index];
        }
        catch { }
        return fallback;
    }

    private static object? SafeProjectileSetValue(string fieldName, int index)
    {
        try
        {
            var field = typeof(ProjectileID.Sets).GetField(fieldName, System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
            if (field is null) return null;
            object? value = field.GetValue(null);
            if (value is Array arr && index >= 0 && index < arr.Length)
                return arr.GetValue(index);
        }
        catch { }
        return null;
    }

    private static bool TryCreateProjectileDefaults(int projectileType, out Projectile projectile)
    {
        projectile = new Projectile();
        if (projectileType <= ProjectileID.None) return false;
        try
        {
            projectile.SetDefaults(projectileType);
            return true;
        }
        catch
        {
            projectile = new Projectile();
            return false;
        }
    }

    private static object RarityDetailsFromItem(Item item)
    {
        int raw = item.rare;
        try
        {
            ModRarity? modRarity = RarityLoader.GetRarity(raw);
            if (modRarity is not null)
            {
                Color color = modRarity.RarityColor;
                string modName = "UnknownMod";
                string rarityName = modRarity.GetType().Name;
                try { modName = modRarity.Mod?.Name ?? modName; } catch { }
                try { rarityName = string.IsNullOrWhiteSpace(modRarity.Name) ? rarityName : modRarity.Name; } catch { }
                return new
                {
                    raw,
                    isModded = true,
                    mod = modName,
                    name = rarityName,
                    fullName = modName + "/" + rarityName,
                    colorHex = ColorToHex(color),
                    colorR = color.R,
                    colorG = color.G,
                    colorB = color.B,
                    source = "RarityLoader.GetRarity"
                };
            }
        }
        catch { }

        return new
        {
            raw,
            isModded = false,
            mod = "Terraria",
            name = VanillaRarityName(raw),
            fullName = "Terraria/" + VanillaRarityName(raw),
            colorHex = VanillaRarityHex(raw),
            source = "vanilla numeric rarity"
        };
    }

    private static string ColorToHex(Color color)
    {
        return $"#{color.R:X2}{color.G:X2}{color.B:X2}";
    }

    private static string VanillaRarityName(int rare) => rare switch
    {
        ItemRarityID.Gray => "Gray",
        ItemRarityID.White => "White",
        ItemRarityID.Blue => "Blue",
        ItemRarityID.Green => "Green",
        ItemRarityID.Orange => "Orange",
        ItemRarityID.LightRed => "LightRed",
        ItemRarityID.Pink => "Pink",
        ItemRarityID.LightPurple => "LightPurple",
        ItemRarityID.Lime => "Lime",
        ItemRarityID.Yellow => "Yellow",
        ItemRarityID.Cyan => "Cyan",
        ItemRarityID.Red => "Red",
        ItemRarityID.Purple => "Purple",
        _ => "UnknownVanillaRarity"
    };

    private static string VanillaRarityHex(int rare) => rare switch
    {
        ItemRarityID.Gray => "#828282",
        ItemRarityID.White => "#FFFFFF",
        ItemRarityID.Blue => "#9696FF",
        ItemRarityID.Green => "#96FF96",
        ItemRarityID.Orange => "#FFC896",
        ItemRarityID.LightRed => "#FF9696",
        ItemRarityID.Pink => "#FF96FF",
        ItemRarityID.LightPurple => "#D2A0FF",
        ItemRarityID.Lime => "#96FF0A",
        ItemRarityID.Yellow => "#FFFF0A",
        ItemRarityID.Cyan => "#05C8FF",
        ItemRarityID.Red => "#FF2864",
        ItemRarityID.Purple => "#B428FF",
        _ => "#FFFFFF"
    };

    private static IEnumerable<string> AutoFeaturesFromItem(Item item)
    {
        // Mechanically derived features only. No hand-authored per-item semantic tags.
        var tags = new HashSet<string>();
        void Add(string tag) => tags.Add(tag);

        if (item.damage > 0) Add("weapon");
        if (item.DamageType == DamageClass.Melee) Add("melee");
        if (item.DamageType == DamageClass.Ranged) Add("ranged");
        if (item.DamageType == DamageClass.Magic) Add("magic");
        if (item.DamageType == DamageClass.Summon) Add("summon");
        if (item.accessory) Add("accessory");
        if (item.defense > 0 || item.headSlot >= 0 || item.bodySlot >= 0 || item.legSlot >= 0) Add("armor");
        if (item.material) Add("material");
        if (item.pick > 0 || item.axe > 0 || item.hammer > 0 || item.fishingPole > 0) Add("tool");
        if (item.pick > 0) Add("pickaxe");
        if (item.axe > 0) Add("axe");
        if (item.hammer > 0) Add("hammer");
        if (item.fishingPole > 0) Add("fishing_pole");
        if (item.healLife > 0 || item.healMana > 0 || item.buffType > InfiniTerrariaSentinels.NoBuffType) Add("potion_like");
        if (item.consumable) Add("consumable");
        if (item.ammo > AmmoID.None) Add("ammo");
        if (item.useAmmo > AmmoID.None) Add("uses_ammo");
        if (item.createTile >= TileID.Dirt || item.createWall >= WallID.None) Add("placeable");
        if (item.createTile >= TileID.Dirt && item.maxStack > 1) Add("placeable_block_or_tile");
        if (item.maxStack > 1) Add("stackable");
        if (item.shoot > ProjectileID.None) Add("projectile");
        if (item.channel) Add("channel");
        if (item.noMelee) Add("no_melee");
        if (item.noUseGraphic) Add("hidden_use_graphic");
        if (item.autoReuse) Add("auto_reuse");

        try
        {
            if (item.shoot > ProjectileID.None)
            {
                if (!TryCreateProjectileDefaults(item.shoot, out Projectile p))
                    return tags;
                if (p.penetrate == -1 || p.penetrate > 1) Add("piercing_projectile");
                if (p.extraUpdates > 0) Add("fast_projectile");
                if (!p.tileCollide) Add("noncolliding_projectile");
                if (p.usesLocalNPCImmunity || p.usesIDStaticNPCImmunity) Add("multi_hit_projectile");
                if (p.ownerHitCheck) Add("melee_projection");
                if (p.minion || p.sentry) Add("summon_projectile");
                if (p.arrow) Add("arrow_projectile");
            }
        }
        catch { }

        return tags;
    }
}
