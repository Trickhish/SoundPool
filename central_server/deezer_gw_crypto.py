"""
Deezer mobile-gateway request signer, ported from the Android TV app
(deezer.android.tv). Replicates the obfuscated AES routine the app uses to turn
a `mobile_auth` TOKEN into the `auth_token` that `api_checkToken` accepts.

Pipeline (matches IlIllllIlIIIlI in the APK):
    decrypted = AES_dec(key=icon_key[:16], hex->bytes(TOKEN))   # custom LE AES
    s1 = decrypted[0:64]; s2 = decrypted[64:80]
    auth_token = hex( AES_enc(key=s2[:16], s1) )

The AES tables and the key hidden in assets/icon2.png are extracted straight from
the APK so there is no transcription risk.
"""

import json
from pathlib import Path

_BASE = Path(__file__).parent
MASK = 0xFFFFFFFF

# ── AES tables (extracted from the decompiled llIlIllllllIll) ─────────────────
_T = json.loads((_BASE / "aes_tables.json").read_text())
RCON  = _T["IIIIlIIIIIIIl"]      # Rcon
SBOX  = _T["IIlIIIlllIIIIlII"]   # forward S-box
ISBOX = _T["IIllIllIllllllII"]   # inverse S-box
TE0   = _T["IIllIlllIIIlIIll"]   # encrypt round tables
TE1   = _T["IIIlllIIlIllIlIl"]
TE2   = _T["llIIllIlIlIlIl"]
TE3   = _T["IIIllllIIlIIlIlI"]
TD0   = _T["lIlllIIIllIllIl"]    # decrypt round tables
TD1   = _T["IllIlllIIlIIllll"]
TD2   = _T["IllIlllIlIIlll"]
TD3   = _T["IlllIIlllIlIIllI"]
TKD0  = _T["IllIllllllIIllI"]    # InvMixColumns key-prep tables
TKD1  = _T["IlIllIIIIlllllI"]
TKD2  = _T["IIlllIIlIllIllII"]
TKD3  = _T["lllIIlIIllIllII"]


def _b8(i):  return (i >> 8) & 255
def _b16(i): return (i >> 16) & 255
def _b24(i): return (i >> 24) & 255


def extract_icon_key() -> str:
    """The 32-char key hidden after the PLTE chunk of assets/icon2.png."""
    data = (_BASE / "apk_extract" / "assets" / "icon2.png").read_bytes()
    i = data.find(b"PLTE")
    c = bytes(data[i + 4 + 90 + k] for k in range(210))
    return bytes(b ^ 64 for b in c)[1:33].decode("latin-1")


def _pack(b):
    """4 bytes -> little-endian 32-bit words."""
    return [(b[j] | (b[j+1] << 8) | (b[j+2] << 16) | (b[j+3] << 24)) & MASK
            for j in range(0, len(b), 4)]


def _unpack(words):
    out = bytearray()
    for w in words:
        out += bytes((w & 255, _b8(w), _b16(w), _b24(w)))
    return out


