"""Per-course Azure resource + local-directory provisioning.

`create_course_resources` is called when a new course is being created;
`delete_course_resources` is its inverse. We only auto-manage the **blob
container** here — Azure AI Search resources (index / indexer / datasource)
are project-specific schemas that should be defined externally (Bicep / ARM
/ portal). The names live on the course row so the harness can reference
them; teardown returns those names to the admin for manual cleanup.

Lazy-imports the Azure SDK the same way `server/indexing.py` does.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from agentic_system import SystemConfig

logger = logging.getLogger(__name__)


def create_course_resources(config: SystemConfig, course: dict) -> None:
    """Create the per-course blob container if Azure blob storage is configured.

    Idempotent: if the container already exists, this is a no-op. Raises
    on any other failure so the caller (the admin create-course endpoint)
    can roll back the SQL insert.
    """
    if not config.azure_blob_connection_string:
        logger.info(
            "Skipping blob container create for course %s — no AZURE_BLOB_CONNECTION_STRING",
            course["id"],
        )
        return

    container = course["blob_container_name"]
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient

    client = BlobServiceClient.from_connection_string(config.azure_blob_connection_string)
    try:
        client.create_container(container)
        logger.info("Created blob container %s for course %s", container, course["id"])
    except ResourceExistsError:
        logger.info("Blob container %s already exists; reusing", container)


def delete_course_resources(
    config: SystemConfig, course: dict, data_root: Path
) -> dict:
    """Tear down per-course resources we own.

    Returns a dict with the names of resources we did NOT delete (so the
    admin can clean them up manually). Search resources fall in this bucket.
    """
    leftovers: dict = {
        "search_index_name": course["search_index_name"],
        "search_indexer_name": course["search_indexer_name"],
        "search_datasource_name": course["search_datasource_name"],
    }

    # 1. Per-course SQLite directory.
    course_dir = Path(data_root) / "courses" / course["id"]
    if course_dir.exists():
        try:
            shutil.rmtree(course_dir)
            logger.info("Removed %s", course_dir)
        except OSError as e:
            logger.warning("Failed to remove %s: %s", course_dir, e)

    # 2. Blob container (only if blob storage is configured).
    if config.azure_blob_connection_string:
        from azure.core.exceptions import ResourceNotFoundError
        from azure.storage.blob import BlobServiceClient

        client = BlobServiceClient.from_connection_string(
            config.azure_blob_connection_string
        )
        try:
            client.delete_container(course["blob_container_name"])
            logger.info("Deleted blob container %s", course["blob_container_name"])
        except ResourceNotFoundError:
            logger.info(
                "Blob container %s did not exist", course["blob_container_name"]
            )
        except Exception as e:  # pragma: no cover
            logger.warning(
                "Failed to delete blob container %s: %s",
                course["blob_container_name"], e,
            )
            leftovers["blob_container_name"] = course["blob_container_name"]

    return leftovers


def derive_resource_names(course_id: str, overrides: dict | None = None) -> dict:
    """Compute the conventional Azure resource names for a course.

    `overrides` lets the admin supply pre-existing names (when the search
    index has already been provisioned externally). Anything missing falls
    back to the convention ``course-{uuid_short}-{...}``.
    """
    short = course_id.split("-")[0]
    defaults = {
        "blob_container_name": f"course-{short}",
        "search_index_name": f"course-{short}-idx",
        "search_indexer_name": f"course-{short}-indexer",
        "search_datasource_name": f"course-{short}-ds",
    }
    if overrides:
        for k, v in overrides.items():
            if v:
                defaults[k] = v
    return defaults
