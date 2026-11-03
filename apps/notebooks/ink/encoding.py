"""Canonical binary encoding used for every Digital Ink hash (spec section 5)."""

import hashlib
import struct
from typing import Any

MAX_SAFE_INT = 2**53 - 1

TAG_NULL = b"\x00"
TAG_INT = b"\x01"
TAG_STR = b"\x02"
TAG_LIST = b"\x03"
TAG_BOOL = b"\x04"
TAG_MAP = b"\x05"


class InkError(Exception):
    """A contract violation. `code` is shared with the JS core through the fixtures."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _encode_str(value: str) -> bytes:
    try:
        raw = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InkError("INVALID_STRING", "text is not valid Unicode") from exc
    return TAG_STR + struct.pack(">I", len(raw)) + raw


def scan(value: Any) -> None:
    """Reject values that cannot be represented identically in JS, Python and C."""
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, float):
        raise InkError("FLOAT_NOT_ALLOWED")
    if isinstance(value, int):
        if not -MAX_SAFE_INT <= value <= MAX_SAFE_INT:
            raise InkError("INT_OUT_OF_RANGE")
        return
    if isinstance(value, str):
        if "\x00" in value:
            raise InkError("INVALID_STRING", "text may not contain U+0000")
        _encode_str(value)
        return
    if isinstance(value, list):
        for item in value:
            scan(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise InkError("INVALID_STRING", "map keys must be ASCII")
            scan(item)
        return
    raise InkError("INVALID_SHAPE", f"unsupported type {type(value).__name__}")


def encode(value: Any) -> bytes:
    if value is None:
        return TAG_NULL
    if isinstance(value, bool):
        return TAG_BOOL + (b"\x01" if value else b"\x00")
    if isinstance(value, float):
        raise InkError("FLOAT_NOT_ALLOWED")
    if isinstance(value, int):
        if not -MAX_SAFE_INT <= value <= MAX_SAFE_INT:
            raise InkError("INT_OUT_OF_RANGE")
        return TAG_INT + struct.pack(">q", value)
    if isinstance(value, str):
        return _encode_str(value)
    if isinstance(value, list):
        return TAG_LIST + struct.pack(">I", len(value)) + b"".join(encode(v) for v in value)
    if isinstance(value, dict):
        parts = [TAG_MAP, struct.pack(">I", len(value))]
        for key in sorted(value):
            if not key.isascii():
                raise InkError("INVALID_STRING", "map keys must be ASCII")
            parts.append(_encode_str(key))
            parts.append(encode(value[key]))
        return b"".join(parts)
    raise InkError("INVALID_SHAPE", f"unsupported type {type(value).__name__}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def op_hash(op: dict[str, Any]) -> str:
    return sha256_hex(encode(op))


CHAIN_GENESIS = sha256_hex(b"tutor.ink.v1.chain")


def chain_next(previous_hex: str, op_hash_hex: str) -> str:
    return sha256_hex(bytes.fromhex(previous_hex) + bytes.fromhex(op_hash_hex))
