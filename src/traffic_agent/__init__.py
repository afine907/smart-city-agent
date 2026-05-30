"""
LLM Traffic Controller — AI-Powered Traffic Signal Control

Multi-Agent system using LLMs for intelligent traffic management.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("llm-traffic-timing")
except PackageNotFoundError:
    __version__ = "0.2.0"  # fallback for development

__author__ = "afine907"
