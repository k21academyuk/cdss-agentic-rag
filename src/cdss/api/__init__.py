"""FastAPI API layer for the Clinical Decision Support System.

Exports the main router and the application factory for convenient imports.
"""

from cdss.api.routes import router

__all__ = ["router"]
