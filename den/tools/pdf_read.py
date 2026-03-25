"""pdf_read -- extract text from PDF files."""

from __future__ import annotations

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput

MAX_CHARS = 50_000


class PdfReadTool(DenTool):
    name = "pdf_read"
    description = (
        "Extract text from a PDF file. Returns the full text content. "
        "For large PDFs, specify page_start/page_end to read a range. "
        "Useful for reading research papers, reports, and documents."
    )
    version = "1.0.0"
    requires_filesystem = True

    class Input(BaseModel):
        path: str = Field(description="Path to PDF file")
        page_start: int | None = Field(default=None, description="Start page (0-indexed)")
        page_end: int | None = Field(default=None, description="End page (exclusive)")

    class Output(ToolOutput):
        text: str = ""
        page_count: int = 0
        pages_read: int = 0
        truncated: bool = False

    def execute(self, input: Input) -> Output:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ToolError("pdf_read requires 'pypdf' package. Install: pip install pypdf")

        try:
            reader = PdfReader(input.path)
        except FileNotFoundError:
            raise ToolError(f"PDF file not found: {input.path}")
        except Exception as e:
            raise ToolError(f"Failed to open PDF '{input.path}': {e}")

        total_pages = len(reader.pages)
        start = input.page_start or 0
        end = input.page_end or total_pages
        end = min(end, total_pages)

        text_parts = []
        pages_read = 0
        total_chars = 0

        for i in range(start, end):
            try:
                page_text = reader.pages[i].extract_text() or ""
                text_parts.append(f"--- Page {i + 1} ---\n{page_text}")
                pages_read += 1
                total_chars += len(page_text)
                if total_chars > MAX_CHARS:
                    break
            except Exception:
                text_parts.append(f"--- Page {i + 1} --- [extraction failed]")
                pages_read += 1

        text = "\n\n".join(text_parts)
        truncated = total_chars > MAX_CHARS

        return self.Output(
            text=text[:MAX_CHARS],
            page_count=total_pages,
            pages_read=pages_read,
            truncated=truncated,
        )
