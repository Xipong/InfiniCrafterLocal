#nullable enable
using System;
using Terraria;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// Technical replay ownership for the installed ordered ModPacket transport.
/// Generations identify attachment, not transport streams. Owner claims share
/// one sequence across every source. The server re-stamps admitted claims into
/// its one ordered outbound stream, so owner reconnects cannot rewind peers.
/// No TTL, retired-generation table, eviction, or gameplay admission budget.
/// </summary>
internal sealed class VfxOrderedPeerStream
{
    private sealed record OwnerCursor(Player Player, object? Socket, ulong Sequence);
    private readonly OwnerCursor?[] owners = new OwnerCursor?[Main.maxPlayers];
    private object? relaySocket;
    private ulong relaySequence, nextOwnerOccurrence, nextRelayOccurrence;

    internal ulong NewOwnerOccurrence() => checked(++nextOwnerOccurrence);
    internal ulong NewRelayOccurrence() => checked(++nextRelayOccurrence);

    internal bool AcceptOwner(int owner, ulong sequence)
    {
        if (owner < 0 || owner >= owners.Length || sequence == 0 || Main.player[owner] is not { active: true } player) return false;
        object? socket = Netplay.Clients[owner]?.Socket;
        var previous = owners[owner];
        // RemoteClient.Reset replaces Player; a new accepted connection replaces
        // Socket. Old TCP bytes do not migrate to that new transport session.
        if (previous is not null && ReferenceEquals(previous.Player, player)
            && ReferenceEquals(previous.Socket, socket) && sequence <= previous.Sequence) return false;
        owners[owner] = new(player, socket, sequence);
        return true;
    }

    internal bool AcceptRelay(ulong sequence)
    {
        if (sequence == 0) return false;
        object? socket = Netplay.Connection?.Socket;
        if (!ReferenceEquals(relaySocket, socket)) { relaySocket = socket; relaySequence = 0; }
        if (sequence <= relaySequence) return false;
        relaySequence = sequence;
        return true;
    }

    internal void Clear()
    {
        Array.Clear(owners); relaySocket = null; relaySequence = 0;
        nextOwnerOccurrence = nextRelayOccurrence = 0;
    }
}
