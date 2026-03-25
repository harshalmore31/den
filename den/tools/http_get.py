"""http_get -- fetch a URL and return its content."""

from __future__ import annotations

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput

MAX_CONTENT = 50_000  # chars


class HttpGetTool(DenTool):
    name = "http_get"
    description = (
        "Fetch content from a URL. Returns the page content as text. "
        "Useful for reading documentation, APIs, or web pages found via web_search. "
        "URL must be from an allowed host in permissions.network."
    )
    version = "1.0.0"
    requires_network = True

    class Input(BaseModel):
        url: str = Field(description="URL to fetch (must be from an allowed host)")
        headers: dict[str, str] = Field(default_factory=dict, description="Optional HTTP headers")

    class Output(ToolOutput):
        content: str = ""
        status_code: int = 0
        content_type: str = ""
        truncated: bool = False

    def execute(self, input: Input) -> Output:
        try:
            import httpx
        except ImportError:
            raise ToolError("http_get requires 'httpx' package.")

        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                response = client.get(input.url, headers=input.headers)
        except httpx.TimeoutException:
            raise ToolError(
                f"Request timed out for '{input.url}'.",
                suggestions=["Try again", "Check if the site is accessible"],
            )
        except Exception as e:
            raise ToolError(f"Failed to fetch '{input.url}': {e}")

        content = response.text
        truncated = len(content) > MAX_CONTENT
        if truncated:
            content = content[:MAX_CONTENT]

        return self.Output(
            content=content,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            truncated=truncated,
        )
