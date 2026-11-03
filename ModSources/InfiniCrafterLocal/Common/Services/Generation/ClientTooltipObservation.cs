#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Text;

namespace InfiniCrafterLocal.Common.Services;

// Client-originated observation, not authenticated server facts. The enclosing
// craft packet supplies owner, request, lane and exact escrow ingredient refs.
internal sealed record ClientTooltipObservation(string[] Lines, string Language, string Status = "observed");

internal static class ClientTooltipWire
{
    // Both parents together remain comfortably below the network packet limit.
    internal const int MaxObservationBytes = 16384;
    internal const int MaxLineCount = 64;
    private const int MaxLanguageBytes = 128;
    private static readonly UTF8Encoding Utf8 = new(false, true);

    internal static void Write(BinaryWriter writer, ClientTooltipObservation? observation)
    {
        if (observation is null) { writer.Write((ushort)0); return; }
        using var stream = new MemoryStream();
        using (var block = new BinaryWriter(stream, Utf8, true))
        {
            if (observation.Lines is null || observation.Lines.Length > MaxLineCount)
                throw new InvalidDataException("invalid tooltip line count");
            byte status = observation.Status switch { "observed" => 1, "refused_utf8_bound" => 2, "refused_invalid_encoding" => 3, _ => throw new InvalidDataException("invalid tooltip status") };
            if (status != 1 && observation.Lines.Length != 0) throw new InvalidDataException("refused tooltip must be empty");
            block.Write(status);
            WriteString(block, observation.Language, MaxLanguageBytes);
            block.Write((byte)observation.Lines.Length);
            foreach (string line in observation.Lines) WriteString(block, line, MaxObservationBytes);
        }
        if (stream.Length > MaxObservationBytes) throw new InvalidDataException("tooltip exceeds packet bound");
        writer.Write((ushort)stream.Length);
        writer.Write(stream.GetBuffer(), 0, (int)stream.Length);
    }

    private static void WriteString(BinaryWriter writer, string text, int limit)
    {
        if (text is null) throw new InvalidDataException("null tooltip string");
        byte[] bytes = Utf8.GetBytes(text);
        if (bytes.Length > limit) throw new InvalidDataException("tooltip string exceeds packet bound");
        writer.Write((ushort)bytes.Length);
        writer.Write(bytes);
    }

    internal static ClientTooltipObservation? Read(BinaryReader reader)
    {
        int size = reader.ReadUInt16();
        if (size == 0) return null;
        if (size > MaxObservationBytes) throw new InvalidDataException("tooltip exceeds packet bound");
        byte[] bytes = reader.ReadBytes(size);
        if (bytes.Length != size) throw new EndOfStreamException("truncated tooltip");
        using var stream = new MemoryStream(bytes, false);
        using var block = new BinaryReader(stream, Utf8);
        string status = block.ReadByte() switch { 1 => "observed", 2 => "refused_utf8_bound", 3 => "refused_invalid_encoding", _ => throw new InvalidDataException("invalid tooltip status") };
        string language = ReadString(block, MaxLanguageBytes);
        int count = block.ReadByte();
        if (count > MaxLineCount) throw new InvalidDataException("invalid tooltip line count");
        var lines = new string[count];
        for (int i = 0; i < count; i++) lines[i] = ReadString(block, MaxObservationBytes);
        if (stream.Position != stream.Length) throw new InvalidDataException("trailing tooltip bytes");
        if (status != "observed" && count != 0) throw new InvalidDataException("refused tooltip must be empty");
        return new ClientTooltipObservation(lines, language, status);
    }

    private static string ReadString(BinaryReader reader, int limit)
    {
        int size = reader.ReadUInt16();
        if (size > limit || size > reader.BaseStream.Length - reader.BaseStream.Position)
            throw new InvalidDataException("invalid tooltip string length");
        return Utf8.GetString(reader.ReadBytes(size));
    }

    internal static ClientTooltipObservation? Freeze(ClientTooltipObservation? observation)
    {
        if (observation is null) return null;
        try
        {
            var frozen = new ClientTooltipObservation(observation.Lines.ToArray(), observation.Language, observation.Status);
            _ = Save(frozen); // Refuse the whole optional observation, never clip it.
            return frozen;
        }
        catch (EncoderFallbackException) { return new ClientTooltipObservation(Array.Empty<string>(), "unknown", "refused_invalid_encoding"); }
        catch (InvalidDataException) { return new ClientTooltipObservation(Array.Empty<string>(), "unknown", "refused_utf8_bound"); }
    }

    internal static byte[] Save(ClientTooltipObservation? value)
    {
        using var stream = new MemoryStream();
        using (var writer = new BinaryWriter(stream, Utf8, true)) Write(writer, value);
        return stream.ToArray();
    }

    internal static ClientTooltipObservation? Restore(byte[] bytes)
    {
        if (bytes is null || bytes.Length > MaxObservationBytes + 2) throw new InvalidDataException("invalid saved tooltip");
        using var stream = new MemoryStream(bytes, false);
        using var reader = new BinaryReader(stream, Utf8);
        ClientTooltipObservation? result = Read(reader);
        if (stream.Position != stream.Length) throw new InvalidDataException("trailing saved tooltip bytes");
        return result;
    }
}
