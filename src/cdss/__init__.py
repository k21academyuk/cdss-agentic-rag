"""Clinical Decision Support System with Agentic RAG on Azure.

This package provides a multi-agent clinical decision support system
that leverages Retrieval-Augmented Generation (RAG) with Azure AI
services to deliver evidence-based clinical recommendations.
"""

from cdss.core.config import Settings, get_settings
from cdss.core.models import ClinicalQuery, ClinicalResponse, PatientProfile

__all__ = [
    "ClinicalQuery",
    "ClinicalResponse",
    "PatientProfile",
    "Settings",
    "get_settings",
]
