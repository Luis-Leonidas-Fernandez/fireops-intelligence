from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()

# Static precomputed dummy Argon2id hash with identical cost parameters (m=65536, t=3, p=4)
# Used to enforce cryptographic cost parity on nonexistent/passwordless accounts without CPU amplification.
DUMMY_ARGON2_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$Om5wv0jWIUUAP2uogbL5HA$nmj5hoRVJLXitOxjcyM+u0KHl5S1a6Sp8AT0jWoBQL8"
)


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return _password_hash.verify(password, stored_hash)
