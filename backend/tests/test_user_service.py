"""Unit tests for the DB-independent pieces of user_service.py: password
hashing and JWT issuance/verification. The DB-touching functions
(create_user, authenticate_user, get_user_by_id) are exercised at the
route level instead (tests/test_auth_routes.py), matching this repo's
existing convention of mocking at the service-function boundary rather
than running against a real database (see test_main.py's tenant-
ownership tests for the same pattern).
"""

import pytest

from app.core.config import settings
from app.core.exceptions import AuthConfigurationError
from app.services.user_service import (
    _hash_password,
    _verify_password,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:
    def test_correct_password_verifies(self):
        password_hash = _hash_password("correct-horse-battery-staple")
        assert _verify_password("correct-horse-battery-staple", password_hash) is True

    def test_wrong_password_does_not_verify(self):
        password_hash = _hash_password("correct-horse-battery-staple")
        assert _verify_password("wrong-password", password_hash) is False

    def test_same_password_hashes_differently_each_time(self):
        # bcrypt salts per-call — two hashes of the same password must
        # never be equal, or the salt isn't doing its job.
        first = _hash_password("same-password")
        second = _hash_password("same-password")
        assert first != second
        assert _verify_password("same-password", first) is True
        assert _verify_password("same-password", second) is True


class TestJWT:
    @pytest.fixture(autouse=True)
    def _jwt_secret(self, monkeypatch):
        monkeypatch.setattr(settings, "jwt_secret_key", "test-secret-key")
        monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
        monkeypatch.setattr(settings, "jwt_expiry_minutes", 1440)

    def test_round_trip(self):
        token = create_access_token(user_id=42, email="a@example.com")
        assert decode_access_token(token) == 42

    def test_decode_with_wrong_secret_returns_none(self, monkeypatch):
        token = create_access_token(user_id=42, email="a@example.com")
        monkeypatch.setattr(settings, "jwt_secret_key", "a-different-secret")
        assert decode_access_token(token) is None

    def test_decode_garbage_token_returns_none(self):
        assert decode_access_token("not-a-real-jwt") is None

    def test_decode_expired_token_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "jwt_expiry_minutes", -1)  # already expired
        token = create_access_token(user_id=42, email="a@example.com")
        assert decode_access_token(token) is None

    def test_create_without_secret_raises_auth_configuration_error(self, monkeypatch):
        monkeypatch.setattr(settings, "jwt_secret_key", "")
        with pytest.raises(AuthConfigurationError):
            create_access_token(user_id=42, email="a@example.com")

    def test_decode_without_secret_returns_none_not_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "jwt_secret_key", "")
        assert decode_access_token("anything") is None
