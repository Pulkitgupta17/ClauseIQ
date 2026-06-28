"""MCP server entry point (stdio transport) for Claude Desktop.

Registers three tools on a :class:`FastMCP` server and runs over stdio. Logs go
to stderr (configured in :mod:`clauseiq.logging_config`) so they never corrupt
the stdout JSON-RPC stream.

Run directly (``python -m clauseiq.interfaces.mcp.server``) or via the
``clauseiq-mcp`` console script; see ``docs/MCP_INSTALL.md`` for the
``claude_desktop_config.json`` snippet.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from clauseiq.interfaces.mcp import tools
from clauseiq.logging_config import configure_logging, get_logger

log = get_logger(__name__)

mcp = FastMCP(
    "clauseiq",
    instructions=(
        "ClauseIQ analyses Indian contracts. Use analyze_contract to flag unfair "
        "clauses with severity and cited law; search_indian_law to look up sections "
        "of the Indian Contract Act, 1872; and verify_citation to confirm a cited "
        "section exists before relying on it."
    ),
)


@mcp.tool()
async def analyze_contract(contract_text: str) -> dict[str, Any]:
    """Analyse an Indian contract: flag unfair clauses with a 1-5 severity, a
    rationale, and citations to the exact sections of Indian law that back each flag.

    Args:
        contract_text: The full text of the contract to analyse.
    """
    return await tools.analyze_contract(contract_text)


@mcp.tool()
async def search_indian_law(query: str, k: int = 5) -> dict[str, Any]:
    """Search the Indian Contract Act, 1872 for sections relevant to a query.

    Args:
        query: A legal topic or question (e.g. "agreement in restraint of trade").
        k: Number of sections to return (default 5).
    """
    return await tools.search_indian_law(query, k)


@mcp.tool()
async def verify_citation(claim: str, citation: str) -> dict[str, Any]:
    """Verify that a cited section of Indian law actually exists in the corpus.

    Args:
        claim: The legal claim the citation is meant to support.
        citation: The citation to check, e.g. "ICA_1872:27" or "Section 27".
    """
    return await tools.verify_citation(claim, citation)


def main() -> None:
    """Run the MCP server over stdio."""
    configure_logging()
    log.info("mcp_server_starting", transport="stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
