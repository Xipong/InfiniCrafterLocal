using System;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static VfxContourMaterial ContourMaterial() => new()
    {
        Texture = new()
        {
            Source = "library",
            AssetId = "solidPixel",
            Uv = new()
            {
                QuarterTurns = 0,
                MirrorU = false,
                MirrorV = false
            }
        },
        Sampling = "point",
        ColorStart = new()
        {
            R = 255,
            G = 255,
            B = 255
        },
        ColorEnd = new()
        {
            R = 255,
            G = 255,
            B = 255
        },
        OpacityStart = .5f,
        OpacityEnd = .5f
    };
    private static VfxContourTransform ContourTransform() => new()
    {
        Translate = new[]
        {
            0f,
            0f
        },
        Scale = new[]
        {
            1f,
            1f
        },
        RotationRadians = 0
    };
    private static VfxContourSpec ContourGeometry() => new()
    {
        Attachment = "world",
        RotationFrame = "world",
        TransformStart = ContourTransform(),
        TransformEnd = ContourTransform(),
        Contours = new[]
        {
            new VfxContourNode
            {
                Id = "polygon",
                Kind = "polyline",
                Points = new[]
                {
                    new[]
                    {
                        0f,
                        0f
                    },
                    new[]
                    {
                        10f,
                        0f
                    },
                    new[]
                    {
                        10f,
                        4f
                    },
                    new[]
                    {
                        4f,
                        4f
                    },
                    new[]
                    {
                        4f,
                        10f
                    },
                    new[]
                    {
                        0f,
                        10f
                    },
                    new[]
                    {
                        0f,
                        0f
                    }
                }
            }
        },
        Draws = new[]
        {
            new VfxContourDraw
            {
                Op = "fill",
                Contour = "polygon",
                Material = ContourMaterial(),
                Mapping = new()
                {
                    Origin = new[]
                    {
                        0f,
                        0f
                    },
                    Size = new[]
                    {
                        10f,
                        10f
                    },
                    AddressMode = "clamp"
                }
            }
        }
    };
    private static VfxSlotSpec ContourSlot() => new()
    {
        Id = "contour",
        EntityId = "probe",
        Event = "on_hit",
        RendererKind = "contour",
        Anchor = "self",
        Layer = "AfterProjectiles",
        Blend = "alpha",
        StartTick = 0,
        RepeatEvery = 0,
        Duration = 10,
        Geometry = ContourGeometry()
    };
    private static double ContourArea(VfxContourGeometry.Triangle[] t) => t.Sum(x => Math.Abs(VfxContourGeometry.Cross(x.A, x.B, x.C)) * .5);
    private static void ContourRejected(Action action, string label)
    {
        bool rejected = false;
        try
        {
            action();
        }
        catch (System.IO.InvalidDataException)
        {
            rejected = true;
        }

        Equal(true, rejected, label);
    }

    private static void ContourTopologyChecks()
    {
        var g = ContourGeometry();
        g.Validate();
        var p = VfxContourGeometry.Resolve(g.Contours)["polygon"];
        var fill = VfxContourGeometry.Fill(p);
        Equal(4, fill.Length, "concave n-2 triangles");
        Equal(64d, ContourArea(fill), "concave exact area");
        Equal(64d, ContourArea(VfxContourGeometry.Fill(p.Reverse().ToArray())), "reverse winding same area");
        ContourRejected(() => VfxContourGeometry.Fill(new[] { new Vector2(0, 0), new Vector2(10, 10), new Vector2(0, 10), new Vector2(10, 0), new Vector2(0, 0) }), "bow tie rejected");
        ContourRejected(() => VfxContourGeometry.Fill(new[] { Vector2.Zero, Vector2.UnitX, Vector2.UnitY }), "open fill rejected");
        var composition = VfxContourGeometry.Resolve(new[] { new VfxContourNode { Id = "a", Kind = "line", From = new[] { 0f, 0f }, To = new[] { 10f, 0f } }, new VfxContourNode { Id = "b", Kind = "line", From = new[] { 10f, 0f }, To = new[] { 10f, 10f } }, new VfxContourNode { Id = "joined", Kind = "concat", Sources = new[] { "a", "b" } }, new VfxContourNode { Id = "portion", Kind = "trim", Source = "joined", Start = .25f, End = .75f }, new VfxContourNode { Id = "back", Kind = "trim", Source = "joined", Start = .75f, End = .25f } });
        Equal(true, composition["portion"].SequenceEqual(new[] { new Vector2(5, 0), new Vector2(10, 0), new Vector2(10, 5) }), "trim preserves original interior corner");
        Equal(true, composition["back"].SequenceEqual(composition["portion"].Reverse()), "descending trim range explicitly reverses");
        ContourRejected(() => VfxContourGeometry.Resolve(new[] { new VfxContourNode { Id = "a", Kind = "line", From = new[] { 0f, 0f }, To = new[] { 10f, 0f } }, new VfxContourNode { Id = "bad", Kind = "concat", Sources = new[] { "a", "a" } } }), "concat never invents a bridge");
        var a = new[]
        {
            new Vector2(0, 0),
            new Vector2(10, 0)
        };
        var b = new[]
        {
            new Vector2(0, 2),
            new Vector2(3, 2),
            new Vector2(10, 2)
        };
        Equal(20d, ContourArea(VfxContourGeometry.Band(a, b)), "band preserves unequal contour corner fractions");
        ContourRejected(() => VfxContourGeometry.Band(a, b.Reverse().ToArray()), "band reversed direction not guessed");
        var outer = new[]
        {
            new Vector2(-10, -10),
            new Vector2(10, -10),
            new Vector2(10, 10),
            new Vector2(-10, 10),
            new Vector2(-10, -10)
        };
        var inner = outer.Select(x => x * .5f).ToArray();
        Equal(300d, ContourArea(VfxContourGeometry.Band(outer, inner)), "closed band retains hole");
        var twice = outer.Concat(outer.Skip(1)).ToArray();
        ContourRejected(() => VfxContourGeometry.Band(twice, twice.Select(x => x * .5f).ToArray()), "double traversal rejected");
        var stroke = VfxContourGeometry.Stroke(new[] { Vector2.Zero, new Vector2(10, 0), new Vector2(10, 10) }, 2, "bevel", "butt", 2);
        Equal(true, Math.Abs(39.5d - ContourArea(stroke)) < 1e-5, "bevel stroke does not double blend inner join");
        Equal(true, Math.Abs(40d - ContourArea(VfxContourGeometry.Stroke(new[] { Vector2.Zero, new Vector2(10, 0), new Vector2(10, 10) }, 2, "miter", "butt", 2))) < 1e-5, "miter joint exact area");
        Equal(24d, ContourArea(VfxContourGeometry.Stroke(a, 2, "bevel", "square", 2)), "square cap authored extension");
        Equal(true, VfxContourGeometry.Stroke(new[] { Vector2.Zero, new Vector2(10, 0), new Vector2(10, 1), new Vector2(0, 1) }, 4, "bevel", "butt", 2).All(t => float.IsFinite(t.A.X) && float.IsFinite(t.B.X) && float.IsFinite(t.C.X)), "wide hairpin literal coverage remains finite");
        Equal(true, VfxContourGeometry.Stroke(new[] { Vector2.Zero, new Vector2(10, 0), Vector2.Zero, new Vector2(0, 10) }, 2, "bevel", "butt", 2).Length > 0, "reversal does not disappear");
        Equal(true, VfxContourGeometry.Stroke(new[] { new Vector2(4096, 0), new Vector2(4096.00048828125f, 0) }, 2, "bevel", "butt", 2).All(t => float.IsFinite(t.A.X) && float.IsFinite(t.B.X) && float.IsFinite(t.C.X)), "halfpoint float plateau cannot create NaN");
        Equal(0, VfxContourGeometry.Fill(new[] { Vector2.Zero, Vector2.UnitX, Vector2.Zero }).Length, "collapsed closed fill silent");
        ContourRejected(() => VfxContourGeometry.Resolve(new[] { new VfxContourNode { Id = "cycle", Kind = "transform", Source = "cycle", Translate = new[] { 0f, 0f }, Scale = new[] { 1f, 1f }, RotationRadians = 0 } }), "DAG cycle rejected");
    }

    private static void ContourAdmissionChecks()
    {
        var m = new VfxManifestSpec
        {
            RecipeId = "contour_probe",
            Slots = new[]
            {
                ContourSlot()
            }
        };
        string json = m.ToJson();
        Equal(true, json.Contains("geometry"), "contour reaches persisted wire");
        var insufficient = new VfxManifestSpec
        {
            RecipeId = "contour_budget",
            Budget = new()
            {
                MaxDrawCalls = 1
            },
            Slots = new[]
            {
                ContourSlot()
            }
        };
        Equal("", insufficient.ToJson(), "whole contour budget deficiency rejected before runtime");
        var denseSlot = ContourSlot();
        denseSlot.Geometry!.Contours = new[]
        {
            new VfxContourNode
            {
                Id = "rim",
                Kind = "ellipseArc",
                Center = new[]
                {
                    0f,
                    0f
                },
                RadiusX = 32,
                RadiusY = 32,
                StartRadians = 0,
                SweepRadians = MathF.Tau,
                Segments = 64
            }
        };
        denseSlot.Geometry.Draws = Enumerable.Range(0, 16).Select(_ => new VfxContourDraw { Op = "stroke", Contour = "rim", WidthPx = 2, Join = "bevel", Cap = "butt", MiterLimit = 2, Material = ContourMaterial(), Mapping = new() { Mode = "stretch", RepeatLengthPx = 1, ScrollPxPerTick = 0 }, OpacityProfile = new() { Start = 1, Middle = 1, End = 1, Curve = "linear" } }).ToArray();
        int required = denseSlot.Geometry.RequiredDrawBudget();
        Equal(true, required > 512 && required <= 2048, "fine contour composition uses expanded work allowance");
        var denseManifest = new VfxManifestSpec
        {
            RecipeId = "dense_contour",
            Budget = new()
            {
                MaxDrawCalls = required
            },
            Slots = new[]
            {
                denseSlot
            }
        };
        string denseJson = denseManifest.ToJson();
        Equal(true, denseJson.Length > 0, "larger valid geometry compiles without slot padding");
        Equal(required, VfxManifestSpec.FromJson(denseJson).Budget.MaxDrawCalls, "derived expanded budget persists exactly");
        denseSlot.Geometry.Draws[0].WidthPx=0;
        Equal(required-97,denseSlot.Geometry.RequiredDrawBudget(),"explicit zero-width stroke consumes zero declared work");
        foreach(var draw in denseSlot.Geometry.Draws)draw.WidthPx=0;
        Equal(0,denseSlot.Geometry.RequiredDrawBudget(),"entire explicitly silent stroke composition has zero work cost");
        foreach (int legacy in new[]
        {
            0,
            64,
            512
        }

        )
        {
            var saved = new VfxQualityBudgetSpec
            {
                MaxDrawCalls = legacy
            };
            saved.Normalize();
            Equal(legacy, saved.MaxDrawCalls, "existing serialized draw allowance unchanged");
        }

        var ceiling = new VfxQualityBudgetSpec
        {
            MaxDrawCalls = 4096
        };
        ceiling.Normalize();
        Equal(2048, ceiling.MaxDrawCalls, "expanded global work ceiling still bounded");
        var root = JsonNode.Parse(json)!.AsObject();
        root["slots"]![0]!["geometry"]!["contours"]![0]!["radiusX"] = 2;
        Equal(0, VfxManifestSpec.FromJson(root.ToJsonString()).Slots.Length, "foreign contour field rejected");
        string? fixture = Environment.GetEnvironmentVariable("IFC_CONTOUR_COMPILED_FIXTURE");
        if (!string.IsNullOrWhiteSpace(fixture))
        {
            var compiled = JsonNode.Parse(System.IO.File.ReadAllText(fixture))!;
            Equal(1, VfxManifestSpec.FromJson(compiled["vfxManifest"]!.ToJsonString()).Slots.Length, "actual production compiled manifest native admission");
        }

        string? corpus = Environment.GetEnvironmentVariable("IFC_CONTOUR_CORPUS");
        if (!string.IsNullOrWhiteSpace(corpus))
        {
            var cases = JsonNode.Parse(System.IO.File.ReadAllText(corpus))!.AsArray();
            var rows = new System.Collections.Generic.List<object>();
            foreach (var row in cases)
            {
                bool accepted = true;
                int? budget = null;
                string? error = null;
                try
                {
                    var geometry = System.Text.Json.JsonSerializer.Deserialize<VfxContourSpec>(row!["geometry"]!.ToJsonString(), new System.Text.Json.JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
                    geometry.Validate();
                    budget = geometry.RequiredDrawBudget();
                }
                catch (Exception e)
                {
                    accepted = false;
                    error = e.Message;
                }

                rows.Add(new { name = (string? )row!["name"], accepted, error, budget });
            }

            System.IO.File.WriteAllText(corpus + ".native.json", System.Text.Json.JsonSerializer.Serialize(rows));
        }

        var bad = ContourGeometry();
        bad.Draws[0].Contour = "missing";
        ContourRejected(bad.Validate, "draw dangling reference rejected");
        bad = ContourGeometry();
        bad.Draws[0].Material.Texture.AssetId = "not_a_texture";
        ContourRejected(bad.Validate, "unknown library asset rejects");
        bad = ContourGeometry();
        bad.TransformStart.Scale[0] = float.NaN;
        ContourRejected(bad.Validate, "nonfinite transform rejected");
    }

    private static void ContourSnapshotAndMeshChecks()
    {
        WithVfxGeometryQueue((batch, pixel, count, vertices, colors) =>
        {
            const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
            var type = typeof(InfiniDetachedVfxSystem);
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", flags)!;
            var oldClock = clock.GetValue(null);
            bool oldServer = Terraria.Main.dedServ;
            var emissions = (System.Collections.IList)type.GetField("ContourEmissions", flags)!.GetValue(null)!;
            var system = new InfiniDetachedVfxSystem();
            void Invoke(string name, params object[] args) => type.GetMethod(name, flags)!.Invoke(null, args);
            try
            {
                system.OnWorldUnload();
                Terraria.Main.dedServ = false;
                clock.SetValue(null, 100u);
                var data = GeneratedItemData.Placeholder();
                var slot = ContourSlot();
                data.VfxManifest = new()
                {
                    RecipeId = "contour",
                    Budget = new()
                    {
                        MaxDrawCalls = 2
                    },
                    Slots = new[]
                    {
                        slot
                    }
                };
                var frame = new VfxSourceFrame(new Vector2(20, 30), Vector2.UnitX, Vector2.Zero);
                var source = new ShapeSource
                {
                    Position = frame.Position
                };
                var design = type.GetMethod("CopyContours", flags)!.Invoke(null, new object[] { data, slot })!;
                object Property(object x, string name) => x.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.GetValue(x)!;
                var draws = (Array)Property(design, "Draws");
                Microsoft.Xna.Framework.Graphics.VertexPositionColorTexture[] Mesh(float t) => (Microsoft.Xna.Framework.Graphics.VertexPositionColorTexture[])type.GetMethod("BuildContourMesh", flags)!.Invoke(null, new[] { draws.GetValue(0)!, Property(design, "Start"), Property(design, "End"), "world", (object)frame, t, 100UL, "alpha" })!;
                var mesh = Mesh(0);
                Equal(12, mesh.Length, "real mesh owns four triangles");
                Equal(true, mesh.All(v => v.Color.A is >= 127 and <= 128), "material opacity once per vertex");
                Equal(true, mesh.All(v => Math.Abs(v.TextureCoordinate.X - (v.Position.X - 20) / 10) < 1e-6 && Math.Abs(v.TextureCoordinate.Y - (v.Position.Y - 30) / 10) < 1e-6), "planar UV evaluated before scene transform");
                slot.Geometry!.Contours[0].Points![1][0] = 99;
                slot.Geometry.Draws[0].Material.ColorStart.R = 0;
                Equal(true, Mesh(0).SequenceEqual(mesh), "snapshot owns compiled geometry and material");
                var strokeSlot = ContourSlot();
                strokeSlot.Geometry!.Contours = new[]
                {
                    new VfxContourNode
                    {
                        Id = "line",
                        Kind = "line",
                        From = new[]
                        {
                            0f,
                            0f
                        },
                        To = new[]
                        {
                            10f,
                            0f
                        }
                    }
                };
                strokeSlot.Geometry.Draws = new[]
                {
                    new VfxContourDraw
                    {
                        Op = "stroke",
                        Contour = "line",
                        WidthPx = 2,
                        Join = "bevel",
                        Cap = "butt",
                        MiterLimit = 2,
                        Material = ContourMaterial(),
                        Mapping = new()
                        {
                            Mode = "stretch",
                            RepeatLengthPx = 1,
                            ScrollPxPerTick = 0
                        },
                        OpacityProfile = new()
                        {
                            Start = 1,
                            Middle = 0,
                            End = 1,
                            Curve = "linear"
                        }
                    }
                };
                foreach (var scale in new[]
                {
                    new[]
                    {
                        1f,
                        3f
                    },
                    new[]
                    {
                        -2f,
                        3f
                    },
                    new[]
                    {
                        1f,
                        0f
                    }
                }

                )
                {
                    strokeSlot.Geometry.TransformStart.Scale = scale;
                    strokeSlot.Geometry.TransformEnd.Scale = scale;
                    var strokeDesign = type.GetMethod("CopyContours", flags)!.Invoke(null, new object[] { data, strokeSlot })!;
                    var draw = ((Array)Property(strokeDesign, "Draws")).GetValue(0)!;
                    var strokeMesh = (Microsoft.Xna.Framework.Graphics.VertexPositionColorTexture[])type.GetMethod("BuildContourMesh", flags)!.Invoke(null, new[] { draw, Property(strokeDesign, "Start"), Property(strokeDesign, "End"), "world", (object)frame, 0f, 100UL, "alpha" })!;
                    if (scale[1] == 0)
                        Equal(0, strokeMesh.Length, "singular scene scale silent");
                    else
                    {
                        Equal(true, Math.Abs(strokeMesh.Max(v => v.Position.Y) - strokeMesh.Min(v => v.Position.Y) - 2) < 1e-5, "stroke world width independent of anisotropic or negative scale");
                        Equal(true, strokeMesh.Any(v => v.Color.A == 0), "length opacity middle is sampled on straight stroke");
                    }
                }

                foreach (var sampleSlot in new[]
                {
                    ContourSlot(),
                    strokeSlot
                }

                )
                {
                    sampleSlot.Geometry!.TransformStart.Scale = new[]
                    {
                        1f,
                        1f
                    };
                    sampleSlot.Geometry.TransformEnd.Scale = new[]
                    {
                        1f,
                        1f
                    };
                    sampleSlot.Geometry.TransformStart.Translate = new[]
                    {
                        10f,
                        0f
                    };
                    sampleSlot.Geometry.TransformEnd.Translate = new[]
                    {
                        10f,
                        0f
                    };
                    var transformedDesign = type.GetMethod("CopyContours", flags)!.Invoke(null, new object[] { data, sampleSlot })!;
                    var firstDraw = ((Array)Property(transformedDesign, "Draws")).GetValue(0)!;
                    var up = new VfxSourceFrame(Vector2.Zero, Vector2.UnitY, Vector2.Zero);
                    var transformedMesh = (Microsoft.Xna.Framework.Graphics.VertexPositionColorTexture[])type.GetMethod("BuildContourMesh", flags)!.Invoke(null, new[] { firstDraw, Property(transformedDesign, "Start"), Property(transformedDesign, "End"), "source", (object)up, 0f, 100UL, "alpha" })!;
                    Equal(true, Math.Abs(transformedMesh.Min(v => v.Position.Y) - 10) < 1e-4, "source rotation applies to whole local transform incl translation");
                }

                slot = ContourSlot();
                slot.StartTick = 2;
                Equal(true, InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, "probe", slot, "contour-source", frame, source), "snapshot enqueues contour");
                slot = ContourSlot();
                slot.Geometry!.Attachment = "source";
                Equal(true, InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, "probe", slot, "attached-contour", frame, source), "source contour enqueues");
                source.Live = false;
                Invoke("UpdateContours", 100UL);
                Equal(1, emissions.Count, "retirement clears attached contour only");
                Invoke("UpdateContours", 112UL);
                Equal(0, emissions.Count, "delayed contour lifetime expires at due plus duration");
                Invoke("BeginDrawBudgetFrame");
                Equal(false, InfiniDetachedVfxSystem.TrySpendSourceDraw("atomic-contour", 2, 3), "whole mesh over budget rejects");
                Equal(true, InfiniDetachedVfxSystem.TrySpendSourceDraw("atomic-contour", 2, 2), "failed reservation spent nothing");
                Equal(false, InfiniDetachedVfxSystem.TrySpendSourceDraw("atomic-contour", 2, 1), "shared source budget exhausted");
                source = new ShapeSource
                {
                    Position = frame.Position
                };
                slot = ContourSlot();
                slot.Event = "periodic";
                slot.RepeatEvery = 3;
                slot.StartTick = 0;
                data.VfxManifest.Slots = new[]
                {
                    slot
                };
                InfiniDetachedVfxSystem.RegisterPeriodicElements(data, "probe", "periodic-contour", source);
                Invoke("UpdatePeriodicElements", 100UL);
                Equal(1, emissions.Count, "periodic contour registration executes");
                Invoke("UpdatePeriodicElements", 100UL);
                Equal(1, emissions.Count, "same tick no duplicate");
                string? preview = Environment.GetEnvironmentVariable("IFC_CONTOUR_PREVIEW_PATH");
                if (!string.IsNullOrWhiteSpace(preview))
                    System.IO.File.WriteAllText(preview, System.Text.Json.JsonSerializer.Serialize(mesh.Select(v => new { position = new[] { v.Position.X, v.Position.Y }, uv = new[] { v.TextureCoordinate.X, v.TextureCoordinate.Y }, color = new[] { v.Color.R, v.Color.G, v.Color.B, v.Color.A } })));
                if (!string.IsNullOrWhiteSpace(preview))
                {
                    void Export(string suffix, VfxSlotSpec sample)
                    {
                        var snapshot = type.GetMethod("CopyContours", flags)!.Invoke(null, new object[] { data, sample })!;
                        var firstDraw = ((Array)Property(snapshot, "Draws")).GetValue(0)!;
                        var output = (Microsoft.Xna.Framework.Graphics.VertexPositionColorTexture[])type.GetMethod("BuildContourMesh", flags)!.Invoke(null, new[] { firstDraw, Property(snapshot, "Start"), Property(snapshot, "End"), "world", (object)frame, 0f, 100UL, "alpha" })!;
                        System.IO.File.WriteAllText(preview + suffix, System.Text.Json.JsonSerializer.Serialize(output.Select(v => new { position = new[] { v.Position.X, v.Position.Y }, uv = new[] { v.TextureCoordinate.X, v.TextureCoordinate.Y }, color = new[] { v.Color.R, v.Color.G, v.Color.B, v.Color.A } })));
                    }

                    Export(".stroke.json", strokeSlot);
                    var ring = ContourSlot();
                    ring.Geometry!.Contours = new[]
                    {
                        new VfxContourNode
                        {
                            Id = "rim",
                            Kind = "ellipseArc",
                            Center = new[]
                            {
                                0f,
                                0f
                            },
                            RadiusX = 20,
                            RadiusY = 20,
                            StartRadians = 0,
                            SweepRadians = MathF.Tau,
                            Segments = 16
                        },
                        new VfxContourNode
                        {
                            Id = "inner",
                            Kind = "transform",
                            Source = "rim",
                            Scale = new[]
                            {
                                .6f,
                                .6f
                            },
                            Translate = new[]
                            {
                                0f,
                                0f
                            },
                            RotationRadians = 0
                        }
                    };
                    ring.Geometry.Draws = new[]
                    {
                        new VfxContourDraw
                        {
                            Op = "band",
                            First = "rim",
                            Second = "inner",
                            Material = ContourMaterial(),
                            Mapping = new()
                            {
                                Mode = "stretch",
                                RepeatLengthPx = 1,
                                ScrollPxPerTick = 0
                            },
                            OpacityProfile = new()
                            {
                                Start = 1,
                                Middle = 1,
                                End = 1,
                                Curve = "linear"
                            }
                        }
                    };
                    Export(".ring.json", ring);
                }

                system.OnWorldUnload();
                Equal(0, emissions.Count, "world unload clears contours");
            }
            finally
            {
                system.OnWorldUnload();
                clock.SetValue(null, oldClock);
                Terraria.Main.dedServ = oldServer;
            }
        });
    }
}
