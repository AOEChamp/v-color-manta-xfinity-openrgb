# Saved settings fixture

`saved-static-red.bin` is the 384-byte settings block extracted from a controller save. It contains static red for eight LEDs, marker `5A`, and checksum `3A`.

Offline tests use it to verify restoration from a real serialized settings block. It is not firmware and is not used or written by the flashing tool. The full diagnostic report is not included.
