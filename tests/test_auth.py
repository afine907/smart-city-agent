"""
Tests for API Authentication module.
"""

import time
import pytest

from traffic_agent.api.auth import (
    APIKey,
    APIKeyManager,
    create_default_admin_key,
    get_api_key_manager,
)


class TestAPIKey:
    """Test APIKey data class."""

    def test_not_expired(self):
        key = APIKey(
            key_id="test",
            key_hash="hash",
            name="test",
            created_at=time.time(),
        )
        assert not key.is_expired()

    def test_expired(self):
        key = APIKey(
            key_id="test",
            key_hash="hash",
            name="test",
            created_at=time.time(),
            expires_at=time.time() - 1,
        )
        assert key.is_expired()

    def test_has_scope(self):
        key = APIKey(
            key_id="test",
            key_hash="hash",
            name="test",
            created_at=time.time(),
            scopes=["read", "write"],
        )
        assert key.has_scope("read")
        assert key.has_scope("write")
        assert not key.has_scope("admin")


class TestAPIKeyManager:
    """Test APIKeyManager."""

    def test_create_and_validate(self):
        manager = APIKeyManager()
        raw_key, api_key = manager.create_key(name="test")

        # Should validate correctly
        validated = manager.validate_key(raw_key)
        assert validated is not None
        assert validated.key_id == api_key.key_id

    def test_validate_invalid_key(self):
        manager = APIKeyManager()
        manager.create_key(name="test")

        # Invalid key should return None
        assert manager.validate_key("invalid_key") is None

    def test_validate_expired_key(self):
        manager = APIKeyManager()
        raw_key, api_key = manager.create_key(
            name="test",
            expires_in=-1,  # Already expired
        )

        assert manager.validate_key(raw_key) is None

    def test_revoke_key(self):
        manager = APIKeyManager()
        raw_key, api_key = manager.create_key(name="test")

        assert manager.revoke_key(api_key.key_id)
        assert manager.validate_key(raw_key) is None

    def test_revoke_nonexistent(self):
        manager = APIKeyManager()
        assert not manager.revoke_key("nonexistent")

    def test_rate_limit(self):
        manager = APIKeyManager()
        raw_key, api_key = manager.create_key(name="test", rate_limit=3)

        # Should allow up to rate_limit requests
        assert manager.check_rate_limit(api_key.key_id)
        assert manager.check_rate_limit(api_key.key_id)
        assert manager.check_rate_limit(api_key.key_id)

        # Should deny after limit
        assert not manager.check_rate_limit(api_key.key_id)

    def test_list_keys(self):
        manager = APIKeyManager()
        manager.create_key(name="key1")
        manager.create_key(name="key2")

        keys = manager.list_keys()
        assert len(keys) == 2
        assert all("key_id" in k for k in keys)

    def test_scopes(self):
        manager = APIKeyManager()
        raw_key, api_key = manager.create_key(
            name="test",
            scopes=["read"],
        )

        assert api_key.has_scope("read")
        assert not api_key.has_scope("write")


class TestGlobalManager:
    """Test global API key manager."""

    @pytest.fixture(autouse=True)
    def reset_global_manager(self):
        """Reset global manager before each test."""
        import traffic_agent.api.auth as auth_module
        auth_module._api_key_manager = None
        yield
        auth_module._api_key_manager = None

    def test_get_manager(self):
        manager = get_api_key_manager()
        assert isinstance(manager, APIKeyManager)

    def test_create_admin_key(self):
        key = create_default_admin_key()
        assert isinstance(key, str)
        assert len(key) > 0
