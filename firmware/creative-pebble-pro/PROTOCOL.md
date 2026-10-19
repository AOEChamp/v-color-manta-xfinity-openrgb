# Pebble Pro custom USB RGB protocol

## Patched v1 wire format

HID control SET_REPORT Output 03, interface 0, 64 bytes including report ID. The message-format identifier at byte 4 is `0x03`; this byte is independent of the patched v1 release name.

| Byte | Set mode/color | Query |
| --- | --- | --- |
| 0..3 | 03 52 47 42 | 03 52 47 42 |
| 4 | 03 | 03 |
| 5 | 01 | 02 |
| 6..8 | R,G,B | Three-byte nonce |
| 9 | Static=0, Cycle=1, Pulsate=2, Off=3 | Reserved |
| 10 | Save=1, volatile=0; other flags rejected | Reserved |
| Remaining | Zero padding | Zero padding |

The USB callback only validates and copies one atomic mailbox word. Persistence,
query property reads and replies run in the application timer after IRQ unlock.

Query response uses **interrupt IN report 03**, not GET_REPORT or a Feature report.
Open the generic HID input collection before issuing the control-output query.
The native endpoint sender copies the stack response synchronously. A query can take time in the application loop.

| Response bytes | Meaning |
| --- | --- |
| 0..3 | 03 52 47 42 |
| 4..6 | Protocol 03, reply opcode 82, capabilities 0F |
| 7 | Raw native mode: FF host static/off, FE host pulse, 01 native cycle |
| 8..10 | Instantaneous R,G,B output |
| 11 | Reserved zero |
| 12..14 | Host R,G,B target, valid for FE/FF only |
| 15 | Reserved zero |
| 16..27 | Saved property record; validate magic/complement/mode before use |
| 28..30 | Echoed nonce |
| 31..63 | Reserved zero |

Raw FF plus black cannot distinguish Static black from Off. The saved record
does preserve the chosen mode. The protocol value identifies this custom build's
interface, not Creative's original firmware version. Replies are validated by
signature, protocol, opcode, capabilities and nonce in the host helper.

A query refuses to replace an unapplied setting command; retry if the control
transfer is rejected as busy. Setting commands still coalesce to the newest
complete mode/color/save tuple. Pause streaming when saving, then verify via
read-back. This is not a durable-save acknowledgment: the native flush wrapper
hides underlying write errors, and the getter may return cached state. Confirm
actual persistence with a power-cycle test before relying on it.
