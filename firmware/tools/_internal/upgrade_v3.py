"""Upgrade exact E000 v2 firmware to v3, preserving live saved settings."""
from unittest.mock import patch
from firmware_image import build as build_v2, SOURCE
from firmware_v3 import build, OUTPUT
import page_installer as installer

ORDER = (0x3480, 0x2000)
READS = sorted({p + d for p in ORDER for d in (-128, 0, 128)} |
               {0, 0x4180, 0x4200, 0x6B00, 0x6E00, 0x6E80, 0xE000, 0xE080, 0xE100})


def install(bus, report, save):
    parent, _ = build_v2(SOURCE.read_bytes())
    with patch.multiple(installer, build=build, OUTPUT=OUTPUT, ORDER=ORDER, READS=READS):
        installer.install(bus, report, save, expected=parent, preserve_settings=True)
