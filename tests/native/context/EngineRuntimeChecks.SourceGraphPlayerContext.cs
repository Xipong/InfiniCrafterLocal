using System;
using System.Linq;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static int PlayerContextSourceExecutions;

    private sealed class PlayerContextEmptyItem : ModItem { }

    private sealed class PlayerContextNoise : ModPlayer
    {
        public int HealReduction = 0;
        public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (damageDone > 0 && HealReduction > 0) Player.potionDelay -= HealReduction;
        }
        public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (projectile.owner == Player.whoAmI && HealReduction > 0) Player.potionDelay -= HealReduction;
        }
    }

    private abstract class PlayerContextItemPredicate : ModPlayer
    {
        protected abstract bool Matches(Item item);
        public override bool CanUseItem(Item item)
        {
            PlayerContextSourceExecutions++;
            return Matches(item) && Player.wet;
        }
    }
    private sealed class PlayerContextRelevant : PlayerContextItemPredicate
    {
        protected override bool Matches(Item item) => item.type == 61;
        public override void ModifyWeaponCrit(Item item, ref float crit)
        {
            PlayerContextSourceExecutions++;
            if (item.damage > 0) crit += 13f;
        }
        public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (projectile.type == 7 && Player.wet) Player.statDefense += 17;
        }
        public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (Player.HeldItem.type == 61) Player.statDefense += 19;
        }
        public override void ModifyHitNPCWithProj(Projectile projectile, NPC target, ref NPC.HitModifiers modifiers)
        {
            PlayerContextSourceExecutions++;
            if (projectile.velocity.X > 0) modifiers.SourceDamage.Flat += 31f;
        }
    }

    private sealed class PlayerContextStateItem : ModItem
    {
        public override void UpdateAccessory(Player player, bool hideVisual)
        {
            PlayerContextSourceExecutions++;
            player.GetModPlayer<PlayerContextState>().Active = true;
        }
    }
    private sealed class PlayerContextState : ModPlayer
    {
        public bool Active, Unrelated = false;
        private bool HasActive() => Active;
        public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (HasActive() && Player.wet) Player.statDefense += 23;
            if (Unrelated && Player.lavaWet) Player.statManaMax2 += 29;
        }
    }

    private static void ParentSourceGraphExcludesUnlinkedPlayerContext()
    {
        PlayerContextSourceExecutions = 0;
        JsonObject graph = SelectionCapture(typeof(PlayerContextEmptyItem), consumer: typeof(PlayerContextNoise));
        Equal(true, SelectionNode(graph, "PlayerContextNoise.OnHitNPCWithItem(") is null,
            "an unused Item argument is not parent-specific evidence for global healing");
        Equal(true, SelectionNode(graph, "PlayerContextNoise.OnHitNPCWithProj(") is null,
            "projectile ownership only is authority context, not parent mechanics");
        Equal(2, graph["externalPlayerContext"]?["unlinkedHookCount"]?.GetValue<int>() ?? -1,
            "excluded global hooks remain explicitly counted as external context");
        Equal(0, PlayerContextSourceExecutions, "relevance analysis never executes global hooks");
        Equal(graph.ToJsonString(), SelectionCapture(typeof(PlayerContextEmptyItem), consumer: typeof(PlayerContextNoise)).ToJsonString(),
            "global context exclusion is deterministic");
        AssertSelectionReferences(graph);
        JsonObject actual = SelectionCapture(typeof(PlayerContextEmptyItem),
            consumer: typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer));
        Equal(true, SelectionNode(actual, "InfiniCraftPlayer.OnHitNPCWithItem(") is null
            && SelectionNode(actual, "InfiniCraftPlayer.OnHitNPCWithProj(") is null
            && !actual.ToJsonString().Contains("ReduceHealingPotionCooldown", StringComparison.Ordinal),
            "captured Ebonstone healing chain is external player context, not material mechanics");
        Equal(true, (actual["externalPlayerContext"]?["unlinkedHookCount"]?.GetValue<int>() ?? 0) >= 2,
            "real excluded player hooks have an explicit external-context receipt");
        AssertSelectionReferences(actual);
    }

    private static void ParentSourceGraphRetainsItemConditionedPlayerContext()
    {
        PlayerContextSourceExecutions = 0;
        JsonObject graph = SelectionCapture(typeof(PlayerContextEmptyItem), consumer: typeof(PlayerContextRelevant));
        foreach (string hook in new[] { "PlayerContextItemPredicate.CanUseItem(", "PlayerContextRelevant.ModifyWeaponCrit(",
            "PlayerContextRelevant.OnHitNPCWithProj(", "PlayerContextRelevant.OnHitNPCWithItem(",
            "PlayerContextRelevant.ModifyHitNPCWithProj(" })
            Equal(true, SelectionNode(graph, hook)?["values"] is JsonObject,
                "item-conditioned source remains inspectable: " + hook);
        string text = graph.ToJsonString();
        Equal(true, text.Contains("Terraria.Item.type", StringComparison.Ordinal)
            && text.Contains("Terraria.Projectile.type", StringComparison.Ordinal)
            && text.Contains(".wet", StringComparison.Ordinal),
            "identity and live conditions remain source evidence, not evaluated facts");
        Equal(0, PlayerContextSourceExecutions, "conditional discovery never executes predicates or hooks");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphRetainsStateLinkedPlayerContext()
    {
        PlayerContextSourceExecutions = 0;
        JsonObject graph = SelectionCapture(typeof(PlayerContextStateItem), consumer: typeof(PlayerContextState));
        JsonObject? hook = SelectionNode(graph, "PlayerContextState.OnHitNPCWithItem(");
        Equal(true, hook?["values"] is JsonObject, "accessory-owned state retains an otherwise unlinked player hook");
        Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge =>
            edge["kind"]?.GetValue<string>() == "registered_field_consumer_candidate"
            && edge["to"]?.GetValue<int>() == hook!["id"]!.GetValue<int>()),
            "state-linked hook has a field-consumer justification");
        string text = graph.ToJsonString();
        Equal(true, text.Contains(".Active", StringComparison.Ordinal) && text.Contains(".wet", StringComparison.Ordinal)
            && text.Contains(".statDefense", StringComparison.Ordinal), "state and live predicate reach their exact guarded effect");
        Equal(false, text.Contains(".Unrelated", StringComparison.Ordinal) || text.Contains(".statManaMax2", StringComparison.Ordinal),
            "field-focused discovery excludes independent player effects");
        Equal(0, graph["externalPlayerContext"]?["unlinkedHookCount"]?.GetValue<int>() ?? 0,
            "a later admitted field consumer is not counted as excluded external context");
        Equal(0, PlayerContextSourceExecutions, "state discovery never runs the accessory or its consumer");
        AssertSelectionReferences(graph);
    }

    private class PlayerContextOpaquePredicate
    {
        public virtual bool Matches() => false;
    }
    private sealed class PlayerContextOpaqueOverride : PlayerContextOpaquePredicate
    {
        public Item Candidate = null!;
        public override bool Matches() => Candidate.type == 61;
    }
    private sealed class PlayerContextOpaque : ModPlayer
    {
        public PlayerContextOpaquePredicate Other = null!;
        public override bool CanUseItem(Item item) => Other.Matches();
    }
    private sealed class PlayerContextIdentity : ModPlayer
    {
        public override bool CanUseItem(Item item) => IsItem(item);
        private static bool IsItem(object value) => value is Item;
        public override bool CanShoot(Item item) => RuntimeType(item).Name.Length > 0;
        private static Type RuntimeType(Item item) => item.GetType();
    }

    private static void ParentSourceGraphPreservesOpaqueAndIdentityPlayerContext()
    {
        JsonObject opaque = SelectionCapture(typeof(PlayerContextEmptyItem), consumer: typeof(PlayerContextOpaque));
        Equal(true, SelectionNode(opaque, "PlayerContextOpaque.CanUseItem(")?["values"] is JsonObject,
            "unknown virtual receiver cannot prove that the hook is unrelated to the parent");
        Equal(true, opaque["unresolved"]!.ToJsonString().Contains("player_context_dependency_unresolved", StringComparison.Ordinal),
            "unknown dispatch is explicitly unresolved, never an exact parent applicability claim");
        Equal(true, SelectionNode(opaque, "PlayerContextOpaqueOverride.Matches(") is null,
            "conservative admission must not select an arbitrary subtype override");
        AssertSelectionReferences(opaque);

        JsonObject identity = SelectionCapture(typeof(PlayerContextEmptyItem), consumer: typeof(PlayerContextIdentity));
        foreach (string hook in new[] { "PlayerContextIdentity.CanUseItem(", "PlayerContextIdentity.CanShoot(" })
            Equal(true, SelectionNode(identity, hook)?["values"] is JsonObject,
                "Item identity survives object-typed helpers and Object.GetType: " + hook);
        AssertSelectionReferences(identity);
    }

}
