"""Synthetic PE files and a non-executing identification process for UI tests."""
import struct
from types import SimpleNamespace


def program_bytes(name):
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", data, 0x84, 0x14C, 1)
    struct.pack_into("<HH", data, 0x94, 224, 2)
    struct.pack_into("<H", data, 0x98, 0x10B)
    struct.pack_into("<IIII", data, 0x178 + 8, 512, 0x1000, 512, 512)
    markers = (b"Superflip version: charge-flipping -V--version" if "superflip" in name.lower()
               else b"data_structure_from_EDMA edmaatoms" if name.lower() == "edma.exe" else b"unrelated program")
    data[512:512 + len(markers)] = markers
    return bytes(data)


def identification_process(path, arguments):
    output = b"Superflip version: mock-test-build" if arguments else b"Please insert the name of your inputfile"
    return SimpleNamespace(returncode=0, stdout=output, stderr=b"")


def isolate_discovery():
    from contextlib import ExitStack
    from unittest.mock import patch
    context = ExitStack()
    context.enter_context(patch("phase_studio.scientific_tools._probe", identification_process))
    context.enter_context(patch("phase_studio.requirements._standalone_candidates", lambda kind: []))
    return context
