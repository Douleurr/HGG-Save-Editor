"""Build PKHeX's HeartGold Generations personal table (base stats, types, growth, etc.) from an HGG ROM.

Usage:
    python HGG/build_personal_hgg.py "C:/Roms/NDS/HGG 2.0 Visual 512.nds"

Reads the ROM's personal data (a/0/0/2) and writes PKHeX.Core/Resources/byte/personal/personal_hgg,
re-indexed from HGG's numbering to National Dex numbering so PKHeX can look entries up directly:

    output index     source (HGG personal index)
    0-493            0-493       (same as HeartGold)
    494-1025         544-1075    (HGG stores Gen 5+ species at National + 50)
    1026-1037        496-507     (HeartGold's alternate-form entries: Deoxys, Wormadam, Giratina, Shaymin, Rotom)

Bytes 0x29-0x2B of each entry are PKHeX's own form bookkeeping (form count, form stats index), which the ROM
leaves as padding. They're copied from PKHeX's vanilla HeartGold table, with form indexes moved to the new spot.
"""
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PERSONAL_DIR = REPO / "PKHeX.Core" / "Resources" / "byte" / "personal"
SIZE = 0x2C

NATIONAL_MAX = 1025
HGG_OFFSET = 50               # HGG index = National + 50, for National 494+
VANILLA_FORMS = range(496, 508)
FORMS_START = NATIONAL_MAX + 1  # where HeartGold's form entries land in the output


def rom_file(rom: bytes, path: str) -> bytes:
    """Read a file out of an .nds image by its path in the filesystem (e.g. 'a/0/0/2')."""
    fnt_off, fat_off = struct.unpack_from("<I", rom, 0x40)[0], struct.unpack_from("<I", rom, 0x48)[0]
    dir_id = 0
    parts = path.split("/")
    for depth, name in enumerate(parts):
        sub_off, file_id = struct.unpack_from("<IH", rom, fnt_off + 8 * dir_id)
        pos = fnt_off + sub_off
        while True:
            head = rom[pos]
            if head == 0:
                raise FileNotFoundError(path)
            length = head & 0x7F
            entry = rom[pos + 1: pos + 1 + length].decode("ascii")
            pos += 1 + length
            if head & 0x80:  # directory
                sub_id = struct.unpack_from("<H", rom, pos)[0] & 0x0FFF
                pos += 2
                if entry == name and depth < len(parts) - 1:
                    dir_id = sub_id
                    break
            else:
                if entry == name and depth == len(parts) - 1:
                    start, end = struct.unpack_from("<II", rom, fat_off + 8 * file_id)
                    return rom[start:end]
                file_id += 1
    raise FileNotFoundError(path)


def narc_files(narc: bytes) -> list[bytes]:
    off = struct.unpack_from("<H", narc, 0xC)[0]
    btaf_size, count = struct.unpack_from("<IH", narc, off + 4)
    entries = [struct.unpack_from("<II", narc, off + 12 + 8 * i) for i in range(count)]
    btnf = off + btaf_size
    base = btnf + struct.unpack_from("<I", narc, btnf + 4)[0] + 8
    return [narc[base + s: base + e] for s, e in entries]


def main(rom_path: str) -> None:
    hgg = narc_files(rom_file(Path(rom_path).read_bytes(), "a/0/0/2"))
    vanilla = (PERSONAL_DIR / "personal_hgss").read_bytes()
    assert len(hgg) >= 1076 and all(len(e) == SIZE for e in hgg[:1076]), "unexpected HGG personal data"
    assert len(vanilla) == 508 * SIZE, "unexpected vanilla table"

    def with_pkhex_bytes(entry: bytes, vanilla_index: int | None) -> bytes:
        e = bytearray(entry)
        if vanilla_index is None:
            e[0x29:0x2C] = bytes([1, 0, 0])  # one form, no form entries (new species' forms come later)
            return bytes(e)
        v = vanilla[vanilla_index * SIZE:(vanilla_index + 1) * SIZE]
        e[0x29] = v[0x29]
        form_index = struct.unpack_from("<H", v, 0x2A)[0]
        if form_index:
            form_index = form_index - VANILLA_FORMS.start + FORMS_START
        struct.pack_into("<H", e, 0x2A, form_index)
        return bytes(e)

    out = bytearray()
    for national in range(NATIONAL_MAX + 1):
        if national <= 493:
            out += with_pkhex_bytes(hgg[national], national)
        else:
            out += with_pkhex_bytes(hgg[national + HGG_OFFSET], None)
    for i in VANILLA_FORMS:
        out += with_pkhex_bytes(hgg[i], i)

    dest = PERSONAL_DIR / "personal_hgg"
    dest.write_bytes(out)
    print(f"wrote {dest} ({len(out) // SIZE} entries)")


if __name__ == "__main__":
    main(sys.argv[1])
