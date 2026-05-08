import struct
import hashlib

DELTA = 0x9E3779B9
EXPECTED_TOTAL_STEPS = 999999
TOTAL_LEVELS = 1024  # 2^10, all context paths in the Hanoi tree

# XXTEA encrypted flag (generated separately)
ENCRYPTED_FLAG = b''  # stored in _core.so, not here


def _mx(z, y, total, key, p, e):
    return ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4)) ^ ((total ^ y) + (key[(p & 3) ^ e] ^ z))


def xxtea_encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt data with XXTEA using 128-bit key."""
    if len(data) == 0:
        return data
    key_u32 = list(struct.unpack('<4I', key[:16]))
    v = list(struct.unpack(f'<{len(data) // 4}I', data))
    n = len(v)
    q = 6 + 52 // n
    total = 0
    z = v[n - 1]
    for _ in range(q):
        total = (total + DELTA) & 0xFFFFFFFF
        e = (total >> 2) & 3
        for p in range(n - 1):
            y = v[p + 1]
            v[p] = (v[p] + _mx(z, y, total, key_u32, p, e)) & 0xFFFFFFFF
            z = v[p]
        y = v[0]
        v[n - 1] = (v[n - 1] + _mx(z, y, total, key_u32, n - 1, e)) & 0xFFFFFFFF
        z = v[n - 1]
    return struct.pack(f'<{n}I', *v)


def xxtea_decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt data with XXTEA using 128-bit key."""
    if len(data) == 0:
        return data
    key_u32 = list(struct.unpack('<4I', key[:16]))
    v = list(struct.unpack(f'<{len(data) // 4}I', data))
    n = len(v)
    q = 6 + 52 // n
    total = (DELTA * q) & 0xFFFFFFFF
    y = v[0]
    for _ in range(q):
        e = (total >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - _mx(z, y, total, key_u32, p, e)) & 0xFFFFFFFF
            y = v[p]
        z = v[n - 1]
        v[0] = (v[0] - _mx(z, y, total, key_u32, 0, e)) & 0xFFFFFFFF
        y = v[0]
        total = (total - DELTA) & 0xFFFFFFFF
    return struct.pack(f'<{n}I', *v)


def hash_level_state(level_path: str, goals_str: str) -> str:
    """Hash a level's completion state using goal positions (fixed terrain)."""
    data = f"{level_path}|{goals_str}"
    return hashlib.sha256(data.encode()).hexdigest()


def derive_key(completed_hashes: dict) -> bytes:
    combined = ''.join(completed_hashes[lp] for lp in sorted(completed_hashes))
    return hashlib.sha256(combined.encode()).digest()[:16]


# Try C extension first (harder to reverse), fall back to pure Python
try:
    from _core import decrypt as _c_decrypt
    def _decrypt_flag(key: bytes) -> str:
        return _c_decrypt(key)
except ImportError:
    def _decrypt_flag(key: bytes) -> str:
        return xxtea_decrypt(ENCRYPTED_FLAG, key).rstrip(b'\x00').decode()


def try_get_flag(completed_hashes: dict, total_steps: int) -> str | None:
    if len(completed_hashes) < TOTAL_LEVELS:
        return None
    key = derive_key(completed_hashes)
    return _decrypt_flag(key)