class AES:
    def __init__(self, key: bytes):
        self.key = key[:16]
        self.rounds = {16: 10, 24: 12, 32: 14}[len(self.key)]
        self.rk = self._expand(self.key)

    def _expand(self, key):
        nk = len(key) // 4
        total = 4 * (self.rounds + 1)
        w = _pack(key)
        for i in range(nk, total):
            t = w[i - 1]
            if i % nk == 0:
                b0, b1, b2, b3 = t & 255, _b8(t), _b16(t), _b24(t)
                t = (SBOX[b1] | (SBOX[b2] << 8) | (SBOX[b3] << 16) | (SBOX[b0] << 24)) & MASK
                t ^= RCON[i // nk - 1]
            elif nk > 6 and i % nk == 4:
                t = (SBOX[t & 255] | (SBOX[_b8(t)] << 8) | (SBOX[_b16(t)] << 16) | (SBOX[_b24(t)] << 24)) & MASK
            w.append((w[i - nk] ^ t) & MASK)
        return [[w[4*r], w[4*r+1], w[4*r+2], w[4*r+3]] for r in range(self.rounds + 1)]

    def encrypt_block(self, st):
        s0, s1, s2, s3 = st
        for r in range(self.rounds - 1):
            k = self.rk[r]
            a0 = s0 ^ k[0]; a1 = s1 ^ k[1]; a2 = s2 ^ k[2]; a3 = s3 ^ k[3]
            s0 = (TE0[a0 & 255] ^ TE1[_b8(a1)] ^ TE2[_b16(a2)] ^ TE3[_b24(a3)]) & MASK
            s1 = (TE0[a1 & 255] ^ TE1[_b8(a2)] ^ TE2[_b16(a3)] ^ TE3[_b24(a0)]) & MASK
            s2 = (TE0[a2 & 255] ^ TE1[_b8(a3)] ^ TE2[_b16(a0)] ^ TE3[_b24(a1)]) & MASK
            s3 = (TE0[a3 & 255] ^ TE1[_b8(a0)] ^ TE2[_b16(a1)] ^ TE3[_b24(a2)]) & MASK
        k = self.rk[self.rounds - 1]
        a0 = s0 ^ k[0]; a1 = s1 ^ k[1]; a2 = s2 ^ k[2]; a3 = s3 ^ k[3]
        kf = self.rk[self.rounds]
        return [
            (self._mixfinal(a0, a1, a2, a3) ^ kf[0]) & MASK,
            (self._mixfinal(a1, a2, a3, a0) ^ kf[1]) & MASK,
            (self._mixfinal(a2, a3, a0, a1) ^ kf[2]) & MASK,
            (self._mixfinal(a3, a0, a1, a2) ^ kf[3]) & MASK,
        ]

    @staticmethod
    def _mixfinal(i, i2, i3, i4):
        return (_b8(TE0[i & 255]) | (_b8(TE0[_b8(i2)]) << 8)
                | (_b8(TE0[_b16(i3)]) << 16) | (_b8(TE0[_b24(i4)]) << 24)) & MASK

    def _dec_rk(self):
        rk = [list(w) for w in self.rk]
        for r in range(1, self.rounds):
            for c in range(4):
                x = rk[r][c]
                rk[r][c] = (TKD0[x & 255] ^ TKD1[_b8(x)] ^ TKD2[_b16(x)] ^ TKD3[_b24(x)]) & MASK
        return rk

    def decrypt_block(self, st, drk):
        s0, s1, s2, s3 = st
        for r in range(self.rounds, 1, -1):
            k = drk[r]
            a0 = s0 ^ k[0]; a1 = s1 ^ k[1]; a2 = s2 ^ k[2]; a3 = s3 ^ k[3]
            s0 = (TD0[a0 & 255] ^ TD1[_b8(a3)] ^ TD2[_b16(a2)] ^ TD3[_b24(a1)]) & MASK
            s1 = (TD0[a1 & 255] ^ TD1[_b8(a0)] ^ TD2[_b16(a3)] ^ TD3[_b24(a2)]) & MASK
            s2 = (TD0[a2 & 255] ^ TD1[_b8(a1)] ^ TD2[_b16(a0)] ^ TD3[_b24(a3)]) & MASK
            s3 = (TD0[a3 & 255] ^ TD1[_b8(a2)] ^ TD2[_b16(a1)] ^ TD3[_b24(a0)]) & MASK
        k = drk[1]
        a0 = s0 ^ k[0]; a1 = s1 ^ k[1]; a2 = s2 ^ k[2]; a3 = s3 ^ k[3]
        s0 = (ISBOX[a0 & 255] | (ISBOX[_b8(a3)] << 8) | (ISBOX[_b16(a2)] << 16) | (ISBOX[_b24(a1)] << 24)) & MASK
        s1 = (ISBOX[a1 & 255] | (ISBOX[_b8(a0)] << 8) | (ISBOX[_b16(a3)] << 16) | (ISBOX[_b24(a2)] << 24)) & MASK
        s2 = (ISBOX[a2 & 255] | (ISBOX[_b8(a1)] << 8) | (ISBOX[_b16(a0)] << 16) | (ISBOX[_b24(a3)] << 24)) & MASK
        s3 = (ISBOX[a3 & 255] | (ISBOX[_b8(a2)] << 8) | (ISBOX[_b16(a1)] << 16) | (ISBOX[_b24(a0)] << 24)) & MASK
        k0 = drk[0]
        return [s0 ^ k0[0], s1 ^ k0[1], s2 ^ k0[2], s3 ^ k0[3]]

    def decrypt(self, data: bytes) -> bytes:
        drk = self._dec_rk()
        out = bytearray()
        for off in range(0, len(data), 16):
            out += _unpack(self.decrypt_block(_pack(data[off:off+16]), drk))
        return bytes(out)

    def encrypt(self, data: bytes) -> bytes:
        out = bytearray()
        for off in range(0, len(data), 16):
            out += _unpack(self.encrypt_block(_pack(data[off:off+16])))
        return bytes(out)


def derive_auth_token(token_hex: str) -> str:
    """mobile_auth TOKEN (hex) -> api_checkToken `auth_token` (hex)."""
    icon_key = extract_icon_key().encode("utf-8")[:16]
    decrypted = AES(icon_key).decrypt(bytes.fromhex(token_hex))
    s1 = decrypted[0:64]
    s2 = decrypted[64:80]
    enc = AES(s2[:16]).encrypt(s1)
    return enc.hex()


if __name__ == "__main__":
    import sys
    print("icon key:", extract_icon_key())
    if len(sys.argv) > 1:
        print("auth_token:", derive_auth_token(sys.argv[1]))
