"""CredentialStore — secure API key management.

Keys are stored AES-encrypted in ~/.genus/credentials.enc.
The encryption key is read from the environment variable
GENUS_CREDENTIAL_KEY, or generated on first use and saved to
~/.genus/.credential_key.
"""

import getpass
import json
import logging
import os
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet

    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    _CRYPTOGRAPHY_AVAILABLE = False
    logger.warning(
        "cryptography package not available. Credentials will be stored "
        "unencrypted. Install cryptography>=41.0.0 for secure storage."
    )

_DEFAULT_STORAGE_PATH = Path.home() / ".genus" / "credentials.enc"
_DEFAULT_KEY_PATH = Path.home() / ".genus" / ".credential_key"


class CredentialStore:
    """Secure API key management.

    Keys are AES-encrypted and stored in ~/.genus/credentials.enc.
    The encryption key comes from the environment variable
    GENUS_CREDENTIAL_KEY, or is generated on first use and saved to
    ~/.genus/.credential_key.

    Never in source code, never in Git.

    Args:
        storage_path: Path to the encrypted credentials file.
                      Default: ~/.genus/credentials.enc
        key_path: Path to the encryption key file.
                  Default: ~/.genus/.credential_key
        prompt_fn: Function that prompts the user for a key.
                   Default: getpass.getpass (interactive).
                   In tests: lambda name: "test-key"
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        key_path: Optional[Path] = None,
        prompt_fn: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._storage_path = Path(storage_path) if storage_path else _DEFAULT_STORAGE_PATH
        self._key_path = Path(key_path) if key_path else _DEFAULT_KEY_PATH
        self._prompt_fn = prompt_fn or (lambda name: getpass.getpass(f"API key for {name}: "))
        self._fernet: Optional[object] = None  # Fernet instance or None

        if _CRYPTOGRAPHY_AVAILABLE:
            self._fernet = self._load_or_create_fernet()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, provider: str) -> Optional[str]:
        """Loads the API key for a provider. Returns None if not found."""
        data = self._load_all()
        return data.get(provider)

    def get_or_ask(self, provider: str) -> str:
        """Loads the key or prompts the user interactively.

        Raises:
            LLMCredentialMissingError: when no key was entered.
        """
        from genus.llm.exceptions import LLMCredentialMissingError

        key = self.get(provider)
        if key:
            return key

        entered = self._prompt_fn(provider)
        if not entered or not entered.strip():
            raise LLMCredentialMissingError(
                f"No API key entered for provider '{provider}'."
            )
        self.set(provider, entered.strip())
        return entered.strip()

    def set(self, provider: str, key: str) -> None:
        """Stores an API key encrypted."""
        data = self._load_all()
        data[provider] = key
        self._save_all(data)

    def delete(self, provider: str) -> None:
        """Deletes a provider's key."""
        data = self._load_all()
        data.pop(provider, None)
        self._save_all(data)

    def list_providers(self) -> List[str]:
        """Returns all stored provider names."""
        return list(self._load_all().keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_create_fernet(self) -> object:
        """Loads or creates the Fernet encryption key."""
        env_key = os.environ.get("GENUS_CREDENTIAL_KEY")
        if env_key:
            return Fernet(env_key.encode() if isinstance(env_key, str) else env_key)

        if self._key_path.exists():
            raw = self._key_path.read_bytes().strip()
            return Fernet(raw)

        # Generate a new key
        new_key = Fernet.generate_key()
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.write_bytes(new_key)
        self._key_path.chmod(0o600)
        logger.info("New credential key generated at %s", self._key_path)
        return Fernet(new_key)

    def _load_all(self) -> dict:
        """Loads all credentials from the storage file."""
        if not self._storage_path.exists():
            return {}

        raw = self._storage_path.read_bytes()

        if self._fernet is not None:
            try:
                decrypted = self._fernet.decrypt(raw)
                return json.loads(decrypted.decode("utf-8"))
            except Exception as exc:
                logger.error("Failed to decrypt credentials: %s", exc)
                return {}
        else:
            # Fallback: unencrypted
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception as exc:
                logger.error("Failed to load credentials: %s", exc)
                return {}

    def _save_all(self, data: dict) -> None:
        """Saves all credentials to the storage file."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data).encode("utf-8")

        if self._fernet is not None:
            encrypted = self._fernet.encrypt(payload)
            self._storage_path.write_bytes(encrypted)
        else:
            # Fallback: unencrypted
            self._storage_path.write_bytes(payload)

        self._storage_path.chmod(0o600)
