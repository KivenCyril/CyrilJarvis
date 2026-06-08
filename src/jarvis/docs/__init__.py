"""JARVIS API Documentation Generator.

Provides tools for auto-generating OpenAPI specs, Markdown docs,
and HTML documentation from FastAPI applications and module introspection.
"""

from jarvis.docs.generator import APIDocGenerator, EndpointDoc, ModuleDoc, generate_api_docs

__all__ = ["APIDocGenerator", "EndpointDoc", "ModuleDoc", "generate_api_docs"]
