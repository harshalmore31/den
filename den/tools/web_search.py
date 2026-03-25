"""web_search + web_context -- Brave Search tools for Den agents."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class ContextSnippet(BaseModel):
    url: str
    title: str
    snippets: list[str]


class SourceMeta(BaseModel):
    title: str
    hostname: str
    age: str = ""


def _get_brave_key() -> str:
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        raise ToolError(
            "BRAVE_API_KEY not set. Brave Search requires an API key.\n"
            "Get a free key (2000 queries/mo): https://brave.com/search/api/\n"
            "Then run: den auth brave",
            suggestions=["Run: den auth brave", "Or: export BRAVE_API_KEY=your-key"],
        )
    return key


class WebSearchTool(DenTool):
    name = "web_search"
    description = (
        "Search the web using Brave Search. Returns titles, URLs, and snippets. "
        "Use for quick research, fact-checking, finding sources, or discovering "
        "alternatives. For deep content extraction, use web_context instead."
    )
    version = "2.0.0"
    requires_network = True

    class Input(BaseModel):
        query: str = Field(description="Search query -- be specific for better results")
        max_results: int = Field(default=10, le=20, description="Maximum results")

    class Output(ToolOutput):
        results: list[SearchResult] = []
        query: str = ""
        total_found: int = 0

    def execute(self, input: Input) -> Output:
        import httpx
        api_key = _get_brave_key()

        try:
            response = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": input.query, "count": input.max_results},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ToolError("Invalid BRAVE_API_KEY. Check at brave.com/search/api")
            raise ToolError(f"Brave Search error: {e}")
        except Exception as e:
            raise ToolError(f"Search request failed: {e}")

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
            )
            for r in data.get("web", {}).get("results", [])
        ]

        return self.Output(
            results=results[:input.max_results],
            query=input.query,
            total_found=len(results),
        )


class WebContextTool(DenTool):
    name = "web_context"
    description = (
        "Get pre-extracted web content for LLM grounding. Unlike web_search which "
        "returns links and snippets, this returns actual page content (text, tables, "
        "code) ready for analysis. Use for deep research, RAG, fact-checking, or "
        "when you need to reason over full page content -- not just snippets."
    )
    version = "1.0.0"
    requires_network = True

    class Input(BaseModel):
        query: str = Field(description="Search query")
        max_tokens: int = Field(default=8192, ge=1024, le=32768, description="Max tokens of context")
        max_urls: int = Field(default=10, ge=1, le=50, description="Max URLs to extract from")
        freshness: str = Field(default="", description="Filter by freshness: pd (day), pw (week), pm (month), py (year)")
        threshold: str = Field(default="balanced", description="Relevance filter: strict, balanced, lenient, disabled")

    class Output(ToolOutput):
        content: list[ContextSnippet] = []
        sources: dict[str, SourceMeta] = {}
        query: str = ""
        total_urls: int = 0
        total_snippets: int = 0

    def execute(self, input: Input) -> Output:
        import httpx
        api_key = _get_brave_key()

        params = {
            "q": input.query,
            "maximum_number_of_tokens": input.max_tokens,
            "maximum_number_of_urls": input.max_urls,
            "context_threshold_mode": input.threshold,
        }
        if input.freshness:
            params["freshness"] = input.freshness

        try:
            response = httpx.get(
                "https://api.search.brave.com/res/v1/llm/context",
                params=params,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ToolError("Invalid BRAVE_API_KEY. Check at brave.com/search/api")
            raise ToolError(f"Brave LLM Context error: {e}")
        except Exception as e:
            raise ToolError(f"Context request failed: {e}")

        content = []
        total_snippets = 0
        for item in data.get("grounding", {}).get("generic", []):
            snippets = item.get("snippets", [])
            total_snippets += len(snippets)
            content.append(ContextSnippet(
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippets=snippets,
            ))

        sources = {}
        for url, meta in data.get("sources", {}).items():
            age_list = meta.get("age") or []
            age = age_list[-1] if age_list else ""
            sources[url] = SourceMeta(
                title=meta.get("title", ""),
                hostname=meta.get("hostname", ""),
                age=age,
            )

        return self.Output(
            content=content,
            sources=sources,
            query=input.query,
            total_urls=len(content),
            total_snippets=total_snippets,
        )
