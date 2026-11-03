"""Real dncil decoding with synthetic PE metadata and declared method bodies."""
import hashlib
import struct
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/generate"))
import generate_native_hit_status as decoder


class Table(list):
    @property
    def rows(self):
        return self


def synthetic_pe(monkeypatch, tmp_path, code, *, declared_size=None, flags=0x3003, tail=b""):
    import dnfile
    raw = struct.pack("<HHII", flags, 8, len(code) if declared_size is None else declared_size, 0) + code + tail
    method = NS(Name="Test", Rva=4096, Signature=NS(value=b"\x00\x00\x01"))
    ctor = NS(Name=".ctor", Signature=NS(value=bytes.fromhex("2002010c0c")),
              Class=NS(row=NS(TypeNamespace="Microsoft.Xna.Framework", TypeName="Vector2")))
    tables = NS(TypeDef=Table([NS(TypeNamespace="Terraria", TypeName="Player", FieldList=[], MethodList=[NS(row=method)])]),
                MethodDef=Table([method]), MemberRef=Table([ctor]), Constant=Table(),
                Module=Table([NS(Mvid=NS(value=uuid.UUID(int=1).bytes_le))]),
                Assembly=Table([NS(MajorVersion=1, MinorVersion=0, BuildNumber=0, RevisionNumber=0)]))
    pe = NS(net=NS(mdtables=tables), get_data=lambda rva, size: raw[rva - 4096:rva - 4096 + size])
    monkeypatch.setattr(dnfile, "dnPE", lambda path: pe)
    path = tmp_path / "synthetic.dll"
    path.write_bytes(raw)
    return path


def test_decode_consumes_full_declared_large_method_and_hashes_all_il(monkeypatch, tmp_path):
    code = b"\x00" * 100_500 + b"\x2a"
    path = synthetic_pe(monkeypatch, tmp_path, code)
    instructions, _, _, _, method_hash, _, _ = decoder.decode(path, "Player", "Test")
    assert len(instructions) == len(code)
    assert instructions[-1].op == "ret"
    assert instructions[-1].offset == 12 + len(code) - 1
    assert method_hash == hashlib.sha256(code).hexdigest()


def test_decoder_preserves_exact_constructor_metadata(monkeypatch, tmp_path):
    code = b"\x22" + struct.pack("<f", 1) + b"\x22" + struct.pack("<f", 0) + b"\x73\x01\x00\x00\x0a\x26\x2a"
    path = synthetic_pe(monkeypatch, tmp_path, code)
    instructions = decoder.decode(path, "Player", "Test")[0]
    ctor = next(i for i in instructions if i.op == "newobj")
    assert ctor.arg == ("Microsoft.Xna.Framework.Vector2..ctor", "2002010c0c")


def test_helper_expression_carries_exact_local_method_certificate(monkeypatch, tmp_path):
    import dnfile
    code = b"\x02\x04\x28\x02\x00\x00\x06\x26\x2a"
    path = synthetic_pe(monkeypatch, tmp_path, code)
    pe = dnfile.dnPE(str(path))
    helper_code = b"\x22" + struct.pack("<f", 1.25) + b"\x2a"
    helper_raw = bytes([(len(helper_code) << 2) | 2]) + helper_code
    helper = NS(Name="GetAdjustedItemScale", Rva=8192, Signature=NS(value=bytes.fromhex("20010c1208")))
    pe.net.mdtables.MethodDef.append(helper)
    pe.net.mdtables.TypeDef[0].MethodList.append(NS(row=helper))
    original_read = pe.get_data
    pe.get_data = lambda rva, size: helper_raw[rva - 8192:rva - 8192 + size] if rva >= 8192 else original_read(rva, size)
    instructions = decoder.decode(path, "Player", "Test")[0]
    cert = instructions.method_provenance.get("Terraria.Player.GetAdjustedItemScale")
    assert cert == {"status": "certified_source_only", "member": "Terraria.Player.GetAdjustedItemScale",
                    "signature": "20010c1208", "sourceMethodSha256": hashlib.sha256(helper_code).hexdigest(),
                    "sourceModuleVersionId": str(uuid.UUID(int=1))}
    import native_attack_fact_analysis as analysis
    args = (("const", 0),) * 9 + (("call", "Terraria.Player.GetAdjustedItemScale", ("ldarg", 0), ("ldarg", 2)),)
    inputs = analysis.spawn_inputs(instructions, 3, args, instructions.method_provenance)
    assert inputs["ai2"]["provenance"] == cert
    assert inputs["ai2"]["evaluation"] == "unresolved_helper_or_hook_output"


def test_truncated_declared_body_fails_explicitly(monkeypatch, tmp_path):
    path = synthetic_pe(monkeypatch, tmp_path, b"\x2a", declared_size=100_501)
    with pytest.raises(ValueError, match="truncated.*method"):
        decoder.decode(path, "Player", "Test")
