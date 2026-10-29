#nullable enable
using System;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Terraria;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private static readonly Lazy<string?> ShootFactCertificate = new(() => NativeAttackCertificate(typeof(Player), "ItemCheck_Shoot"));
    private static readonly Lazy<string?> CollisionFactCertificate = new(() => NativeAttackCertificate(typeof(Projectile), "Colliding"));

    private static string? NativeAttackCertificate(Type owner, string method)
    {
        try
        {
            var member = owner.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                .SingleOrDefault(m => m.Name == method);
            byte[]? il = member?.GetMethodBody()?.GetILAsByteArray();
            return il is null ? null : Convert.ToHexString(SHA256.HashData(il)).ToLowerInvariant()
                + ":" + owner.Module.ModuleVersionId;
        }
        catch { return null; }
    }

    internal static JsonObject? CaptureNativeShootReference(Item item)
        => VerifiedNativeAttackReference(item.type, item.ModItem is null, "Player.ItemCheck_Shoot", ShootFactCertificate.Value);

    internal static JsonObject? CaptureNativeCollisionReference(Projectile projectile)
        => VerifiedNativeAttackReference(projectile.type, projectile.ModProjectile is null, "Projectile.Colliding", CollisionFactCertificate.Value);

    private static JsonObject? VerifiedNativeAttackReference(int type, bool vanilla, string method, string? certificate)
    {
        if (!vanilla || certificate is null
            || !NativeAttackFactsCatalog.Sources.TryGetValue(method + ":" + certificate, out var catalog)
            || !catalog.TryGetValue(type, out var json))
            return null;
        var facts = (JsonObject)JsonNode.Parse(json)!;
        facts["source"] = "verified_native_" + method + "_reference";
        facts["sourceMethodSha256"] = certificate.Split(':')[0];
        facts["sourceModuleVersionId"] = certificate.Split(':')[1];
        if (method == "Player.ItemCheck_Shoot")
            facts["scope"] = "Explicit spawn calls inside this native item-type branch, on terminating paths once that branch is reached. External use/player/ammo/mod gates and other hooks are unknown; not cadence, guaranteed hits, total attack count or inherited execution. damageMultiplierAtSpawn multiplies the current native shot-damage local after ammo/player/mod and any branch-local changes, not item base damage. Native contact damage remains separate when noMelee is false. Author chooses generated behavior explicitly.";
        return facts;
    }
}
