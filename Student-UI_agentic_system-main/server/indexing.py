"""Blob upload and search-indexer trigger for instructor file uploads."""

from __future__ import annotations

import logging

import httpx

from agentic_system.config import SystemConfig

logger = logging.getLogger(__name__)


def upload_blob(config: SystemConfig, filename: str, data: bytes) -> str:
    from azure.storage.blob import BlobServiceClient

    client = BlobServiceClient.from_connection_string(config.azure_blob_connection_string)
    blob = client.get_blob_client(container=config.azure_blob_container, blob=filename)
    blob.upload_blob(data, overwrite=True)
    return blob.url


def run_indexer(config: SystemConfig) -> int:
    endpoint = config.azure_search_endpoint.rstrip("/")
    url = f"{endpoint}/indexers/{config.azure_search_indexer_name}/run?api-version=2024-07-01"
    resp = httpx.post(url, headers={"api-key": config.azure_search_admin_key})
    resp.raise_for_status()
    return resp.status_code


def get_indexer_status(config: SystemConfig) -> dict:
    endpoint = config.azure_search_endpoint.rstrip("/")
    url = f"{endpoint}/indexers/{config.azure_search_indexer_name}/status?api-version=2024-07-01"
    resp = httpx.get(url, headers={"api-key": config.azure_search_admin_key})
    resp.raise_for_status()
    return resp.json()
