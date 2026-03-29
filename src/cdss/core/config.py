"""Settings management for the Clinical Decision Support System.

Uses pydantic-settings to load configuration from environment variables
with the CDSS_ prefix. All settings can be overridden via a .env file.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the CDSS application.

    All environment variables are prefixed with CDSS_ and loaded
    from a .env file when present.
    """

    model_config = SettingsConfigDict(
        env_prefix="CDSS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Azure OpenAI ──────────────────────────────────────────────────────────
    azure_openai_endpoint: str = Field(
        default="",
        description="Azure OpenAI service endpoint URL.",
    )
    azure_openai_api_key: str = Field(
        default="",
        description="Azure OpenAI API key.",
    )
    azure_openai_deployment_name: str = Field(
        default="gpt-4o",
        description="Primary GPT-4o deployment name for clinical reasoning.",
    )
    azure_openai_mini_deployment_name: str = Field(
        default="gpt-4o-mini",
        description="GPT-4o-mini deployment name for lighter tasks (classification, extraction).",
    )
    azure_openai_embedding_deployment: str = Field(
        default="text-embedding-3-large",
        description="Embedding model deployment name.",
    )
    azure_openai_api_version: str = Field(
        default="2024-12-01-preview",
        description="Azure OpenAI API version.",
    )

    # ── Azure AI Search ───────────────────────────────────────────────────────
    azure_search_endpoint: str = Field(
        default="",
        description="Azure AI Search service endpoint URL.",
    )
    azure_search_api_key: str = Field(
        default="",
        description="Azure AI Search admin or query API key.",
    )
    azure_search_patient_records_index: str = Field(
        default="patient-records",
        description="Index name for patient records.",
    )
    azure_search_treatment_protocols_index: str = Field(
        default="treatment-protocols",
        description="Index name for treatment protocols and clinical guidelines.",
    )
    azure_search_medical_literature_index: str = Field(
        default="medical-literature-cache",
        description="Index name for medical literature (PubMed articles).",
    )
    azure_search_patient_records_semantic_config: str = Field(
        default="patient-records-semantic",
        description="Semantic configuration for patient records index.",
    )
    azure_search_treatment_protocols_semantic_config: str = Field(
        default="protocols-semantic",
        description="Semantic configuration for treatment protocols index.",
    )
    azure_search_medical_literature_semantic_config: str = Field(
        default="literature-semantic",
        description="Semantic configuration for medical literature index.",
    )

    # ── Azure Cosmos DB ───────────────────────────────────────────────────────
    azure_cosmos_endpoint: str = Field(
        default="",
        description="Azure Cosmos DB endpoint URL.",
    )
    azure_cosmos_key: str = Field(
        default="",
        description="Azure Cosmos DB primary key.",
    )
    azure_cosmos_use_entra_id: bool = Field(
        default=False,
        description="Use Azure Entra ID (DefaultAzureCredential) for Cosmos DB auth instead of account key.",
    )
    azure_cosmos_database_name: str = Field(
        default="cdss-db",
        description="Cosmos DB database name.",
    )
    azure_cosmos_patient_profiles_container: str = Field(
        default="patient-profiles",
        description="Container for patient profile documents.",
    )
    azure_cosmos_conversation_history_container: str = Field(
        default="conversation-history",
        description="Container for conversation turn history.",
    )
    azure_cosmos_embedding_cache_container: str = Field(
        default="embedding-cache",
        description="Container for cached embeddings.",
    )
    azure_cosmos_audit_log_container: str = Field(
        default="audit-log",
        description="Container for HIPAA-compliant audit log entries.",
    )
    azure_cosmos_agent_state_container: str = Field(
        default="agent-state",
        description="Container for agent execution state.",
    )

    # ── Azure Document Intelligence ──────────────────────────────────────────
    azure_document_intelligence_endpoint: str = Field(
        default="",
        description="Azure Document Intelligence (Form Recognizer) endpoint.",
    )
    azure_document_intelligence_key: str = Field(
        default="",
        description="Azure Document Intelligence API key.",
    )

    # ── Azure Key Vault ──────────────────────────────────────────────────────
    azure_key_vault_url: str = Field(
        default="",
        description="Azure Key Vault URL for secrets management.",
    )

    # ── Azure Blob Storage ───────────────────────────────────────────────────
    azure_blob_connection_string: str = Field(
        default="",
        description="Azure Blob Storage connection string.",
    )
    azure_blob_endpoint: str = Field(
        default="",
        description="Azure Blob Storage endpoint URL (for Entra ID auth).",
    )
    azure_blob_use_entra_id: bool = Field(
        default=False,
        description="Use Azure Entra ID (DefaultAzureCredential) for Blob Storage auth instead of connection string.",
    )
    azure_blob_protocols_container: str = Field(
        default="treatment-protocols",
        description="Blob container for uploaded protocol documents.",
    )

    # ── PubMed / Entrez ──────────────────────────────────────────────────────
    pubmed_api_key: str = Field(
        default="",
        description="NCBI PubMed API key for higher rate limits.",
    )
    pubmed_email: str = Field(
        default="",
        description="Email address required by NCBI Entrez.",
    )
    pubmed_base_url: str = Field(
        default="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        description="PubMed Entrez base URL.",
    )

    # ── OpenFDA ──────────────────────────────────────────────────────────────
    openfda_base_url: str = Field(
        default="https://api.fda.gov",
        description="OpenFDA API base URL.",
    )

    # ── RxNorm ───────────────────────────────────────────────────────────────
    rxnorm_base_url: str = Field(
        default="https://rxnav.nlm.nih.gov/REST",
        description="RxNorm REST API base URL.",
    )

    # ── DrugBank ─────────────────────────────────────────────────────────────
    drugbank_api_key: str = Field(
        default="",
        description="DrugBank API key for drug interaction data.",
    )
    drugbank_base_url: str = Field(
        default="https://api.drugbank.com/v1",
        description="DrugBank API base URL.",
    )

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching and rate limiting.",
    )

    # ── Application ──────────────────────────────────────────────────────────
    debug: bool = Field(
        default=False,
        description="Enable debug mode with verbose logging.",
    )
    use_mock_mode: bool = Field(
        default=False,
        description="Enable mock mode for local testing without Azure services.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001"],
        description="Allowed CORS origins.",
    )
    cors_allow_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="Allowed CORS methods.",
    )
    cors_allow_headers: list[str] = Field(
        default=["Authorization", "Content-Type", "X-Request-ID"],
        description="Allowed CORS headers.",
    )
    cors_expose_headers: list[str] = Field(
        default=["X-Request-ID", "X-Trace-ID"],
        description="CORS response headers exposed to clients.",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Whether CORS requests may include credentials.",
    )
    auth_enabled: bool = Field(
        default=False,
        description="Enable Azure Entra ID JWT authentication validation.",
    )
    auth_tenant_id: str = Field(
        default="",
        description="Azure Entra tenant ID used to validate JWT issuer and JWKS.",
    )
    auth_audience: str = Field(
        default="",
        description="Expected JWT audience (API application ID URI/client ID).",
    )
    auth_required_scopes: list[str] = Field(
        default_factory=list,
        description="Optional required scopes for API access (scp claim).",
    )
    max_concurrent_agents: int = Field(
        default=10,
        description="Maximum number of agents that can execute concurrently.",
    )
    response_timeout_seconds: int = Field(
        default=30,
        description="Maximum seconds to wait for a complete agent response.",
    )
    confidence_threshold: float = Field(
        default=0.6,
        description="Minimum confidence threshold for highlighting low-confidence responses.",
    )

    # -----------------------------------------------------------------
    # Alias properties for backward compatibility
    # cosmos_client.py expects cosmos_db_endpoint, cosmos_db_key, cosmos_db_database_name
    # -----------------------------------------------------------------

    @property
    def cosmos_db_endpoint(self) -> str:
        """Alias for backward compatibility with legacy code."""
        return self.azure_cosmos_endpoint

    @property
    def cosmos_db_key(self) -> str:
        """Alias for backward compatibility with legacy code."""
        return self.azure_cosmos_key

    @property
    def cosmos_db_database_name(self) -> str:
        """Alias for backward compatibility with legacy code."""
        return self.azure_cosmos_database_name

    @property
    def cosmos_db_use_entra_id(self) -> bool:
        """Alias for backward compatibility with legacy code."""
        return self.azure_cosmos_use_entra_id

    @property
    def keyvault_url(self) -> str:
        return self.azure_key_vault_url

    @property
    def blob_storage_connection_string(self) -> str:
        """Alias for backward compatibility with legacy code."""
        return self.azure_blob_connection_string

    @property
    def blob_storage_endpoint(self) -> str:
        """Alias for backward compatibility with legacy code."""
        return self.azure_blob_endpoint

    @property
    def blob_storage_use_entra_id(self) -> bool:
        """Alias for backward compatibility with legacy code."""
        return self.azure_blob_use_entra_id

    @property
    def blob_storage_container_name(self) -> str:
        """Alias for backward compatibility with legacy code."""
        return self.azure_blob_protocols_container

    @property
    def document_intelligence_endpoint(self) -> str:
        """Alias for backward compatibility with legacy code."""
        return self.azure_document_intelligence_endpoint

    @property
    def document_intelligence_api_key(self) -> str:
        """Alias for backward compatibility with legacy code."""
        return self.azure_document_intelligence_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance.

    The settings are loaded once from environment variables and the .env file,
    then cached for the lifetime of the process.
    """
    return Settings()
