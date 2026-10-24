using System;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static (GeneratedProjectile Host, Projectile Body) OscillationActor(Player owner, int updates,
        float worldSpeed, float worldAmplitude, float worldFrequency, float phase,
        string law = "lateral_velocity_sine", RuntimeMotionWindowSpec? window = null)
    {
        var data = MotionDefinition("{}");
        var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
        entity.Collision.ExtraUpdates = updates - 1;
        var oscillation = new RuntimeOscillationSpec {
            Law = law, FrequencyRadiansPerUpdate = worldFrequency / (60f * updates), PhaseRadians = phase,
            Amplitude = law == "angular_sine" ? worldAmplitude / (60f * updates) : worldAmplitude * 16f / (60f * updates)
        };
        if (window is not null) oscillation.Window = window;
        oscillation.Validate();
        entity.Oscillation = oscillation;
        return MotionActor(data, owner, Vector2.UnitX * (worldSpeed * 16f / (60f * updates)));
    }

    private static Vector2 OriginalLateralStep(Vector2 velocity, float frequency, float phase,
        float amplitude, int age, float minimumSpeed = 0f, float scale = 1f)
    {
        // Frozen u=1 / legacy operation order; not the corrected atan reference.
        float speed = Math.Max(minimumSpeed, velocity.Length());
        Vector2 forward = velocity.SafeNormalize(Vector2.UnitX);
        Vector2 lateral = forward.RotatedBy(MathHelper.PiOver2) * MathF.Sin(age * frequency + phase) * amplitude * scale;
        return (forward * speed + lateral).SafeNormalize(forward) * speed;
    }

    private static void OscillationNear(double expected, double actual, double tolerance, string label)
    {
        if (!double.IsFinite(actual) || Math.Abs(actual - expected) > tolerance)
            throw new InvalidOperationException(label + ": " + expected + " != " + actual + " (tol " + tolerance + ")");
    }

    private static void LateralOscillationPreservesU1AndLegacy()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs).Select(i => new NPC { whoAmI = i }).ToArray();
            foreach (float speed in new[] { 0f, 1e-9f, .001f, 20f })
            foreach (float amplitude in new[] { 0f, .3f, 60f }) {
                var actor = OscillationActor(owner, 1, speed, amplitude, 3f, -.7f);
                Vector2 expected = actor.Body.velocity;
                for (int age = 1; age <= 120; age++) {
                    expected = OriginalLateralStep(expected, 3f / 60f, -.7f, amplitude * 16f / 60f, age);
                    ModifierAge(actor.Host, age); InvokeModifier(actor.Host, "RunResolvedMotion");
                    Equal(expected, actor.Body.velocity, "u=1 retains exact normalized-vector operation order");
                }
            }
            foreach (int updates in new[] { 1, 2, 3, 6 }) {
                var data = MotionDefinition("{}");
                var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                entity.Collision.ExtraUpdates = updates - 1;
                entity.Movement = new() { Name = RuntimeOpcodeNames.MovementName(7), Code = 7,
                    Params = new() { RangeTiles = 20, HomingStrength = .1f, WaveAmplitude = 30 } };
                var actor = MotionActor(data, owner, new Vector2(.02f, .01f));
                Vector2 expected = actor.Body.velocity;
                for (int age = 1; age <= 60 * updates; age++) {
                    expected = OriginalLateralStep(expected, .18f, 0f, 30f, age, minimumSpeed: 1f, scale: .03f);
                    ModifierAge(actor.Host, age); InvokeModifier(actor.Host, "RunResolvedMotion");
                    Equal(expected, actor.Body.velocity, "saved SineHome remains exact at every extraUpdates value");
                }
            }
        });
    }

    private static void LateralOscillationNonlinearSubstepMatrix()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            foreach (int updates in new[] { 1, 2, 3, 6 })
            foreach (float speed in new[] { 0f, 1e-9f, .001f, 20f })
            foreach (float amplitude in new[] { 0f, .3f, 60f })
            foreach (float frequency in new[] { 0f, .1f, 3f, 6f })
            foreach (float phase in new[] { 0f, -.7f, MathHelper.PiOver2 }) {
                var actor = OscillationActor(owner, updates, speed, amplitude, frequency, phase);
                float nativeSpeed = speed * 16f / (60f * updates);
                float nativeAmplitude = amplitude * 16f / (60f * updates);
                float nativeFrequency = frequency / (60f * updates);
                foreach (int age in new[] { 1, 17, 60 * updates }) {
                    actor.Body.velocity = Vector2.UnitX * nativeSpeed;
                    ModifierAge(actor.Host, age); InvokeModifier(actor.Host, "RunResolvedMotion");
                    double expectedAngle = speed == 0f ? 0d
                        : Math.Atan2(MathF.Sin(age * nativeFrequency + phase) * nativeAmplitude, nativeSpeed) / updates;
                    Equal(true, float.IsFinite(actor.Body.velocity.X) && float.IsFinite(actor.Body.velocity.Y), "zero and near-zero components stay finite");
                    OscillationNear(nativeSpeed, actor.Body.velocity.Length(), Math.Max(1e-15, nativeSpeed * 2e-6), "finite preserved scalar speed");
                    if (speed == 0f) Equal(Vector2.Zero, actor.Body.velocity, "stopped body remains stopped without NaN");
                    else OscillationNear(expectedAngle, actor.Body.velocity.ToRotation(), 2e-6, "divide nonlinear angle, not lateral amplitude");
                }
            }
        });
    }

    private static void LateralOscillationWorldTimeAndWindow()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            foreach (int updates in new[] { 1, 2, 3, 6 })
            foreach (float amplitude in new[] { .3f, 60f }) {
                var actor = OscillationActor(owner, updates, 20f, amplitude, 0f, MathHelper.PiOver2);
                double accumulated = 0;
                for (int n = 1; n <= 60 * updates; n++) {
                    float before = actor.Body.velocity.ToRotation();
                    actor.Host.AI();
                    accumulated += MathHelper.WrapAngle(actor.Body.velocity.ToRotation() - before);
                }
                OscillationNear(60d * Math.Atan(amplitude / 20d), accumulated, .0002,
                    "constant phase accumulates same world-time nonlinear turn for all substeps");

                var window = new RuntimeMotionWindowSpec { Phase = "always", Clock = "active", StartDelayTicks = 2, DurationTicks = 3 };
                var gated = OscillationActor(owner, updates, 20f, amplitude, 3f, -.7f, window: window);
                double expected = 0, actual = 0;
                for (int n = 1; n <= 8 * updates; n++) {
                    float before = gated.Body.velocity.ToRotation();
                    float magnitude = gated.Body.velocity.Length();
                    gated.Host.AI();
                    actual += MathHelper.WrapAngle(gated.Body.velocity.ToRotation() - before);
                    if (n > 2 * updates && n <= 5 * updates)
                        expected += Math.Atan2(MathF.Sin(n * (3f / (60f * updates)) - .7f) * (amplitude * 16f / (60f * updates)), magnitude) / updates;
                    OscillationNear(expected, actual, .0001, "window samples world phase and preserves accumulated heading after closing");
                }
                var angular = OscillationActor(owner, updates, 20f, 3f, 3f, -.7f, law: "angular_sine");
                Vector2 expectedAngular = angular.Body.velocity;
                for (int n = 1; n <= 60 * updates; n++) {
                    expectedAngular = expectedAngular.RotatedBy(MathF.Sin(n * (3f / (60f * updates)) - .7f) * (3f / (60f * updates)));
                    ModifierAge(angular.Host, n); InvokeModifier(angular.Host, "RunResolvedMotion");
                    Equal(expectedAngular, angular.Body.velocity, "angular law remains exactly unchanged");
                }
            }
        });
    }

    private static (double X, double Y) LateralDoubleTrajectory(int updates, double speed, double amplitude, double frequency, double phase)
    {
        double heading = 0, x = 0, y = 0;
        for (int n = 1; n <= 60 * updates; n++) {
            heading += Math.Atan((amplitude / speed) * Math.Sin(n * frequency / (60 * updates) + phase)) / updates;
            x += speed / (60 * updates) * Math.Cos(heading);
            y += speed / (60 * updates) * Math.Sin(heading);
        }
        return (x, y);
    }

    private static void LateralOscillationTrajectoryConvergence()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            foreach (float amplitude in new[] { .3f, 60f }) {
                // Nonzero-frequency trajectories converge; coarse/fine samples
                // need not have identical endpoints or cancel heading exactly.
                var reference = LateralDoubleTrajectory(4096, 20, amplitude, 3, .2f);
                double lastError = double.PositiveInfinity;
                foreach (int updates in new[] { 1, 2, 3, 6 }) {
                    var actor = OscillationActor(owner, updates, 20, amplitude, 3, .2f);
                    double x = 0, y = 0;
                    for (int n = 1; n <= 60 * updates; n++) {
                        actor.Host.AI();
                        Equal(true, actor.Host.ShouldUpdatePosition(), "oscillation retains one native free-flight integration");
                        actor.Body.position += actor.Body.velocity;
                        x += actor.Body.velocity.X / 16d; y += actor.Body.velocity.Y / 16d;
                    }
                    var sameStep = LateralDoubleTrajectory(updates, 20, amplitude, 3, .2f);
                    OscillationNear(sameStep.X, x, .001, "actual float native trajectory matches same-step double x");
                    OscillationNear(sameStep.Y, y, .001, "actual float native trajectory matches same-step double y");
                    double error = Math.Sqrt(Math.Pow(x - reference.X, 2) + Math.Pow(y - reference.Y, 2));
                    Equal(true, error < lastError * .8, "timestep refinement converges instead of amplifying turn");
                    lastError = error;
                }
                Equal(true, lastError < (amplitude < 1 ? .03 : .10), "maximum admitted substeps approach continuous reference");
            }
        });
    }
}
