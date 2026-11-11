using System;
using System.Reflection;
using System.Linq;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Mono.Cecil.Cil;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData ProjectileOnlyPrefixFixture(int damage = 40)
    {
        var data = GeneratedPrefixFixture("magic");
        data.Id = "projectile-only-prefix-" + damage;
        data.Gameplay.Damage = 0;
        data.RuntimeProgram.Bindings[0].UsePolicy.ContactDamage = false;
        var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Damage.Enabled = true; root.Damage.Damage = damage;
        root.Damage.Knockback = 3; root.Damage.DamageClass = "magic";
        return data;
    }

    private static void ProjectileOnlyNativePrefixEligibilityAndAttack()
    {
        WithGeneratedPrefixScope(() => WithNativeChestRegisteredItem(type => WithGeneratedReforgeBridge(() => {
            using var scope = new SwarmRuntimeScope();
            var owner = Terraria.Main.player[0];
            foreach (int damage in new[] { 40, 9, 2, 1 })
            {
                var data = ProjectileOnlyPrefixFixture(damage);
                var item = GeneratedReforgeItem(type, data);
                var generated = (GeneratedItem)item.ModItem;
                string definition = data.ToNetworkJson();
                Equal("Magic,AnyWeapon", string.Join(",", item.GetPrefixCategories()), "projectile-only categories");
                Equal(true, item.CanHavePrefixes(), "zero body, positive root native eligibility");
                Equal(true, item.Prefix(-3), "zero body native reforge probe");
                // Broken changes damage by -30%. Native rounding rejects a base
                // of one, but accepts two. No invented nonzero body is installed.
                bool applicable = damage > 1;
                Equal(applicable, item.Prefix(PrefixID.Broken), "real native damage-prefix applicability " + damage);
                Equal(0, item.damage, "prefix leaves body damage zero");
                Equal(true, item.noMelee, "authored no contact hitbox survives prefix");
                Equal(false, item.Prefix(PrefixID.Legendary), "foreign melee prefix remains refused");
                owner.inventory[0] = item; owner.selectedItem = 0;
                int expected = applicable ? (int)Math.Round(damage * 0.7f) : damage;
                int spawns = 0;
                using var observer = RootCombatSpawnObserver((source, actual, kb) => {
                    spawns++;
                    Equal(expected, actual, "accepted native prefix reaches real hold-root spawn damage");
                    Equal(0, item.damage, "actual attack source still has zero contact damage");
                });
                try { generated.HoldItem(owner); throw new InvalidOperationException("projectile-only attack missed native spawn"); }
                catch (RootCombatSpawnBoundary) { }
                Equal(1, spawns, "real hold attack reached native projectile spawn boundary");
                var combatBridge = new GeneratedRootCombatSystem();
                try {
                    combatBridge.Load();
                    owner.itemAnimation = item.useAnimation; owner.itemTime = 0;
                    owner.altFunctionUse = 0;
                    Equal(true, generated.CanUseItem(owner), "primary projectile use admitted");
                    try {
                        typeof(Player).GetMethod("ItemCheck_Shoot", RootPrivate)!.Invoke(owner,
                            new object[] { owner.whoAmI, item, 0 });
                        throw new InvalidOperationException("projectile-only primary attack missed native spawn");
                    } catch (TargetInvocationException error) when (RootCombatBoundary(error)) { }
                    Equal(2, spawns, "native primary Shoot also reached projectile spawn");
                } finally { combatBridge.Unload(); }
                Equal(0, item.damage, "attack restores zero body damage");
                Equal(definition, data.ToNetworkJson(), "prefix and attack never alter authored data");
            }
        })));
    }

    private static void ProjectileOnlyNativeReforgeResetAndRoll()
    {
        WithGeneratedPrefixScope(() => WithNativeChestRegisteredItem(type => WithGeneratedReforgeBridge(() => {
            using var peers = new ReviewPeers();
            var data = ProjectileOnlyPrefixFixture();
            peers.Register(data);
            var item = GeneratedReforgeItem(type, data);
            string definition = ((GeneratedItem)item.ModItem).Data.ToNetworkJson();
            Equal(true, item.Prefix(PrefixID.Mythical), "projectile-only starts with real native prefix");
            int prefixedRolls = 0;
            for (int repeat = 0; repeat < 4; repeat++)
            {
                Equal(true, ItemLoader.CanReforge(item), "projectile-only native CanReforge");
                ItemLoader.PreReforge(item);
                item.ResetPrefix();
                Equal(0, item.prefix, "Goblin reset clears projectile-only prefix");
                Equal(true, item.ModItem is GeneratedItem, "native reset reconstructs registered generated item");
                Equal(definition, ((GeneratedItem)item.ModItem).Data.ToNetworkJson(), "reset hydrates exact projectile-only definition");
                Equal(0, item.damage, "reset never gives projectile-only body damage");
                Equal(true, item.Prefix(-2), "projectile-only native Goblin roll " + repeat);
                ItemLoader.PostReforge(item);
                var expected = GeneratedReforgeItem(type, data);
                if (item.prefix != 0)
                {
                    prefixedRolls++;
                    Equal(true, expected.Prefix(item.prefix), "rolled projectile-only prefix remains applicable to fresh instance");
                }
                Equal(GeneratedPrefixStats(expected), GeneratedPrefixStats(item), "Goblin rolls do not compound projectile-only stats " + repeat);
                var actualGenerated = (GeneratedItem)item.ModItem;
                var expectedGenerated = (GeneratedItem)expected.ModItem;
                Equal(expectedGenerated.RootCombatBase(expectedGenerated.Data.RuntimeProgram.TryGetEntity("root")!),
                    actualGenerated.RootCombatBase(actualGenerated.Data.RuntimeProgram.TryGetEntity("root")!),
                    "Goblin rolls do not compound actual root damage or knockback");
                Equal(0, item.damage, "Goblin roll retains zero body damage");
                Equal(true, item.noMelee, "Goblin roll retains no contact hitbox");
                Equal(definition, actualGenerated.Data.ToNetworkJson(), "Goblin roll preserves authored definition");
            }
            Equal(true, prefixedRolls > 0, "bounded native Goblin sequence produces usable projectile-only prefixes");
        })));
    }

    private static void ProjectileOnlyNativePrefixMultipleRoots()
    {
        WithGeneratedPrefixScope(() => WithNativeChestRegisteredItem(type => WithGeneratedReforgeBridge(() => {
            using var scope = new SwarmRuntimeScope();
            var data = ProjectileOnlyPrefixFixture(1);
            var strong = ProjectileOnlyPrefixFixture(40).RuntimeProgram.TryGetEntity("root")!;
            strong.Id = "strong";
            data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(strong).ToArray();
            data.RuntimeProgram.Bindings = data.RuntimeProgram.Bindings.Append(new RuntimeBindingSpec {
                Id = "alternate", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Secondary,
                UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = false, Action = new RuntimeBindingActionSpec {
                    Kind = RuntimeBindingAction.SpawnEntity, TargetId = strong.Id,
                } },
            }).ToArray();
            var item = GeneratedReforgeItem(type, data);
            var generated = (GeneratedItem)item.ModItem;
            string definition = generated.Data.ToNetworkJson();
            Equal(true, item.CanHavePrefixes(), "multiple root native eligibility");
            Equal(true, item.Prefix(PrefixID.Broken), "strong alternate root makes damage prefix applicable despite tiny primary");
            Equal(1, generated.RootCombatBase(data.RuntimeProgram.TryGetEntity("root")!).Damage, "tiny root retains its own rounding");
            Equal(28, generated.RootCombatBase(strong).Damage, "strong root retains its own damage basis");
            var owner = Terraria.Main.player[0]; owner.inventory[0] = item; owner.selectedItem = 0;
            var bridge = new GeneratedRootCombatSystem();
            try {
                bridge.Load();
                foreach (int alternate in new[] { 0, 2 })
                {
                    owner.altFunctionUse = alternate; owner.itemAnimation = item.useAnimation; owner.itemTime = 0;
                    int observed = 0;
                    using var observer = RootCombatSpawnObserver((source, damage, kb) => {
                        observed++;
                        Equal(alternate == 0 ? 1 : 28, damage, "native selected root attack retains its individual prefix rounding");
                        Equal(0, item.damage, "multiple-root attack source stays zero damage");
                    });
                    try {
                        typeof(Player).GetMethod("ItemCheck_Shoot", RootPrivate)!.Invoke(owner,
                            new object[] { owner.whoAmI, item, 0 });
                        throw new InvalidOperationException("multiple-root native attack missed spawn");
                    } catch (TargetInvocationException error) when (RootCombatBoundary(error)) { }
                    Equal(1, observed, "selected multiple-root attack reaches native spawn once");
                }
            } finally { bridge.Unload(); }
            Equal(0, item.damage, "multiple-root item retains zero body damage");
            Equal(definition, generated.Data.ToNetworkJson(), "multiple-root prefix never rewrites authored root damage");
        })));
    }

    private static void ProjectileOnlyNativePrefixBridgeLifecycle()
    {
        WithGeneratedPrefixScope(() => WithNativeChestRegisteredItem(type => {
            var item = GeneratedReforgeItem(type, ProjectileOnlyPrefixFixture());
            var bridge = new GeneratedPrefixCategorySystem();
            try {
                Equal(false, item.CanHavePrefixes(), "uninstalled native zero-body gate");
                bridge.Load();
                Equal(true, item.CanHavePrefixes(), "installed bridge eligibility");
                bridge.Unload();
                Equal(false, item.CanHavePrefixes(), "unload restores native eligibility");
                using (var mutant = new ILHook(typeof(Item).GetMethod(nameof(Item.CanHavePrefixes))!, il => {
                    var cursor = new ILCursor(il);
                    if (!cursor.TryGotoNext(MoveType.Before, i => i.MatchLdfld<Item>(nameof(Item.damage))))
                        throw new InvalidOperationException("native eligibility mutation site missing");
                    cursor.Remove(); cursor.Emit(OpCodes.Pop); cursor.Emit(OpCodes.Ldc_I4_0);
                })) {
                    bool refused = false;
                    try { bridge.Load(); }
                    catch (Exception error) { refused = error.ToString().Contains("native source shape changed", StringComparison.Ordinal); }
                    Equal(true, refused, "changed native damage gate fails closed");
                    foreach (string field in new[] { "_categoriesHook", "_eligibilityHook", "_statEffectHook" })
                        Equal(true, typeof(GeneratedPrefixCategorySystem).GetField(field, RootPrivate)!.GetValue(bridge) is null,
                            "failed install disposes " + field);
                }
                bridge.Load();
                Equal(true, item.CanHavePrefixes(), "bridge reinstalls after failed native shape");
            } finally { bridge.Unload(); }
        }));
    }

    private static void ProjectileOnlyNativePrefixGuards()
    {
        WithGeneratedPrefixScope(() => WithNativeChestRegisteredItem(type => WithGeneratedReforgeBridge(() => {
            foreach (string control in new[] { "zero", "disabled", "unspawnable", "unbound", "stack", "ammo", "type-set" })
            {
                var data = ProjectileOnlyPrefixFixture();
                var root = data.RuntimeProgram.TryGetEntity("root")!;
                if (control == "zero") root.Damage.Damage = 0;
                if (control == "disabled") root.Damage.Enabled = false;
                if (control == "unspawnable") root.Spawn.Enabled = false;
                if (control == "unbound") data.RuntimeProgram.Bindings = Array.Empty<RuntimeBindingSpec>();
                if (control == "stack") data.Gameplay.MaxStack = 99;
                if (control == "ammo") { data.Gameplay.AmmoCategory = "bullet"; data.Gameplay.AmmoProjectileId = ProjectileID.Bullet; }
                var item = GeneratedReforgeItem(type, data);
                bool original = ItemID.Sets.CanGetPrefixes[type];
                try {
                    if (control == "type-set") ItemID.Sets.CanGetPrefixes[type] = false;
                    Equal(false, item.CanHavePrefixes(), control + " native eligibility guard");
                    Equal(false, item.Prefix(-3), control + " native probe guard");
                    Equal(false, item.Prefix(PrefixID.Broken), control + " native apply guard");
                    Equal(0, item.damage, control + " body never mutated");
                } finally { ItemID.Sets.CanGetPrefixes[type] = original; }
            }
            var projectile = GeneratedReforgeItem(type, ProjectileOnlyPrefixFixture());
            Equal(true, projectile.Prefix(PrefixID.Mythical), "projectile-only full magic prefix accepted");
            Equal(0, projectile.damage, "Mythical cannot invent body damage");
            Equal(18, projectile.mana, "Mythical applies native mana reduction");
            Equal(46, ((GeneratedItem)projectile.ModItem).RootCombatBase(
                ((GeneratedItem)projectile.ModItem).Data.RuntimeProgram.TryGetEntity("root")!).Damage,
                "Mythical damage multiplier reaches authored forty root");
            var ordinary = GeneratedReforgeItem(type, GeneratedReforgeFixture("magic"));
            Equal(true, ordinary.CanHavePrefixes(), "ordinary generated weapon eligibility unchanged");
            Equal(true, ordinary.Prefix(PrefixID.Mythical), "ordinary generated weapon prefix unchanged");
            var accessory = GeneratedReforgeItem(type, GeneratedReforgeFixture("accessory"));
            Equal(true, accessory.CanHavePrefixes(), "passive accessory eligibility unchanged");
            Equal(true, accessory.Prefix(PrefixID.Warding), "passive accessory prefix unchanged");
            Equal(false, accessory.Prefix(PrefixID.Broken), "passive accessory not treated as weapon");
        })));
    }
}
