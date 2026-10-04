from datetime import UTC, datetime, timedelta

import pytest

from app.modules.auth.validations.passwords import hash_password, verify_password
from app.modules.auth.validations.tokens import (
    create_access_token,
    validate_access_token,
)
from app.shared.errors.authentication_error import AuthenticationError

TEST_SECRET = "testing-secret-with-more-than-thirty-two-bytes"


def test_password_hash_verification() -> None:
    stored = hash_password("ClaveSegura123")
    assert stored != "ClaveSegura123"
    assert verify_password("ClaveSegura123", stored)
    assert not verify_password("ClaveIncorrecta1", stored)


def test_valid_access_token() -> None:
    token = create_access_token(42, TEST_SECRET)
    assert validate_access_token(token, TEST_SECRET) == 42


def test_tampered_access_token_is_rejected() -> None:
    token = create_access_token(42, TEST_SECRET)
    with pytest.raises(AuthenticationError) as error:
        validate_access_token(token + "tampered", TEST_SECRET)
    assert error.value.code == "INVALID_TOKEN"


def test_expired_access_token_is_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    token = create_access_token(42, TEST_SECRET, now=past)
    with pytest.raises(AuthenticationError) as error:
        validate_access_token(token, TEST_SECRET)
    assert error.value.code == "INVALID_TOKEN"
