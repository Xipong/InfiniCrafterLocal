using System;
using System.Buffers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    // Inject the literal as bytes after fixture serialization: JsonNode/float/double
    // fixture conversion must not erase the counterexample before FromJson sees it.
    private static string HitboxRawNumber(string json, string property, string literal)
        => System.Text.RegularExpressions.Regex.Replace(json,
            "(\"" + property + "\"\\s*:\\s*)[-+0-9.eE]+", "${1}" + literal);

    private static string HitboxNumericFixture()
    {
        var source = RootSpawnFixture(8, 1);
        source.RuntimeProgram.Entities[1].HitboxCurve = HitboxCurve();
        return source.ToJson();
    }

    private static void HitboxRawNumericDomainRefusesOutsideBeforeNarrowing()
    {
        string json = HitboxNumericFixture();
        foreach (string field in new[] { "startScale", "endScale" })
        foreach (string literal in new[] {
            "0.24999999999999997", "8.000000000000002",
            "0.2499999999999999999999999999999999999999999999999999999999",
            "8.0000000000000000000000000000000000000000000000000000000001",
            "2499999999999999999999999999999999999999999999999999999999e-58",
            "8000000000000000000000000000000000000000000000000000000001e-57",
            "1e99999999999999999999999999999999999999999999999999999",
            "1e-99999999999999999999999999999999999999999999999999999",
            "-1e-99999999999999999999999999999999999999999999999999999",
        })
            Equal(true, GeneratedItemData.FromJson(HitboxRawNumber(json, field, literal)) is null,
                "original hitbox domain refuses " + field + "=" + literal);
    }

}
