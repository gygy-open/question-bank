"""Binary stream reader for MTEF (MathType Equation Format).

MTEF uses several non-standard integer encodings:
- nibbles: half-byte units (4 bits) for sizes/spacing
- Mt_uint: variable-length unsigned integer (1 byte if < 255, else 3 bytes)
- mtef16: 16-bit little-endian integer
- fixnum: fixed-point number (integer part + fractional nibble)
- int8_signed: signed 8-bit integer (typeface values use offset +128)
"""

__all__ = ["ByteStream"]


class ByteStream:
    """Reads an MTEF binary stream with nibble-level precision.

    Maintains an internal nibble buffer so that nibble() and uint8()
    calls can be freely mixed. After reading a nibble, the next read
    continues from the remaining half of the byte.
    """

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0          # byte position
        self._nibble: int | None = None  # pending high nibble

    # ── basic readers ──────────────────────────────────────

    def uint8(self) -> int:
        """Read one unsigned byte."""
        if self._nibble is not None:
            # complete the pending nibble with the next byte
            low = self._nibble
            self._nibble = None
            high = self._data[self._pos]
            self._pos += 1
            return (high << 4) | low
        b = self._data[self._pos]
        self._pos += 1
        return b

    def int8(self) -> int:
        """Read one signed byte."""
        v = self.uint8()
        return v - 256 if v >= 128 else v

    def uint16_le(self) -> int:
        """Read a little-endian unsigned 16-bit integer."""
        lo = self.uint8()
        hi = self.uint8()
        return (hi << 8) | lo

    def bytes(self, n: int) -> bytes:
        """Read exactly n bytes."""
        if self._nibble is not None:
            raise RuntimeError("Cannot read aligned bytes with pending nibble")
        chunk = self._data[self._pos:self._pos + n]
        self._pos += n
        return chunk

    # ── MTEF-specific types ────────────────────────────────

    def mt_uint(self) -> int:
        """Read a variable-length unsigned integer (MTEF future-record length).

        Format:
          - If first byte < 255: value is that byte
          - If first byte == 255 (0xFF): next two bytes are low, high
        """
        first = self.uint8()
        if first < 0xFF:
            return first
        lo = self.uint8()
        hi = self.uint8()
        return (hi << 8) | lo

    def mtef16(self) -> int:
        """Read a 16-bit little-endian integer (2 bytes)."""
        return self.uint16_le()

    def fixnum(self) -> float:
        """Read a fixed-point number: integer part + one fractional nibble.

        The integer part is read as a signed byte. The fractional part
        is one nibble (4 bits) giving tenths (0-15 → 0.0-1.5).
        """
        integer = self.int8()
        frac = self.nibble()
        sign = -1 if integer < 0 else 1
        return integer + sign * frac * 0.1

    def nibble(self) -> int:
        """Read one nibble (4 bits), returning 0-15.

        Two consecutive nibble() calls consume one byte: high nibble first,
        then low nibble. Mixing nibble() with uint8() is safe — uint8()
        completes any pending nibble automatically.
        """
        if self._nibble is not None:
            # second nibble from the same byte
            v = self._nibble
            self._nibble = None
            return v
        byte = self._data[self._pos]
        self._pos += 1
        self._nibble = byte & 0x0F  # low nibble pending
        return (byte >> 4) & 0x0F    # high nibble

    def nibble_signed(self) -> int:
        """Read a signed nibble (values 0-7 positive, 8-15 negative)."""
        v = self.nibble()
        return v - 16 if v >= 8 else v

    def peek_uint8(self) -> int:
        """Peek at the next byte without consuming it."""
        b = self._data[self._pos]
        return b

    def align_byte(self) -> None:
        """Discard any pending nibble to align to the next byte boundary.

        After reading nibble-packed data, call this before reading
        byte-aligned fields to skip any padding nibble.
        """
        self._nibble = None

    def unread_byte(self) -> None:
        """Move the stream position back by one byte.

        Used when a record parser consumes a byte that belongs to the
        parent context (e.g., a size marker terminating a template slot).
        """
        if self._pos > 0:
            self._pos -= 1
            self._nibble = None  # Discard any nibble state

    @property
    def remaining(self) -> int:
        """Bytes remaining to read."""
        return len(self._data) - self._pos

    @property
    def position(self) -> int:
        """Current byte position in the stream."""
        return self._pos
