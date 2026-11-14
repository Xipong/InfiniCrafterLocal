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

    private sealed class PlayerContextInheritedEntity : ModPlayer
    {
        public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (projectile.Center.X > 100f) Player.statDefense += 37;
        }
    }

    private sealed class PlayerContextCastEntity : ModPlayer
    {
        public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            object actor = projectile;
            if (((Entity)actor).Center.X > 100f) Player.statDefense += 39;
        }
    }

    private sealed class PlayerContextErasedHelpers : ModPlayer
    {
        private static bool RightOfOrigin(Entity entity) => entity.Center.X > 100f;
        private static bool Named(object value) => value.GetType().Name.Length > 4;
        public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (RightOfOrigin(projectile)) Player.statDefense += 41;
        }
        public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (Named(item)) Player.statDefense += 43;
        }
    }

    private sealed class PlayerContextByRefHelpers : ModPlayer
    {
        private static bool RightOfOrigin(ref Entity entity) => entity.Center.X > 100f;
        private static bool Named(ref object value) => value.GetType().Name.Length > 4;
        public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            Entity actor = projectile;
            if (RightOfOrigin(ref actor)) Player.statDefense += 61;
        }
        public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            object actor = item;
            if (Named(ref actor)) Player.statDefense += 67;
        }
    }

    private sealed class PlayerContextTypedByRefHelpers : ModPlayer
    {
        private static bool RightOfOrigin(ref Projectile projectile) => projectile.Center.X > 100f;
        private static bool Named(ref Item item) => item.GetType().Name.Length > 4;
        public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (RightOfOrigin(ref projectile)) Player.statDefense += 71;
        }
        public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (Named(ref item)) Player.statDefense += 73;
        }
    }

    private sealed class PlayerContextOpaqueDelegate : ModPlayer
    {
        public Func<bool> ParentCondition = null!;
        internal void SetParent(Item item) => ParentCondition = () => item.damage > 0;
        public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (ParentCondition()) Player.statDefense += 47;
        }
    }

    private sealed class PlayerContextOtherEntity : ModPlayer
    {
        private static bool OwnedBy(Projectile projectile, int owner) => projectile.owner == owner;
        private static bool RightOfTarget(ref Player player, ref NPC target) => player.Center.X > target.Center.X;
        public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            Player player = Player;
            if (RightOfTarget(ref player, ref target)) Player.statDefense += 53;
        }
        public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
        {
            PlayerContextSourceExecutions++;
            if (OwnedBy(projectile, Player.whoAmI) && Player.Center.X > target.Center.X) Player.statDefense += 59;
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

    private static void ParentSourceGraphPreservesInheritedProjectileContext()
    {
        PlayerContextSourceExecutions = 0;
        foreach (Type consumer in new[] { typeof(PlayerContextInheritedEntity), typeof(PlayerContextCastEntity) })
        {
            JsonObject graph = SelectionCapture(typeof(PlayerContextEmptyItem), consumer: consumer);
            Equal(true, SelectionNode(graph, consumer.Name + ".OnHitNPCWithProj(")?["values"] is JsonObject,
                "a void hit hook conditioned on the projectile's inherited Center property remains parent source");
            string text = graph.ToJsonString();
            Equal(true, text.Contains("Terraria.Entity.get_Center(", StringComparison.Ordinal)
                && text.Contains(".statDefense", StringComparison.Ordinal),
                "inherited projectile geometry and its guarded mechanical effect remain inspectable");
            Equal(0, graph["externalPlayerContext"]?["unlinkedHookCount"]?.GetValue<int>() ?? -1,
                "a projectile-dependent hook is not reported as excluded global context");
            AssertSelectionReferences(graph);
        }
        Equal(0, PlayerContextSourceExecutions, "inherited geometry discovery never executes the hit hook");
    }

    private static void ParentSourceGraphPreservesErasedParentContext()
    {
        PlayerContextSourceExecutions = 0;
        foreach (Type consumer in new[] { typeof(PlayerContextErasedHelpers), typeof(PlayerContextByRefHelpers), typeof(PlayerContextTypedByRefHelpers) })
        {
            JsonObject graph = SelectionCapture(typeof(PlayerContextEmptyItem), consumer: consumer);
            foreach (string method in new[] { ".OnHitNPCWithProj(", ".OnHitNPCWithItem(" })
                Equal(true, SelectionNode(graph, consumer.Name + method)?["values"] is JsonObject,
                    "passing a parent actor through a broader helper parameter cannot prove irrelevance: " + consumer.Name + method);
            foreach (string method in new[] { ".RightOfOrigin(", ".Named(" })
                Equal(true, SelectionNode(graph, consumer.Name + method)?["values"] is JsonObject,
                    "retained candidate preserves inspectable helper source: " + consumer.Name + method);
            Equal(0, graph["externalPlayerContext"]?["unlinkedHookCount"]?.GetValue<int>() ?? -1,
                "erased parent arguments do not become excluded global context");
            Equal(true, graph["unresolved"]!.ToJsonString().Contains("player_context_dependency_unresolved", StringComparison.Ordinal),
                "erased/indirect argument admission remains an unresolved candidate, not a proven parent effect");
            AssertSelectionReferences(graph);
        }
        Equal(0, PlayerContextSourceExecutions, "erased helper analysis never executes hooks");
    }

    private static void ParentSourceGraphPreservesOpaqueDelegateContext()
    {
        PlayerContextSourceExecutions = 0;
        JsonObject graph = SelectionCapture(typeof(PlayerContextEmptyItem), consumer: typeof(PlayerContextOpaqueDelegate));
        Equal(true, SelectionNode(graph, "PlayerContextOpaqueDelegate.OnHitNPCWithItem(")?["values"] is JsonObject,
            "a void hook's opaque delegate may capture parent state and remains conditional source");
        Equal(true, graph["unresolved"]!.ToJsonString().Contains("player_context_dependency_unresolved", StringComparison.Ordinal),
            "unknown delegate target remains unresolved rather than proven parent-independent");
        Equal(true, SelectionNode(graph, "PlayerContextOpaqueDelegate.SetParent(") is null,
            "conditional admission does not invent a delegate binding or execute setup");
        Equal(0, graph["externalPlayerContext"]?["unlinkedHookCount"]?.GetValue<int>() ?? -1,
            "opaque parent dependencies do not become excluded global context");
        Equal(0, PlayerContextSourceExecutions, "delegate discovery never invokes the callback");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphStillExcludesOtherEntityContext()
    {
        PlayerContextSourceExecutions = 0;
        JsonObject graph = SelectionCapture(typeof(PlayerContextEmptyItem), consumer: typeof(PlayerContextOtherEntity));
        foreach (string hook in new[] { "PlayerContextOtherEntity.OnHitNPCWithProj(", "PlayerContextOtherEntity.OnHitNPCWithItem(" })
            Equal(true, SelectionNode(graph, hook) is null,
                "other-actor geometry and a typed ownership-only helper remain external context: " + hook);
        Equal(2, graph["externalPlayerContext"]?["unlinkedHookCount"]?.GetValue<int>() ?? -1,
            "independent player and NPC effects remain explicitly excluded");
        Equal(0, PlayerContextSourceExecutions, "negative relevance analysis never executes hooks");
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
