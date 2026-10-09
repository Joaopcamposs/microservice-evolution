"""Hash de senha com scrypt (biblioteca padrão): nunca se guarda a senha em texto."""

import hashlib
import hmac
import os


class PasswordHasher:
    """Gera e confere hashes de senha (scrypt com salt aleatório); sem estado."""

    SALT_BYTES = 16
    N = 2**14
    R = 8
    P = 1

    @staticmethod
    def hash(password: str) -> str:
        """Gera `salt$hash` (hex) com salt aleatório; só verificável com `verify`."""
        salt = os.urandom(PasswordHasher.SALT_BYTES)
        return f"{salt.hex()}${PasswordHasher._scrypt(password, salt).hex()}"

    @staticmethod
    def verify(password: str, stored: str) -> bool:
        """Confere a senha contra o `salt$hash` guardado, em tempo constante."""
        salt_hex, digest_hex = stored.split("$")
        digest = PasswordHasher._scrypt(password, bytes.fromhex(salt_hex))
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))

    @staticmethod
    def _scrypt(password: str, salt: bytes) -> bytes:
        """Deriva a chave scrypt da senha com o salt dado."""
        return hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=PasswordHasher.N,
            r=PasswordHasher.R,
            p=PasswordHasher.P,
        )
