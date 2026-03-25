"""Den Tool Library -- curated, reliable tools for AI agents."""

from den.tools._base import DenTool, ToolError, ToolOutput, ToolSpec
from den.tools._interceptor import PermissionInterceptor
from den.tools._registry import ToolRegistry, get_registry, register_tool

from den.tools.web_search import WebSearchTool, WebContextTool
from den.tools.http_get import HttpGetTool
from den.tools.file_read import FileReadTool
from den.tools.file_write import FileWriteTool
from den.tools.file_list import FileListTool
from den.tools.bash_tool import BashTool
from den.tools.python_exec import PythonExecTool
from den.tools.json_parse import JsonParseTool
from den.tools.csv_analyze import CsvAnalyzeTool
from den.tools.pdf_read import PdfReadTool


def _register_standard_tools() -> None:
    registry = get_registry()
    standard_tools = [
        WebSearchTool(),
        WebContextTool(),
        HttpGetTool(),
        FileReadTool(),
        FileWriteTool(),
        FileListTool(),
        BashTool(),
        PythonExecTool(),
        JsonParseTool(),
        CsvAnalyzeTool(),
        PdfReadTool(),
    ]
    for tool in standard_tools:
        try:
            registry.register(tool)
        except ValueError:
            pass


_register_standard_tools()


__all__ = [
    "DenTool",
    "ToolError",
    "ToolOutput",
    "ToolSpec",
    "ToolRegistry",
    "PermissionInterceptor",
    "get_registry",
    "register_tool",
    "WebSearchTool",
    "WebContextTool",
    "HttpGetTool",
    "FileReadTool",
    "FileWriteTool",
    "FileListTool",
    "BashTool",
    "PythonExecTool",
    "JsonParseTool",
    "CsvAnalyzeTool",
    "PdfReadTool",
]
