"""
Encrypted OAuth2 token persistence using Fernet symmetric encryption.

Tokens are serialised to JSON, encrypted, and written to a local file.
The Fernet key is read from the FERNET_KEY environment variable — it is
never embedded in source code.

Requirements: 8.1, 8.4
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings

logger = logging.getLogger(__name__)

# Default location for the encrypted token file — relative to CWD
_DEFAULT_TOKEN_PATH = Path("google_token.enc")


class TokenStore:
    """Encrypts and persists OAuth2 tokens to a local file.

    All data written to disk is opaque ciphertext — never plain-text JSON.
    """

    def __init__(self, token_path: Path | None = None) -> None:
        self._path: Path = token_path or _DEFAULT_TOKEN_PATH
        self._fernet = Fernet(settings.FERNET_KEY.encode())

    # ── Public interface ──────────────────────────────────────────────────────

    def save(self, token_dict: Dict[str, Any]) -> None:
        """Encrypt *token_dict* and write to the token file.

        Args:
            token_dict: Arbitrary mapping produced by the Google OAuth2 flow.
        """
        plaintext = json.dumps(token_dict).encode("utf-8")
        ciphertext = self._fernet.encrypt(plaintext)
        self._path.write_bytes(ciphertext)
        logger.debug("OAuth2 tokens encrypted and persisted to %s", self._path)

    def load(self) -> Dict[str, Any]:
        """Read, decrypt, and return the stored token dictionary.

        Returns:
            The decrypted token mapping.

        Raises:
            FileNotFoundError: The token file does not exist (user not authenticated).
            InvalidToken: The file contents cannot be decrypted (corrupted or wrong key).
        """
        ciphertext = self._path.read_bytes()
        plaintext = self._fernet.decrypt(ciphertext)
        return json.loads(plaintext.decode("utf-8"))

    def exists(self) -> bool:
        """Return True if a token file is present on disk."""
        return self._path.exists()

    def delete(self) -> None:
        """Remove the token file (used during re-authentication flows)."""
        if self._path.exists():
            self._path.unlink()
            logger.debug("Token file %s deleted", self._path)


# Module-level singleton for use outside of dependency injection
token_store = TokenStore()
