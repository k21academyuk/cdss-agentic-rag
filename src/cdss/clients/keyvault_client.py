"""Azure Key Vault client wrapper for secret management."""

from __future__ import annotations

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AzureServiceError
from cdss.core.logging import get_logger

logger = get_logger(__name__)


class KeyVaultClient:
    """Manage secrets via Azure Key Vault.

    Provides secure access to application secrets such as API keys,
    connection strings, and credentials using Azure Key Vault with
    DefaultAzureCredential for authentication.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize Azure Key Vault client with DefaultAzureCredential.

        Args:
            settings: Application settings. If None, loads from environment.
        """
        self._settings = settings or get_settings()

        try:
            self._credential = DefaultAzureCredential()
            self._client = SecretClient(
                vault_url=self._settings.keyvault_url,
                credential=self._credential,
            )

            logger.info(
                "KeyVaultClient initialized",
                vault_url=self._settings.keyvault_url,
            )

        except Exception as exc:
            logger.error(
                "Failed to initialize KeyVaultClient",
                error=str(exc),
            )
            raise AzureServiceError(
                f"Failed to initialize Key Vault client: {exc}"
            ) from exc

    async def get_secret(self, name: str) -> str:
        """Retrieve a secret value by name.

        Args:
            name: Name of the secret to retrieve.

        Returns:
            The secret value as a string.

        Raises:
            AzureServiceError: If the secret cannot be retrieved or does not exist.
        """
        try:
            secret = self._client.get_secret(name)

            if secret.value is None:
                raise AzureServiceError(
                    f"Secret '{name}' exists but has no value"
                )

            logger.debug("Secret retrieved", secret_name=name)
            return secret.value

        except AzureServiceError:
            raise
        except Exception as exc:
            logger.error(
                "Failed to get secret",
                secret_name=name,
                error=str(exc),
            )
            raise AzureServiceError(
                f"Failed to retrieve secret '{name}': {exc}"
            ) from exc

    async def set_secret(self, name: str, value: str) -> None:
        """Create or update a secret.

        Args:
            name: Name of the secret to set.
            value: Secret value to store.

        Raises:
            AzureServiceError: If the secret cannot be set.
        """
        try:
            self._client.set_secret(name, value)

            logger.info("Secret set", secret_name=name)

        except Exception as exc:
            logger.error(
                "Failed to set secret",
                secret_name=name,
                error=str(exc),
            )
            raise AzureServiceError(
                f"Failed to set secret '{name}': {exc}"
            ) from exc

    async def delete_secret(self, name: str) -> None:
        """Begin deletion of a secret.

        This starts a soft-delete operation. The secret enters a deleted
        state and can be recovered within the retention period.

        Args:
            name: Name of the secret to delete.

        Raises:
            AzureServiceError: If the deletion fails.
        """
        try:
            poller = self._client.begin_delete_secret(name)
            poller.wait()

            logger.info("Secret deleted", secret_name=name)

        except Exception as exc:
            logger.error(
                "Failed to delete secret",
                secret_name=name,
                error=str(exc),
            )
            raise AzureServiceError(
                f"Failed to delete secret '{name}': {exc}"
            ) from exc

    async def list_secrets(self) -> list[str]:
        """List all secret names in the vault.

        Returns only the names, not the secret values, for security.

        Returns:
            List of secret name strings.

        Raises:
            AzureServiceError: If the listing fails.
        """
        try:
            secret_names: list[str] = []
            for secret_properties in self._client.list_properties_of_secrets():
                if secret_properties.name:
                    secret_names.append(secret_properties.name)

            logger.info("Secrets listed", count=len(secret_names))
            return secret_names

        except Exception as exc:
            logger.error(
                "Failed to list secrets",
                error=str(exc),
            )
            raise AzureServiceError(
                f"Failed to list secrets: {exc}"
            ) from exc
