"""Service client wrappers for the Clinical Decision Support System.

This package provides production-quality client wrappers for all Azure
services and external biomedical APIs used by the CDSS:

**Azure Services:**

- **AzureSearchClient**: Azure AI Search with hybrid search + semantic ranking.
- **CosmosDBClient**: Azure Cosmos DB for patient data, conversations, and state.
- **AzureOpenAIClient**: Azure OpenAI for chat completions and embeddings.
- **DocumentIntelligenceClient**: Azure Document Intelligence for medical PDF extraction.
- **BlobStorageClient**: Azure Blob Storage for treatment protocol documents.
- **KeyVaultClient**: Azure Key Vault for secret management.

**External Biomedical APIs:**

- **PubMedClient**: NCBI PubMed E-Utilities for biomedical literature search.
- **OpenFDAClient**: FDA adverse events, drug labeling, and recall data.
- **RxNormClient**: NLM RxNorm drug name normalization and interaction lookup.
- **DrugBankClient**: DrugBank drug-drug interaction checking.
"""

from cdss.clients.blob_storage_client import BlobStorageClient
from cdss.clients.cosmos_client import CosmosDBClient
from cdss.clients.document_intelligence_client import DocumentIntelligenceClient
from cdss.clients.drugbank_client import DrugBankClient, DrugBankClientError
from cdss.clients.keyvault_client import KeyVaultClient
from cdss.clients.openai_client import AzureOpenAIClient
from cdss.clients.openfda_client import OpenFDAClient, OpenFDAClientError
from cdss.clients.pubmed_client import PubMedClient, PubMedClientError
from cdss.clients.rxnorm_client import RxNormClient, RxNormClientError
from cdss.clients.search_client import AzureSearchClient

__all__ = [
    # Azure services
    "AzureOpenAIClient",
    "AzureSearchClient",
    "BlobStorageClient",
    "CosmosDBClient",
    "DocumentIntelligenceClient",
    "KeyVaultClient",
    # External biomedical API clients
    "DrugBankClient",
    "DrugBankClientError",
    "OpenFDAClient",
    "OpenFDAClientError",
    "PubMedClient",
    "PubMedClientError",
    "RxNormClient",
    "RxNormClientError",
]
