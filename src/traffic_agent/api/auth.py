"""
API Authentication — Simple API key authentication middleware.

Provides API key validation for securing the traffic control API.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class APIKey:
    """API key with metadata."""

    key_id: str
    key_hash: str
    name: str
    created_at: float
    expires_at: float | None = None
    rate_limit: int = 100  # requests per minute
    scopes: list[str] = field(default_factory=lambda: ["read", "write"])

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


class APIKeyManager:
    """Manages API keys."""

    def __init__(self):
        self._keys: dict[str, APIKey] = {}
        self._request_counts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def create_key(
        self,
        name: str,
        scopes: list[str] | None = None,
        rate_limit: int = 100,
        expires_in: float | None = None,
    ) -> tuple[str, APIKey]:
        """
        Create a new API key.

        Returns:
            Tuple of (raw_key, api_key_object)
        """
        # Generate random key
        raw_key = os.urandom(32).hex()
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = hashlib.sha256(raw_key.encode()).hexdigest()[:8]

        expires_at = None
        if expires_in is not None:
            expires_at = time.time() + expires_in

        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            created_at=time.time(),
            expires_at=expires_at,
            rate_limit=rate_limit,
            scopes=scopes or ["read", "write"],
        )

        self._keys[key_id] = api_key
        return raw_key, api_key

    def validate_key(self, raw_key: str) -> APIKey | None:
        """Validate an API key and return the key object if valid."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        for key_id, api_key in self._keys.items():
            if hmac.compare_digest(api_key.key_hash, key_hash):
                if api_key.is_expired():
                    return None
                return api_key

        return None

    def check_rate_limit(self, key_id: str) -> bool:
        """Check if request is within rate limit."""
        with self._lock:
            if key_id not in self._keys:
                return False

            api_key = self._keys[key_id]
            now = time.time()

            # Initialize request history
            if key_id not in self._request_counts:
                self._request_counts[key_id] = []

            # Clean old requests (older than 1 minute)
            self._request_counts[key_id] = [
                t for t in self._request_counts[key_id]
                if now - t < 60
            ]

            # Check limit
            if len(self._request_counts[key_id]) >= api_key.rate_limit:
                return False

            # Record request
            self._request_counts[key_id].append(now)
            return True

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        if key_id in self._keys:
            del self._keys[key_id]
            self._request_counts.pop(key_id, None)
            return True
        return False

    def list_keys(self) -> list[dict[str, Any]]:
        """List all API keys (without sensitive data)."""
        return [
            {
                "key_id": key.key_id,
                "name": key.name,
                "created_at": key.created_at,
                "expires_at": key.expires_at,
                "rate_limit": key.rate_limit,
                "scopes": key.scopes,
                "is_expired": key.is_expired(),
            }
            for key in self._keys.values()
        ]


# Global API key manager
_api_key_manager: APIKeyManager | None = None


def get_api_key_manager() -> APIKeyManager:
    """Get or create the global API key manager."""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager


def create_default_admin_key() -> str:
    """Create a default admin API key (for development)."""
    manager = get_api_key_manager()
    raw_key, _ = manager.create_key(
        name="admin",
        scopes=["read", "write", "admin"],
        rate_limit=1000,
    )
    return raw_key
