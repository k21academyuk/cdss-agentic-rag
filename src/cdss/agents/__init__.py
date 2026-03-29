"""CDSS Specialist Agents package.

Exports all agent classes used in the Clinical Decision Support System
agentic pipeline. Each agent is a BaseAgent subclass that can be
dispatched by the orchestrator to perform a specialized clinical task.

Agents:
    BaseAgent: Abstract base class for all CDSS agents.
    PatientHistoryAgent: Retrieves and synthesizes patient context.
    MedicalLiteratureAgent: Searches PubMed and literature cache for evidence.
    ProtocolAgent: Matches clinical guidelines and treatment protocols.
    DrugSafetyAgent: Checks drug interactions, adverse events, and allergy safety.
    GuardrailsAgent: Validates clinical output for safety and quality.
"""

from cdss.agents.base import BaseAgent
from cdss.agents.drug_safety import DrugSafetyAgent
from cdss.agents.guardrails import GuardrailsAgent
from cdss.agents.medical_literature import MedicalLiteratureAgent
from cdss.agents.patient_history import PatientHistoryAgent
from cdss.agents.protocol_agent import ProtocolAgent

__all__ = [
    "BaseAgent",
    "PatientHistoryAgent",
    "MedicalLiteratureAgent",
    "ProtocolAgent",
    "DrugSafetyAgent",
    "GuardrailsAgent",
]
