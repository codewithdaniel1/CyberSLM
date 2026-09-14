from __future__ import annotations

import base64
import gzip
import json
import random
from pathlib import Path
from typing import Any
from urllib.parse import quote


def _record(
    record_id: str,
    *,
    mode: str,
    skill: str,
    prompt: str,
    answer: str,
    suggested_split: str,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "mode": mode,
        "skill": skill,
        "source": "CyberSLM original synthetic crypto-CTF draft generator v1",
        "license": "Apache-2.0",
        "contains_private_data": False,
        "approved_for_training": False,
        "review_status": "draft",
        "suggested_split": suggested_split,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ],
    }


def generate_crypto_ctf_drafts(
    output: Path,
    *,
    count: int = 60,
    seed: int = 3407,
) -> list[dict[str, Any]]:
    """Generate original, unapproved crypto-CTF SFT drafts for human review."""
    if count < 12:
        raise ValueError("count must be at least 12 to cover the complete starter taxonomy")
    if output.exists():
        raise ValueError(f"Refusing to overwrite existing draft file: {output}")

    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    for index in range(count):
        token = f"ctf_{index:03d}_{rng.randrange(1_000_000):06d}"
        split = "validation" if index % 10 == 0 else "train"
        kind = index % 12
        record_id = f"crypto-ctf-draft-{index:03d}"
        if kind == 0:
            plaintext = f"flag{{{token}}}"
            encoded = base64.b64encode(plaintext.encode()).decode()
            prompt = f"In a crypto CTF, decode this Base64 text: `{encoded}`."
            answer = (
                f"This is Base64. Decode it once to obtain `{plaintext}`. Do not treat Base64 "
                "as encryption; it is an encoding."
            )
            skill, mode = "base64", "crypto_ctf"
        elif kind == 1:
            plaintext = f"flag{{{token}}}"
            encoded = plaintext.encode().hex()
            prompt = f"In a crypto CTF, decode these hexadecimal bytes: `{encoded}`."
            answer = (
                f"Interpret each pair of hexadecimal characters as one byte. The decoded text is "
                f"`{plaintext}`. Hex is an encoding, not encryption."
            )
            skill, mode = "hex", "crypto_ctf"
        elif kind == 2:
            plaintext = f"flag{{{token}}}"
            url_encoded = quote(plaintext, safe="")
            encoded = base64.b64encode(url_encoded.encode()).decode()
            prompt = (
                "A challenge gives this layered value: "
                f"`{encoded}`. Identify and apply the decoding steps."
            )
            answer = (
                "First Base64-decode the value; the result is URL-encoded text. Then URL-decode "
                f"that text to obtain `{plaintext}`."
            )
            skill, mode = "layered-base64-url", "crypto_ctf"
        elif kind == 3:
            plaintext = f"flag{{{token}}}".encode()
            compressed = gzip.compress(plaintext, mtime=0)
            encoded = base64.b64encode(compressed).decode()
            prompt = (
                "A CTF artifact is Base64 text and is known to contain a gzip member after "
                "decoding: "
                f"`{encoded}`. What is the safe recipe?"
            )
            answer = (
                "Use the two-stage recipe: Base64-decode to bytes, then gzip-decompress those "
                f"bytes. The recovered challenge text is `{plaintext.decode()}`."
            )
            skill, mode = "base64-gzip", "crypto_ctf"
        elif kind == 4:
            value = token.replace("_", "")
            prompt = (
                f"A string `{value}` contains only letters and digits, but the CTF gives no format "
                "hint or ciphertext. Should a decoder be selected?"
            )
            answer = (
                "No recipe should be selected from this evidence alone. The alphabet is ambiguous; "
                "ask for the challenge format, encoding hint, or actual ciphertext rather than "
                "guessing Base64, hex, or a cipher."
            )
            skill, mode = "safe-abstention-ambiguous", "cryptography"
        elif kind == 5:
            digest = f"{rng.getrandbits(256):064x}"
            prompt = f"A CTF note contains this SHA-256-looking digest: `{digest}`. Decode it."
            answer = (
                "A digest is not an encoded plaintext and SHA-256 is not reversible. Identify it "
                "as a likely SHA-256 digest, then ask for challenge-specific verification data or "
                "a stated weakness; do not claim a plaintext can be decoded."
            )
            skill, mode = "hash-safe-abstention", "cryptography"
        elif kind == 6:
            prompt = (
                "A CTF provides an AES-CBC ciphertext and IV but no key, oracle, known plaintext, "
                "or implementation flaw. Choose the next action."
            )
            answer = (
                "Do not select an AES-decrypt recipe: an IV and ciphertext alone are insufficient. "
                "Ask for the key or a challenge-provided weakness, and distinguish that from a "
                "claim that AES-CBC itself is broken."
            )
            skill, mode = "aes-safe-abstention", "cryptography"
        elif kind == 7:
            prompt = (
                "A CTF includes an ASCII-armored PGP message but no private key, passphrase, or "
                "challenge hint about a flaw. What can be concluded?"
            )
            answer = (
                "Recognize PGP armor, but do not attempt decryption without a supplied private "
                "key, "
                "passphrase, or explicit solvable weakness. The correct action is safe abstention "
                "and a request for the missing challenge context."
            )
            skill, mode = "pgp-safe-abstention", "cryptography"
        elif kind == 8:
            prompt = (
                "In a toy RSA CTF, p=61, q=53, e=17, and c=2790. Recover the plaintext integer "
                "and explain why this is educational only."
            )
            answer = (
                "Compute phi(n)=(61-1)(53-1)=3120, then d=17^-1 mod 3120=2753. Compute "
                "m=c^d mod n=65. This is solvable because the factors are supplied and tiny; it "
                "does not imply practical RSA can be decrypted this way."
            )
            skill, mode = "toy-rsa", "crypto_ctf"
        elif kind == 9:
            prompt = (
                "A CTF says several samples use repeating-key XOR with one unknown key, but does "
                "not provide any ciphertext bytes. Give the analysis method without fabricating "
                "a result."
            )
            answer = (
                "Estimate candidate key lengths (for example with normalized Hamming distance), "
                "transpose bytes by key position, score single-byte XOR candidates with language "
                "statistics, and validate a candidate across all samples. No plaintext can be "
                "recovered without the ciphertext."
            )
            skill, mode = "repeating-key-xor", "crypto_ctf"
        elif kind == 10:
            payload = base64.urlsafe_b64encode(
                b'{"sub":"ctf-player","challenge":"' + token.encode() + b'"}'
            ).decode().rstrip("=")
            prompt = (
                "A CTF gives the middle segment of a JWT-like value: "
                f"`{payload}`. What can be decoded, and what must not be trusted?"
            )
            answer = (
                "Base64url-decode the segment to inspect the JSON claims. They are readable but "
                "untrusted until the complete token's signature is verified with the expected "
                "algorithm and key. Do not treat decoding as authentication."
            )
            skill, mode = "jwt-recognition", "crypto_ctf"
        else:
            prompt = (
                "A lab challenge encrypts two different plaintexts with AES-GCM under the same key "
                "and repeats a nonce. Explain the cryptographic mistake and the production lesson "
                "without claiming recovery of either plaintext."
            )
            answer = (
                "Nonce reuse with AES-GCM under one key is a serious misuse that can compromise "
                "confidentiality and authentication guarantees. The production fix is a unique "
                "nonce per encryption under each key, managed by a proven counter or a correctly "
                "sized random-nonce strategy. Recovery cannot be claimed without the supplied data."
            )
            skill, mode = "aead-nonce-reuse", "crypto_ctf"
        records.append(
            _record(
                record_id,
                mode=mode,
                skill=skill,
                prompt=prompt,
                answer=answer,
                suggested_split=split,
            )
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return records
