using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void VerifiedNativeMotionReferenceReachesCraftSnapshot()
    {
        var arrow = new Projectile(); arrow.SetDefaults(ProjectileID.WoodenArrowFriendly);
        arrow.velocity = new Vector2(6.1f, 0f);
        for (int update = 1; update <= 16; update++)
        {
            arrow.AI();
            Equal(6.1f, arrow.velocity.X, "native arrow horizontal velocity retained");
            Equal(update < 15 ? 0f : (update - 14) * 0.1f, arrow.velocity.Y, "actual native delayed gravity");
        }
        for (int update = 17; update <= 200; update++) arrow.AI();
        Equal(16f, arrow.velocity.Y, "real native terminal downward velocity");
        var sourceHelper = typeof(GeneratorClient).GetMethod("VerifiedSourceMotionReference", BindingFlags.Static | BindingFlags.NonPublic)!;
        var unobserved = new Projectile(); unobserved.SetDefaults(ProjectileID.Bullet); unobserved.aiStyle = 1; unobserved.arrow = true;
        Equal(true, sourceHelper.Invoke(null, new object[] { unobserved }) is null, "same style/flag never invents a source reference");
        Console.WriteLine("MOTION_SOURCE_IL_SHA256=" + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(
            typeof(Projectile).GetMethod("AI_001", BindingFlags.Instance | BindingFlags.NonPublic)!.GetMethodBody()!.GetILAsByteArray()!)).ToLowerInvariant());
        var bow = new Item(); bow.SetDefaults(ItemID.WoodenBow);
        var wood = new Item(); wood.SetDefaults(ItemID.Wood);
        using var packet = JsonDocument.Parse(new GeneratorClient().Prepare(bow, wood, new Player()).PayloadJson);
        var reference = packet.RootElement.GetProperty("itemA").GetProperty("directProjectileRaw").GetProperty("motionReference");
        Equal("Terraria/WoodenArrowFriendly", reference.GetProperty("fullName").GetString()!, "exact source identity");
        Equal(15, reference.GetProperty("firstGravityUpdate").GetInt32(), "verified delayed start");
        Equal(0.1f, reference.GetProperty("verticalVelocityIncrementPerUpdate").GetSingle(), "verified native magnitude");
        Equal(16f, reference.GetProperty("maxDownwardVelocityPxPerUpdate").GetSingle(), "verified native cap");
        Equal(true, reference.GetProperty("sourceMethodSha256").GetString()!.Length == 64, "bound source algorithm hash");
        Equal(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(typeof(Projectile)
            .GetMethod("AI_001", BindingFlags.Instance | BindingFlags.NonPublic)!.GetMethodBody()!.GetILAsByteArray()!)).ToLowerInvariant(),
            reference.GetProperty("sourceMethodSha256").GetString()!, "reference names actual loaded native algorithm bytes");
        string? output = Environment.GetEnvironmentVariable("INFINI_PARENT_MOTION_SNAPSHOT_OUT");
        if (!string.IsNullOrWhiteSpace(output)) System.IO.File.WriteAllText(output, packet.RootElement.GetRawText());
    }
}
