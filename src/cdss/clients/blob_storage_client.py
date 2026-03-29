"""Azure Blob Storage client wrapper for treatment protocol document management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AzureServiceError
from cdss.core.logging import get_logger

logger = get_logger(__name__)

PROTOCOLS_CONTAINER = "treatment-protocols"


class BlobStorageClient:
    """Manage treatment protocol documents in Azure Blob Storage.

    Provides upload, download, listing, and deletion of treatment
    protocol documents stored as blobs in a dedicated container.
    Supports both connection string and Entra ID authentication.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

        try:
            credential: str | TokenCredential
            auth_mode = "connection_string"

            if self._settings.azure_blob_use_entra_id or not self._settings.azure_blob_connection_string:
                credential = DefaultAzureCredential()
                auth_mode = "entra_id"

                account_url = self._settings.azure_blob_endpoint
                if not account_url:
                    account_name = self._extract_account_name_from_connection_string(
                        self._settings.azure_blob_connection_string
                    )
                    if account_name:
                        account_url = f"https://{account_name}.blob.core.windows.net"

                if not account_url:
                    raise AzureServiceError(
                        "Blob Storage endpoint required for Entra ID auth. "
                        "Set CDSS_AZURE_BLOB_ENDPOINT or CDSS_AZURE_BLOB_CONNECTION_STRING."
                    )

                self._service_client = BlobServiceClient(
                    account_url=account_url,
                    credential=credential,
                )
            else:
                self._service_client = BlobServiceClient.from_connection_string(
                    self._settings.azure_blob_connection_string
                )

            self._container_name = getattr(
                self._settings,
                "blob_storage_container_name",
                self._settings.azure_blob_protocols_container or PROTOCOLS_CONTAINER,
            )
            self._container_client = self._service_client.get_container_client(self._container_name)

            logger.info(
                "BlobStorageClient initialized",
                account=self._service_client.account_name,
                container=self._container_name,
                auth_mode=auth_mode,
            )

        except AzureServiceError:
            raise
        except Exception as exc:
            logger.error(
                "Failed to initialize BlobStorageClient",
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to initialize Blob Storage client: {exc}") from exc

    def _extract_account_name_from_connection_string(self, conn_str: str) -> str | None:
        if not conn_str:
            return None
        for part in conn_str.split(";"):
            if part.startswith("AccountName="):
                return part.split("=", 1)[1]
        return None

    async def upload_protocol(
        self,
        blob_name: str,
        content: bytes,
        metadata: dict | None = None,
    ) -> str:
        """Upload a treatment protocol document to blob storage.

        Args:
            blob_name: Name/path for the blob (e.g., "cardiology/hypertension-protocol.pdf").
            content: Raw bytes of the document to upload.
            metadata: Optional metadata dict to attach to the blob.

        Returns:
            The URL of the uploaded blob.

        Raises:
            AzureServiceError: If the upload fails.
        """
        try:
            blob_client = self._container_client.get_blob_client(blob_name)

            # Determine content type from blob name
            content_type = self._infer_content_type(blob_name)

            # Enrich metadata with upload timestamp
            upload_metadata = metadata.copy() if metadata else {}
            upload_metadata["uploaded_at"] = datetime.now(timezone.utc).isoformat()
            upload_metadata["size_bytes"] = str(len(content))

            blob_client.upload_blob(
                data=content,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
                metadata=upload_metadata,
            )

            blob_url = blob_client.url

            logger.info(
                "Protocol uploaded",
                blob_name=blob_name,
                size_bytes=len(content),
                content_type=content_type,
                url=blob_url,
            )

            return blob_url

        except Exception as exc:
            logger.error(
                "Failed to upload protocol",
                blob_name=blob_name,
                size_bytes=len(content),
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to upload protocol '{blob_name}': {exc}") from exc

    async def download_protocol(self, blob_name: str) -> bytes:
        """Download a treatment protocol document from blob storage.

        Args:
            blob_name: Name/path of the blob to download.

        Returns:
            Raw bytes of the document.

        Raises:
            AzureServiceError: If the download fails or the blob does not exist.
        """
        try:
            blob_client = self._container_client.get_blob_client(blob_name)
            download_stream = blob_client.download_blob()
            content = download_stream.readall()

            logger.info(
                "Protocol downloaded",
                blob_name=blob_name,
                size_bytes=len(content),
            )

            return content

        except Exception as exc:
            logger.error(
                "Failed to download protocol",
                blob_name=blob_name,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to download protocol '{blob_name}': {exc}") from exc

    async def list_protocols(self, prefix: str | None = None) -> list[dict]:
        """List all protocol blobs with their metadata.

        Args:
            prefix: Optional prefix to filter blobs by path (e.g., "cardiology/").

        Returns:
            List of blob info dicts with keys: name, size, content_type,
            last_modified, metadata.

        Raises:
            AzureServiceError: If the listing fails.
        """
        try:
            kwargs: dict[str, Any] = {"include": ["metadata"]}
            if prefix is not None:
                kwargs["name_starts_with"] = prefix

            blobs: list[dict] = []
            for blob_properties in self._container_client.list_blobs(**kwargs):
                blob_info = {
                    "name": blob_properties.name,
                    "size": blob_properties.size,
                    "content_type": (
                        blob_properties.content_settings.content_type
                        if blob_properties.content_settings
                        else "application/octet-stream"
                    ),
                    "last_modified": (
                        blob_properties.last_modified.isoformat() if blob_properties.last_modified else None
                    ),
                    "metadata": blob_properties.metadata or {},
                }
                blobs.append(blob_info)

            logger.info(
                "Protocols listed",
                prefix=prefix,
                count=len(blobs),
            )

            return blobs

        except Exception as exc:
            logger.error(
                "Failed to list protocols",
                prefix=prefix,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to list protocols with prefix '{prefix}': {exc}") from exc

    async def delete_protocol(self, blob_name: str) -> None:
        """Delete a protocol document from blob storage.

        Args:
            blob_name: Name/path of the blob to delete.

        Raises:
            AzureServiceError: If the deletion fails or the blob does not exist.
        """
        try:
            blob_client = self._container_client.get_blob_client(blob_name)
            blob_client.delete_blob()

            logger.info(
                "Protocol deleted",
                blob_name=blob_name,
            )

        except Exception as exc:
            logger.error(
                "Failed to delete protocol",
                blob_name=blob_name,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to delete protocol '{blob_name}': {exc}") from exc

    @staticmethod
    def _infer_content_type(blob_name: str) -> str:
        """Infer the MIME content type from the blob name extension.

        Args:
            blob_name: Name/path of the blob.

        Returns:
            MIME type string.
        """
        extension_map = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".html": "text/html",
            ".htm": "text/html",
            ".json": "application/json",
            ".xml": "application/xml",
            ".csv": "text/csv",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }

        lower_name = blob_name.lower()
        for ext, content_type in extension_map.items():
            if lower_name.endswith(ext):
                return content_type

        return "application/octet-stream"
