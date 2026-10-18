# Runtime protocol

The bridge uses OpenRGB's installed PawnIO AMD PIIX4 transport. It identifies compatible lighting controllers by the five bytes `A8 32 16 E8 8C` at register `0xB500`, scanning lighting addresses `0x70..0x73`. Discovery reads the existing 24-byte color buffer and never applies a startup frame.

## Register access

Select a 16-bit register with SMBus command `0x00`, byte-swapping its word value: selecting `0xB500` sends `0x00B5`. Read command `0x81` returns the selected byte and advances the pointer. Every operation below first selects its register.

| Register | SMBus command | Payload |
| --- | --- | --- |
| `0xE300` | Block write `0x03`, length 24 | Eight color triples in **R,B,G** order |
| `0xE020` | Block write `0x03`, length 4 | `00 01 00 00` (static) |
| `0xE02F` | Byte write `0x01` | `01` (apply) |
| `0xE0A0` | Byte write `0x01` | `AA` (explicit save on E000 v2) |

Off applies a black frame while retaining the previous colors in software. Direct is a software-updated static frame. Save first completes the frame/mode/apply sequence, then sends one save command. Failed application prevents saving. No automatic save retries or firmware operations are performed. Original and patched firmware share the identity signature; the bridge assumes E000 v2 for persistence.

## SDK and synchronization

The server listens only on IPv4 loopback and implements OpenRGB SDK protocol 3. Each DIMM has a fixed eight-LED zone and Direct, Static and Off modes. All modes advertise manual save (`1 << 8`), never automatic save. Update packets `1050`, `1051`, `1052`, `1100` and `1101` are volatile. Save packet `1102` validates the same mode descriptor as `1101` and applies to the selected device only. Invalid sizes, modes and indices are rejected before hardware writes.

Device locks serialize SDK updates. A process lock and OpenRGB's named `Global\Access_SMBUS.HTP.Method` mutex cover each complete hardware transaction. The PIIX4 port is reselected under that mutex before every transaction because other OpenRGB detectors can change it. Software color state is committed after successful hardware operations.

The bridge does not install drivers, use vendor RGB DLLs, remap DIMMs, write DDR SPD or enter the bootloader. Separate firmware tools under `firmware` implement the explicitly selected firmware workflow.
