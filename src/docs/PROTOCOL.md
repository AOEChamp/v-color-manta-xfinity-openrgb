# Runtime protocol

The bridge uses OpenRGB's installed PawnIO AMD PIIX4 transport. It identifies compatible lighting controllers by the five bytes `A8 32 16 E8 8C` at register `0xB500`, scanning lighting addresses `0x70..0x73`. Discovery reads the existing 24-byte color buffer and never applies a startup frame.

## Register access

Select a 16-bit register with SMBus command `0x00`, byte-swapping its word value: selecting `0xB500` sends `0x00B5`. Read command `0x81` returns the selected byte and advances the pointer. Every operation below first selects its register.

| Register | SMBus command | Payload |
| --- | --- | --- |
| `0xE300` | Block write `0x03`, length 24 | Eight color triples in **R,B,G** order |
| `0xE020` | Block write `0x03`, length 4 | `00 mode speed 00`; static remains `00 01 00 00` |
| `0xE02F` | Byte write `0x01` | `01` (apply) |
| `0xE0A0` | Byte write `0x01` | `AA` (explicit save on patched E000) |

Off applies a black frame while retaining the previous colors in software. Direct is a software-updated static frame. Save first completes the frame/mode/apply sequence, then sends one save command. Failed application prevents saving. No automatic save retries or firmware operations are performed. Original and patched firmware share the identity signature; the bridge assumes patched E000 for persistence.

Mode and speed occupy `E021` and `E022`. Firmware IDs exposed by the bridge are 2 Breathing, 3 Flashing, 4 Spectrum Cycle, 5 Rainbow, 7/8 Chase Fade fixed/rainbow, 9/10 Chase fixed/rainbow, 13 Random Flicker, 14 Stack, 15 Pong and 16 Fill Up. Speed is 0 fastest through 4 slowest, default 2, following the related ENE implementation. Direction remains zero; random-color and direction controls are not advertised.

SDK indices 0/1/2 remain Direct/Static/Off, with effects appended in the order above. Each animated mode retains its own speed; color updates preserve the selected effect and speed. Random Flicker advertises per-LED color control and writes the E300 buffer for firmware with the mode 13 color patch; older firmware may ignore it. Read-only discovery recognizes supported live effect IDs and speeds. Only Static and Rainbow have been visually tested on this RAM so far.

## SDK and synchronization

The server listens only on IPv4 loopback and implements OpenRGB SDK protocol 3. Each DIMM has a fixed eight-LED zone and 15 modes. All modes advertise manual save (`1 << 8`), never automatic save. Animated modes advertise speed, with inverted limits 4/0; fixed-color modes advertise per-LED color. Update packets `1050`, `1051`, `1052`, `1100` and `1101` are volatile. Save packet `1102` validates the same mode descriptor as `1101` and applies to the selected device only. Invalid sizes, modes, speeds and indices are rejected before hardware writes.

Device locks serialize SDK updates. A process lock and OpenRGB's named `Global\Access_SMBUS.HTP.Method` mutex cover each complete hardware transaction. The PIIX4 port is reselected under that mutex before every transaction because other OpenRGB detectors can change it. Software color state is committed after successful hardware operations.

The bridge does not install drivers, use vendor RGB DLLs, remap DIMMs, write DDR SPD or enter the bootloader. Separate firmware tools under `firmware` implement the explicitly selected firmware workflow.
