"""Confirmed firmware mode IDs; OpenRGB indices keep Direct/Static/Off stable.
SPDX-License-Identifier: GPL-2.0-or-later
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Mode:
    name: str
    value: int
    colors: bool
    animated: bool = False


# Speed register values follow the related ENE implementation: 4 slow, 0 fast.
SPEED_SLOWEST = 4
SPEED_FASTEST = 0
SPEED_NORMAL = 2

MODES = (
    Mode('Direct', 1, True),
    Mode('Static', 1, True),
    Mode('Off', 0, False),  # Black static frame; retain previous colors in software.
    Mode('Breathing', 2, True, True),
    Mode('Flashing', 3, True, True),
    Mode('Spectrum Cycle', 4, False, True),
    Mode('Rainbow', 5, False, True),
    Mode('Chase Fade', 7, True, True),
    Mode('Chase Fade Rainbow', 8, False, True),
    Mode('Chase', 9, True, True),
    Mode('Chase Rainbow', 10, False, True),
    Mode('Random Flicker', 13, True, True),
    Mode('Stack', 14, False, True),
    Mode('Pong', 15, False, True),
    Mode('Fill Up', 16, False, True),
)


def validate_mode(index, speed):
    if type(index) is not int or not 0 <= index < len(MODES):
        raise ValueError('Unsupported mode')
    if type(speed) is not int or not 0 <= speed <= 4 or (not MODES[index].animated and speed != 0):
        raise ValueError('Unsupported speed')
