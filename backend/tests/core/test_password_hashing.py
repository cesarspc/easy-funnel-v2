"""Unit tests for Argon2id password hashing (Requirement 7.6)."""

from __future__ import annotations

from app.core.password_hashing import hash_password, verify_password


class TestHashPassword:
    def test_hash_is_never_plaintext(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")

        assert "correct-horse-battery-staple" not in hashed

    def test_hash_uses_argon2id(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")

        assert hashed.startswith("$argon2id$")

    def test_hashing_the_same_password_twice_yields_different_hashes(self) -> None:
        # Proves a unique salt is used per hash, not a fixed/shared salt.
        first = hash_password("same-password")
        second = hash_password("same-password")

        assert first != second


class TestVerifyPassword:
    def test_correct_password_verifies(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")

        assert verify_password(hashed, "correct-horse-battery-staple") is True

    def test_incorrect_password_does_not_verify(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")

        assert verify_password(hashed, "wrong-password") is False

    def test_malformed_hash_does_not_verify_and_does_not_raise(self) -> None:
        assert verify_password("not-a-real-hash", "any-password") is False
