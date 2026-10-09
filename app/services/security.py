"""Hash de senha com scrypt (biblioteca padrão): nunca se guarda a senha em texto."""

import hashlib
import hmac
import os


def hash_password(password: str) -> str:
    """Gera `salt$hash` (hex) com salt aleatório; só verificável com `verify_password`."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Confere a senha contra o `salt$hash` guardado, em tempo constante."""
    salt_hex, digest_hex = stored.split("$")
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
