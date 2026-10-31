#nullable enable
using System.IO;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

public sealed class VfxUvTransformSpec
{
    [JsonRequired] public int QuarterTurns { get; set; }
    [JsonRequired] public bool MirrorU { get; set; }
    [JsonRequired] public bool MirrorV { get; set; }
    internal void Validate() { if(QuarterTurns is <0 or >3)throw new InvalidDataException("UV quarterTurns must be 0..3"); }
}
