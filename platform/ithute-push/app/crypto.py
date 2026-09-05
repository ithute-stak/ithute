import hashlib

from cryptography.fernet import Fernet, InvalidToken


class EndpointCipher:
    def __init__(self, key: str):
        self.fernet = Fernet(key.encode("ascii"))

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("push endpoint encryption key mismatch") from exc


def endpoint_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
