"""Custom exception hierarchy for the Clinical Decision Support System.

All CDSS-specific exceptions inherit from CDSSError, making it easy
to catch any system error at the top level while still allowing
fine-grained handling of specific failure modes.
"""


class CDSSError(Exception):
    """Base exception for all CDSS errors.

    Attributes:
        message: Human-readable error description.
        details: Optional dictionary with structured error context.
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, details={self.details!r})"


class AzureServiceError(CDSSError):
    """Raised when an Azure service call fails.

    Covers Azure OpenAI, AI Search, Cosmos DB, Blob Storage,
    Document Intelligence, and Key Vault failures.

    Attributes:
        service_name: Name of the Azure service that failed.
        status_code: HTTP status code returned, if applicable.
    """

    def __init__(
        self,
        message: str,
        service_name: str = "",
        status_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        self.service_name = service_name
        self.status_code = status_code
        super().__init__(message, details)


class AgentError(CDSSError):
    """Raised when an agent encounters an execution error.

    Attributes:
        agent_name: Name of the agent that failed.
    """

    def __init__(
        self,
        message: str,
        agent_name: str = "",
        details: dict | None = None,
    ) -> None:
        self.agent_name = agent_name
        super().__init__(message, details)


class AgentTimeoutError(AgentError):
    """Raised when an agent exceeds its allowed execution time.

    Attributes:
        timeout_seconds: The timeout threshold that was exceeded.
    """

    def __init__(
        self,
        message: str,
        agent_name: str = "",
        timeout_seconds: float | None = None,
        details: dict | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(message, agent_name, details)


class RetrieverError(CDSSError):
    """Raised when RAG retrieval fails.

    Covers errors during vector search, hybrid search, or
    document retrieval from any knowledge source.

    Attributes:
        retriever_name: Name of the retriever that failed.
        index_name: Search index involved, if applicable.
    """

    def __init__(
        self,
        message: str,
        retriever_name: str = "",
        index_name: str = "",
        details: dict | None = None,
    ) -> None:
        self.retriever_name = retriever_name
        self.index_name = index_name
        super().__init__(message, details)


class DrugSafetyError(CDSSError):
    """Raised when drug interaction or safety checks fail.

    Attributes:
        drug_names: List of drug names involved in the failed check.
    """

    def __init__(
        self,
        message: str,
        drug_names: list[str] | None = None,
        details: dict | None = None,
    ) -> None:
        self.drug_names = drug_names or []
        super().__init__(message, details)


class DocumentProcessingError(CDSSError):
    """Raised when Azure Document Intelligence fails to process a document.

    Attributes:
        document_id: Identifier of the document that failed processing.
        document_type: Type/format of the document (e.g., PDF, DICOM).
    """

    def __init__(
        self,
        message: str,
        document_id: str = "",
        document_type: str = "",
        details: dict | None = None,
    ) -> None:
        self.document_id = document_id
        self.document_type = document_type
        super().__init__(message, details)


class GuardrailsViolation(CDSSError):
    """Raised when a response fails guardrails validation.

    This exception is raised when hallucination detection, safety checks,
    or other guardrails identify problems with a generated response.

    Attributes:
        violations: List of specific guardrail violations detected.
        original_response: The response that failed validation.
    """

    def __init__(
        self,
        message: str,
        violations: list[str] | None = None,
        original_response: str = "",
        details: dict | None = None,
    ) -> None:
        self.violations = violations or []
        self.original_response = original_response
        super().__init__(message, details)


class AuthenticationError(CDSSError):
    """Raised when authentication or authorization fails.

    Covers Azure AD token failures, API key validation errors,
    and insufficient permissions.
    """

    def __init__(
        self,
        message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details)


class RateLimitError(CDSSError):
    """Raised when an API rate limit is exceeded.

    Attributes:
        retry_after: Suggested number of seconds to wait before retrying.
            None if the service did not provide a Retry-After header.
    """

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        details: dict | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, details)


class ValidationError(CDSSError):
    """Raised when input data fails validation.

    Covers clinical query validation, patient data validation,
    and any other domain-specific validation failures.

    Attributes:
        field_errors: Mapping of field names to their validation error messages.
    """

    def __init__(
        self,
        message: str,
        field_errors: dict[str, str] | None = None,
        details: dict | None = None,
    ) -> None:
        self.field_errors = field_errors or {}
        super().__init__(message, details)
