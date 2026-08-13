"""Agent specializations for the multi-agent RAG system."""

from app.services.agents.document_analyst import DocumentAnalyst
from app.services.agents.fact_checker import FactChecker
from app.services.agents.summarizer import Summarizer
from app.services.agents.web_researcher import WebResearcher

__all__ = ["DocumentAnalyst", "WebResearcher", "FactChecker", "Summarizer"]
