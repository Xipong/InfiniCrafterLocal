#nullable enable
using InfiniCrafterLocal.Content.Projectiles;
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

// Per-NPC, per-owner marker for the finite generated-whip tag contract.
// A generated whip hit marks only that owner; subsequent summon projectiles
// from the same owner receive the currently equipped authored ratio bonus.
public sealed class GeneratedWhipTagGlobalNPC : GlobalNPC
{
    private const int TagDurationTicks = 240;
    private readonly ushort[] _ownerTagTicks = new ushort[256];
    private readonly List<int> _activeOwners = new(2);

    public override bool InstancePerEntity => true;

    public override void SetDefaults(NPC entity)
    {
        Array.Clear(_ownerTagTicks);
        _activeOwners.Clear();
    }

    public void Mark(int owner)
    {
        if (owner < 0 || owner >= Main.maxPlayers || owner >= _ownerTagTicks.Length)
            return;
        if (_ownerTagTicks[owner] == 0)
            _activeOwners.Add(owner);
        _ownerTagTicks[owner] = TagDurationTicks;
    }

    public override void PostAI(NPC npc)
    {
        for (int i = _activeOwners.Count - 1; i >= 0; i--)
        {
            int owner = _activeOwners[i];
            if (_ownerTagTicks[owner] > 0)
                _ownerTagTicks[owner]--;
            if (_ownerTagTicks[owner] == 0)
                _activeOwners.RemoveAt(i);
        }
    }

    public override void ModifyHitByProjectile(NPC npc, Projectile projectile, ref NPC.HitModifiers modifiers)
    {
        int owner = projectile.owner;
        if (owner < 0 || owner >= Main.maxPlayers || owner >= _ownerTagTicks.Length || _ownerTagTicks[owner] == 0)
            return;
        if (projectile.ModProjectile is GeneratedProjectile generated && generated.IsGeneratedWhipTagSource)
            return;
        if (projectile.type > ProjectileID.None && projectile.type < ProjectileID.Sets.IsAWhip.Length && ProjectileID.Sets.IsAWhip[projectile.type])
            return;
        bool summonHit = projectile.minion
            || projectile.sentry
            || projectile.DamageType == DamageClass.Summon
            || projectile.DamageType == DamageClass.SummonMeleeSpeed;
        if (!summonHit)
            return;
        Player player = Main.player[owner];
        if (player is null || !player.active)
            return;
        float bonus = Math.Clamp(player.GetModPlayer<InfiniCraftPlayer>().GeneratedSummonTagDamage, 0f, 3f);
        if (bonus > 0f)
            modifiers.SourceDamage *= 1f + bonus;
    }
}
