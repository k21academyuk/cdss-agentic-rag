"""Service layer for the Clinical Decision Support System.

Exports the ClinicalQueryService for convenient imports.
"""

from cdss.services.query_service import ClinicalQueryService

__all__ = ["ClinicalQueryService"]
