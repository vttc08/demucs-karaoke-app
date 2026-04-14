import base64
import json
import os
import random
import string
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import requests
from Crypto.Cipher import AES

# NetEase weapi constants (same values used in many implementations)
NONCE = "0CoJUm6Qyw8W8jud"
IV = "0102030405060708"
PUBKEY = "010001"
MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629"
    "ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424"
    "d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def _pkcs7_pad(data: bytes) -> bytes:
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len]) * pad_len

def _aes_cbc_base64(plaintext: str, key: str) -> str:
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, IV.encode("utf-8"))
    padded = _pkcs7_pad(plaintext.encode("utf-8"))
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted).decode("utf-8")

def _rsa_enc_sec_key(secret_key: str) -> str:
    # reverse secret key, hex-encode, modpow with pubkey & modulus
    rev = secret_key[::-1]
    a = int(rev.encode("utf-8").hex(), 16)
    b = int(PUBKEY, 16)
    c = int(MODULUS, 16)
    x = pow(a, b, c)
    return format(x, "x").zfill(256)

def _random_secret_key(n=16) -> str:
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))

def weapi_encrypt(payload: Dict[str, Any]) -> Dict[str, str]:
    text = json.dumps(payload, separators=(",", ":"))
    sec = _random_secret_key(16)
    params = _aes_cbc_base64(_aes_cbc_base64(text, NONCE), sec)
    encSecKey = _rsa_enc_sec_key(sec)
    return {"params": params, "encSecKey": encSecKey}

@dataclass
class SongCandidate:
    id: int
    name: str
    duration_ms: int
    album: str
    artists: List[str]

def netease_search(query: str, limit: int = 20, session: Optional[requests.Session] = None) -> List[SongCandidate]:
    """
    Calls https://music.163.com/weapi/search/get (type=1 => songs)
    Returns candidates including NetEase song id.
    """
    s = session or requests.Session()
    url = "https://music.163.com/weapi/search/get"
    payload = {
        "csrf_token": "",
        "s": query,
        "offset": 0,
        "type": 1,
        "limit": limit,
    }
    data = weapi_encrypt(payload)

    r = s.post(
        url,
        data=data,
        headers={
            "Referer": "https://music.163.com",
            "User-Agent": USER_AGENT,
        },
        timeout=15,
    )
    r.raise_for_status()
    j = r.json()

    songs = (j.get("result") or {}).get("songs") or []
    out: List[SongCandidate] = []
    for it in songs:
        out.append(
            SongCandidate(
                id=int(it["id"]),
                name=it.get("name") or "",
                duration_ms=int(it.get("duration") or 0),
                album=(it.get("album") or {}).get("name") or "",
                artists=[a.get("name") or "" for a in (it.get("artists") or [])],
            )
        )
    return out

if __name__ == "__main__":
    query = "大约在冬季"
    candidates = netease_search(query)
    for c in candidates:
        print(f"ID: {c.id}, Name: {c.name}, Artists: {', '.join(c.artists)}, Album: {c.album}, Duration: {c.duration_ms}ms")