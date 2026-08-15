"""Vercel serverless entrypoint for the Aivatar FastAPI control plane."""

from src.api.main import app

__all__ = ["app"]
