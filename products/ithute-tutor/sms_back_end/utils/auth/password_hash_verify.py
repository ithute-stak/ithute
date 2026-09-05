from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

def hash_password(password: str) -> str:
    password_safe = password[:72]   # truncate BEFORE hashing
    return pwd_context.hash(password_safe)

def verify_password(plain: str, hashed: str) -> bool:
    plain_safe = plain[:72]
    return pwd_context.verify(plain_safe, hashed)