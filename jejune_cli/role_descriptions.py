"""Role project descriptions for the jejune CLI describe commands."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleDescription:
    title: str
    general_description: str
    responsibilities: tuple[str, ...]


# fmt: off
ROLE_DESCRIPTIONS: dict[str, RoleDescription] = {
    "doc-steward": RoleDescription(
        title="Document Steward",
        general_description=(
            "The Document Steward is responsible for the lifecycle of an individual"
            " jejune_doc_<name> repository: bringing a new document into the system"
            " and keeping its metadata accurate."
        ),
        responsibilities=(
            "Creates a new jejune_doc_<name> repository and populates it with the source document (markdown and/or PDF in original_data/).",
            "Adds a catalog.yaml file at the repository root specifying the document's title, authors, year, keywords, ISBN (if applicable), and the relative paths to its markdown file, optional PDF, and optional sentences file. This file is editorial content and is committed to the repository.",
            "Runs 'jejune convert' to convert a PDF source to markdown when needed.",
            "Runs 'jejune graph extract <doc_dir>' to build the knowledge graph for the document.",
            "Optionally makes a simple single document deployment to improve the document content.",
            "Notifies the Catalog Curator when a new document is ready to be registered in the full catalog.",
        ),
    ),
    "catalog-contributor": RoleDescription(
        title="Catalog Curator",
        general_description=(
            "The Catalog Curator is responsible for the collection as a whole:"
            " knowing which documents exist, keeping their catalog entries accurate,"
            " and making the collection available for deployment."
        ),
        responsibilities=(
            "Maintains jejune_docs_server/DockerContext/full-catalog.yaml: the canonical reference of all known jejune_doc_* repositories (name, url, public fields). This file is the single source of truth; any deployment catalog must be a validated subset of it.",
            "Registers new documents (upon notification from a Document Steward) by adding an entry to full-catalog.yaml.",
            "Runs 'jejune catalog check' periodically to validate that catalog entries match actual GitHub repository visibility.",
            "Runs 'jejune catalog sync' to detect locally cloned jj_doc_* repositories that are not yet in the catalog.",
        ),
    ),
    "deployer": RoleDescription(
        title="Deployer",
        general_description=(
            "The Deployer configures a specific deployment of the jejune system."
        ),
        responsibilities=(
            "Creates a deployment-specific catalog at jj_deployments/deploy_<name>/catalog.yaml: a subset of full-catalog.yaml, selecting the documents relevant for that deployment. build_docs.py validates names and URLs against full-catalog.yaml at build time and rejects any entry not present in it.",
            "Validates the deployment catalog before building via 'jejune catalog check-deployment /path/to/jj_deployments/deploy_<name>'.",
            "Builds jejune_docs_server with the deployment catalog injected as a Docker secret. When CATALOG_FILE is not set, the full catalog is used by default.",
            "Configures deployment-specific environment (Neo4j credentials, LLM endpoint, etc.).",
        ),
    ),
}
# fmt: on


def role_description(role_name: str) -> RoleDescription | None:
    """Return the project description for *role_name*, or None if undocumented."""
    return ROLE_DESCRIPTIONS.get(role_name)
