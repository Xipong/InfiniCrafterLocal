#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.VFX;

namespace InfiniCrafterLocal.Common.Models;
internal static class VfxContourValidation
{
    internal static void Vector(float[]? p, float limit, string label, bool positive = false)
    {
        if (p is null || p.Length != 2)
            throw new InvalidDataException("geometry " + label + " requires two coordinates");
        foreach (float v in p)
        {
            VfxMaterialValidation.Range(v, -limit, limit, label);
            if (positive && v <= 0)
                throw new InvalidDataException("geometry " + label + " must be positive");
        }
    }

    internal static void Fields(string[] expected, params (string name, object? value)[] fields)
    {
        foreach (var(name, value)in fields)
            if (expected.Contains(name) != (value is not null))
                throw new InvalidDataException("geometry field " + name + " is missing or foreign to this branch");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxContourNode
{
    [JsonRequired]
    public string Id { get; set; } = "";

    [JsonRequired]
    public string Kind { get; set; } = "";

    private float[]? _From;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[]? From { get => _From; set => _From = value ?? throw new InvalidDataException("geometry.From cannot be null"); }

    private float[]? _To;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[]? To { get => _To; set => _To = value ?? throw new InvalidDataException("geometry.To cannot be null"); }

    private float[][]? _Points;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[][]? Points { get => _Points; set => _Points = value ?? throw new InvalidDataException("geometry.Points cannot be null"); }

    private float[]? _Center;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[]? Center { get => _Center; set => _Center = value ?? throw new InvalidDataException("geometry.Center cannot be null"); }

    private float? _RadiusX;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? RadiusX { get => _RadiusX; set => _RadiusX = value ?? throw new InvalidDataException("geometry.RadiusX cannot be null"); }

    private float? _RadiusY;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? RadiusY { get => _RadiusY; set => _RadiusY = value ?? throw new InvalidDataException("geometry.RadiusY cannot be null"); }

    private float? _StartRadians;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? StartRadians { get => _StartRadians; set => _StartRadians = value ?? throw new InvalidDataException("geometry.StartRadians cannot be null"); }

    private float? _SweepRadians;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? SweepRadians { get => _SweepRadians; set => _SweepRadians = value ?? throw new InvalidDataException("geometry.SweepRadians cannot be null"); }

    private int? _Segments;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Segments { get => _Segments; set => _Segments = value ?? throw new InvalidDataException("geometry.Segments cannot be null"); }

    private string? _Source;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Source { get => _Source; set => _Source = value ?? throw new InvalidDataException("geometry.Source cannot be null"); }

    private float[]? _Translate;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[]? Translate { get => _Translate; set => _Translate = value ?? throw new InvalidDataException("geometry.Translate cannot be null"); }

    private float[]? _Scale;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[]? Scale { get => _Scale; set => _Scale = value ?? throw new InvalidDataException("geometry.Scale cannot be null"); }

    private float? _RotationRadians;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? RotationRadians { get => _RotationRadians; set => _RotationRadians = value ?? throw new InvalidDataException("geometry.RotationRadians cannot be null"); }

    private float[][]? _Via;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[][]? Via { get => _Via; set => _Via = value ?? throw new InvalidDataException("geometry.Via cannot be null"); }

    private string[]? _sources;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string[]? Sources { get => _sources; set => _sources = value ?? throw new InvalidDataException("geometry.sources cannot be null"); }

    private float? _start, _end;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? Start { get => _start; set => _start = value ?? throw new InvalidDataException("geometry.start cannot be null"); }

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? End { get => _end; set => _end = value ?? throw new InvalidDataException("geometry.end cannot be null"); }

    internal void Validate()
    {
        string[] fields = Kind switch
        {
            "line" => new[]
            {
                "From",
                "To"
            },
            "polyline" => new[]
            {
                "Points"
            },
            "ellipseArc" => new[]
            {
                "Center",
                "RadiusX",
                "RadiusY",
                "StartRadians",
                "SweepRadians",
                "Segments"
            },
            "transform" => new[]
            {
                "Source",
                "Translate",
                "Scale",
                "RotationRadians"
            },
            "close" => new[]
            {
                "Source",
                "Via"
            },
            "concat" => new[]
            {
                "Sources"
            },
            "trim" => new[]
            {
                "Source",
                "Start",
                "End"
            },
            _ => throw new InvalidDataException("unknown contour kind")};
        VfxContourValidation.Fields(fields, ("From", From), ("To", To), ("Points", Points), ("Center", Center), ("RadiusX", RadiusX), ("RadiusY", RadiusY), ("StartRadians", StartRadians), ("SweepRadians", SweepRadians), ("Segments", Segments), ("Source", Source), ("Translate", Translate), ("Scale", Scale), ("RotationRadians", RotationRadians), ("Via", Via), ("Sources", Sources), ("Start", Start), ("End", End));
        foreach (var v in new[]
        {
            From,
            To,
            Center,
            Translate
        }

        )
            if (v is not null)
                VfxContourValidation.Vector(v, 512, "position");
        if (Scale is not null)
            VfxContourValidation.Vector(Scale, 4, "scale");
        if (Points is not null)
        {
            if (Points.Length is < 2 or > 64)
                throw new InvalidDataException("geometry points count 2..64");
            foreach (var p in Points)
                VfxContourValidation.Vector(p, 512, "point");
        }

        if (Via is not null)
        {
            if (Via.Length > 8)
                throw new InvalidDataException("geometry via count <=8");
            foreach (var p in Via)
                VfxContourValidation.Vector(p, 512, "via");
        }

        if (Sources is not null && (Sources.Length is < 2 or > 16 || Sources.Any(x => string.IsNullOrWhiteSpace(x))))
            throw new InvalidDataException("concat sources require 2..16 references");
        if (Start is { } start)
            VfxMaterialValidation.Range(start, 0, 1, "trim start");
        if (End is { } end)
            VfxMaterialValidation.Range(end, 0, 1, "trim end");
        if (Source is not null && (string.IsNullOrWhiteSpace(Source) || Source.Length > 48))
            throw new InvalidDataException("invalid contour reference");
        foreach (var r in new[]
        {
            RadiusX,
            RadiusY
        }

        )
            if (r is { } radius)
                VfxMaterialValidation.Range(radius, 0, 256, "radius");
        foreach (var a in new[]
        {
            StartRadians,
            SweepRadians,
            RotationRadians
        }

        )
            if (a is { } angle)
                VfxMaterialValidation.Range(angle, -MathF.Tau, MathF.Tau, "angle");
        if (Segments is { } count && count is < 3 or > 64)
            throw new InvalidDataException("geometry segments 3..64");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxContourTransform
{
    [JsonRequired]
    public float[] Translate { get; set; } = null !;

    [JsonRequired]
    public float[] Scale { get; set; } = null !;

    [JsonRequired]
    public float RotationRadians { get; set; }

    internal void Validate()
    {
        VfxContourValidation.Vector(Translate, 512, "translate");
        VfxContourValidation.Vector(Scale, 4, "scale");
        VfxMaterialValidation.Range(RotationRadians, -MathF.Tau, MathF.Tau, "rotation");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxContourMaterial
{
    [JsonRequired]
    public VfxTextureSpec Texture { get; set; } = null !;

    [JsonRequired]
    public string Sampling { get; set; } = "";

    [JsonRequired]
    public RuntimeRgbSpec ColorStart { get; set; } = null !;

    [JsonRequired]
    public RuntimeRgbSpec ColorEnd { get; set; } = null !;

    [JsonRequired]
    public float OpacityStart { get; set; }

    [JsonRequired]
    public float OpacityEnd { get; set; }

    internal void Validate()
    {
        if (Texture is null || ColorStart is null || ColorEnd is null)
            throw new InvalidDataException("geometry material requires texture/colors");
        Texture.Validate();
        if (Texture.Source == "impact" || Texture.Uv is null)
            throw new InvalidDataException("geometry requires fresh texture UV and disallows impact");
        ColorStart.Validate();
        ColorEnd.Validate();
        VfxMaterialValidation.Choice(Sampling, "sampling", "point", "linear");
        VfxMaterialValidation.Range(OpacityStart, 0, 1, "opacityStart");
        VfxMaterialValidation.Range(OpacityEnd, 0, 1, "opacityEnd");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxContourMapping
{
    private string? _addressMode;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? AddressMode { get => _addressMode; set => _addressMode = value ?? throw new InvalidDataException("mapping.addressMode cannot be null"); }

    private float[]? _Origin;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[]? Origin { get => _Origin; set => _Origin = value ?? throw new InvalidDataException("mapping.Origin cannot be null"); }

    private float[]? _Size;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float[]? Size { get => _Size; set => _Size = value ?? throw new InvalidDataException("mapping.Size cannot be null"); }

    private string? _Mode;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Mode { get => _Mode; set => _Mode = value ?? throw new InvalidDataException("mapping.Mode cannot be null"); }

    private float? _RepeatLengthPx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? RepeatLengthPx { get => _RepeatLengthPx; set => _RepeatLengthPx = value ?? throw new InvalidDataException("mapping.RepeatLengthPx cannot be null"); }

    private float? _ScrollPxPerTick;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? ScrollPxPerTick { get => _ScrollPxPerTick; set => _ScrollPxPerTick = value ?? throw new InvalidDataException("mapping.ScrollPxPerTick cannot be null"); }

    internal void Validate(bool fill)
    {
        VfxContourValidation.Fields(fill ? new[] { "Origin", "Size", "AddressMode" } : new[] { "Mode", "RepeatLengthPx", "ScrollPxPerTick" }, ("Origin", Origin), ("Size", Size), ("AddressMode", AddressMode), ("Mode", Mode), ("RepeatLengthPx", RepeatLengthPx), ("ScrollPxPerTick", ScrollPxPerTick));
        if (fill)
        {
            VfxMaterialValidation.Choice(AddressMode, "addressMode", "clamp", "repeat");
            VfxContourValidation.Vector(Origin, 512, "mapping origin");
            VfxContourValidation.Vector(Size, 4096, "mapping size", true);
            if (Size!.Any(x => x < .001f))
                throw new InvalidDataException("mapping size below .001");
        }
        else
        {
            VfxMaterialValidation.Choice(Mode, "mapping mode", "stretch", "repeat");
            VfxMaterialValidation.Range(RepeatLengthPx!.Value, 1, 512, "repeat length");
            VfxMaterialValidation.Range(ScrollPxPerTick!.Value, -32, 32, "scroll");
            if (Mode == "stretch" && (RepeatLengthPx != 1 || ScrollPxPerTick != 0))
                throw new InvalidDataException("stretch requires neutral repeat length 1 and scroll 0");
        }
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxContourDraw
{
    [JsonRequired]
    public string Op { get; set; } = "";

    [JsonRequired]
    public VfxContourMaterial Material { get; set; } = null !;

    [JsonRequired]
    public VfxContourMapping Mapping { get; set; } = null !;

    private VfxNumericProfileSpec? _opacityProfile;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public VfxNumericProfileSpec? OpacityProfile { get => _opacityProfile; set => _opacityProfile = value ?? throw new InvalidDataException("opacityProfile cannot be null"); }

    private string? _Contour;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Contour { get => _Contour; set => _Contour = value ?? throw new InvalidDataException("draw.Contour cannot be null"); }

    private string? _First;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? First { get => _First; set => _First = value ?? throw new InvalidDataException("draw.First cannot be null"); }

    private string? _Second;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Second { get => _Second; set => _Second = value ?? throw new InvalidDataException("draw.Second cannot be null"); }

    private float? _WidthPx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? WidthPx { get => _WidthPx; set => _WidthPx = value ?? throw new InvalidDataException("draw.WidthPx cannot be null"); }

    private string? _Join;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Join { get => _Join; set => _Join = value ?? throw new InvalidDataException("draw.Join cannot be null"); }

    private string? _Cap;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Cap { get => _Cap; set => _Cap = value ?? throw new InvalidDataException("draw.Cap cannot be null"); }

    private float? _MiterLimit;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? MiterLimit { get => _MiterLimit; set => _MiterLimit = value ?? throw new InvalidDataException("draw.MiterLimit cannot be null"); }

    internal void Validate()
    {
        var fields = Op switch
        {
            "stroke" => new[]
            {
                "Contour",
                "WidthPx",
                "Join",
                "Cap",
                "MiterLimit"
            },
            "fill" => new[]
            {
                "Contour"
            },
            "band" => new[]
            {
                "First",
                "Second"
            },
            _ => throw new InvalidDataException("unknown geometry draw op")};
        VfxContourValidation.Fields(fields, ("Contour", Contour), ("First", First), ("Second", Second), ("WidthPx", WidthPx), ("Join", Join), ("Cap", Cap), ("MiterLimit", MiterLimit));
        if (Material is null || Mapping is null)
            throw new InvalidDataException("geometry draw requires material and mapping");
        Material.Validate();
        Mapping.Validate(Op == "fill");
        if (Op == "fill" ? OpacityProfile is not null : OpacityProfile is null)
            throw new InvalidDataException("length opacityProfile belongs to stroke/band");
        OpacityProfile?.Validate(1);
        if (Op == "stroke")
        {
            VfxMaterialValidation.Range(WidthPx!.Value, 0, 128, "stroke width");
            VfxMaterialValidation.Choice(Join, "stroke join", "bevel", "miter");
            VfxMaterialValidation.Choice(Cap, "stroke cap", "butt", "square");
            VfxMaterialValidation.Range(MiterLimit!.Value, 1, 8, "miter limit");
        }
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxContourSpec
{
    [JsonRequired]
    public string Attachment { get; set; } = "";

    [JsonRequired]
    public string RotationFrame { get; set; } = "";

    [JsonRequired]
    public VfxContourTransform TransformStart { get; set; } = null !;

    [JsonRequired]
    public VfxContourTransform TransformEnd { get; set; } = null !;

    [JsonRequired]
    public VfxContourNode[] Contours { get; set; } = null !;

    [JsonRequired]
    public VfxContourDraw[] Draws { get; set; } = null !;

    internal int RequiredDrawBudget()
    {
        var paths = VfxContourGeometry.Resolve(Contours);
        int cost = 0;
        foreach (var draw in Draws)
        {
            int triangles = draw.Op switch
            {
                "fill" => VfxContourGeometry.Fill(paths[draw.Contour!]).Length,
                "stroke" => draw.WidthPx == 0 ? 0 : 3 * (paths[draw.Contour!].Length - 1) + 2,
                "band" => VfxContourGeometry.Band(paths[draw.First!], paths[draw.Second!]).Length,
                _ => throw new InvalidDataException("unknown contour draw")};
            cost += (triangles + 1) / 2;
        }

        return cost;
    }

    internal void Validate()
    {
        VfxMaterialValidation.Choice(Attachment, "geometry attachment", "world", "source");
        VfxMaterialValidation.Choice(RotationFrame, "geometry rotationFrame", "world", "source");
        if (TransformStart is null || TransformEnd is null || Draws is null || Draws.Length is < 1 or > 16)
            throw new InvalidDataException("geometry requires transforms and 1..16 draws");
        TransformStart.Validate();
        TransformEnd.Validate();
        var paths = VfxContourGeometry.Resolve(Contours);
        int count = 0;
        foreach (var d in Draws)
        {
            if (d is null)
                throw new InvalidDataException("geometry draw cannot be null");
            d.Validate();
            Microsoft.Xna.Framework.Vector2[] Get(string? id) => id is not null && paths.TryGetValue(id, out var p) ? p : throw new InvalidDataException("unknown geometry draw contour " + id);
            var triangles = d.Op switch
            {
                "fill" => VfxContourGeometry.Fill(Get(d.Contour)),
                "band" => VfxContourGeometry.Band(Get(d.First), Get(d.Second)),
                _ => VfxContourGeometry.Stroke(Get(d.Contour), d.WidthPx!.Value, d.Join!, d.Cap!, d.MiterLimit!.Value)};
            count += triangles.Length;
            if (count > VfxContourGeometry.MaxTriangles)
                throw new InvalidDataException("geometry exceeds 4096 triangles");
        }
    }
}
