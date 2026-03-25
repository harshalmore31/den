"""Tests for the Den tool library."""

import json
import os
import tempfile

import pytest

from den.agentfile.schema import Permissions
from den.tools._base import DenTool, ToolError, ToolOutput, ToolSpec
from den.tools._registry import ToolRegistry, get_registry
from den.tools._interceptor import PermissionInterceptor
from den.tools.file_read import FileReadTool
from den.tools.file_write import FileWriteTool
from den.tools.file_list import FileListTool
from den.tools.json_parse import JsonParseTool
from den.tools.python_exec import PythonExecTool
from den.tools.csv_analyze import CsvAnalyzeTool
from den.tools.bash_tool import BashTool


# ---------------------------------------------------------------------------
# DenTool base
# ---------------------------------------------------------------------------


class TestDenToolBase:
    def test_custom_tool(self):
        from pydantic import BaseModel

        class MyTool(DenTool):
            name = "my_tool"
            description = "Test tool"
            version = "1.0.0"

            class Input(BaseModel):
                text: str

            class Output(ToolOutput):
                upper: str = ""

            def execute(self, input):
                return self.Output(upper=input.text.upper())

        tool = MyTool()
        result = tool(text="hello")
        assert result["success"] is True
        assert result["upper"] == "HELLO"

    def test_callable_propagates_tool_error(self):
        from pydantic import BaseModel

        class FailTool(DenTool):
            name = "fail_tool"
            description = "Fails"
            version = "1.0.0"

            class Input(BaseModel):
                pass

            def execute(self, input):
                raise ToolError("Something went wrong", suggestions=["Try X"])

        tool = FailTool()
        with pytest.raises(ToolError, match="Something went wrong"):
            tool()

    def test_get_spec(self):
        from pydantic import BaseModel

        class SpecTool(DenTool):
            name = "spec_tool"
            description = "Has a spec"
            version = "2.0.0"
            requires_network = True

            class Input(BaseModel):
                query: str

            def execute(self, input):
                return self.Output()

        spec = SpecTool().get_spec()
        assert isinstance(spec, ToolSpec)
        assert spec.name == "spec_tool"
        assert spec.requires_network is True
        assert spec.version == "2.0.0"
        assert "query" in json.dumps(spec.input_schema)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_global_registry_has_standard_tools(self):
        registry = get_registry()
        tools = registry.list_tools()
        assert "file_read" in tools
        assert "file_write" in tools
        assert "web_search" in tools
        assert "bash" in tools
        assert "python_exec" in tools
        assert "json_parse" in tools
        assert "csv_analyze" in tools
        assert registry.count >= 10

    def test_load_tools_subset(self):
        registry = get_registry()
        loaded = registry.load_tools(["file_read", "file_write"])
        assert len(loaded) == 2
        assert "file_read" in loaded

    def test_load_unknown_tool_raises(self):
        registry = get_registry()
        with pytest.raises(ValueError, match="Unknown tool"):
            registry.load_tools(["nonexistent_tool"])

    def test_get_callables(self):
        registry = get_registry()
        callables = registry.get_callables(["json_parse"])
        assert "json_parse" in callables
        assert callable(callables["json_parse"])


# ---------------------------------------------------------------------------
# Permission interceptor
# ---------------------------------------------------------------------------


class TestPermissionInterceptor:
    def test_blocks_network(self):
        perms = Permissions(network=["api.example.com"], filesystem=["/den/workspace"])
        interceptor = PermissionInterceptor(perms)
        tool = HttpGetToolStub()
        interceptor.wrap(tool)

        with pytest.raises(ToolError, match="Network access denied"):
            tool(url="https://evil.com/data")

    def test_allows_network(self):
        perms = Permissions(
            network=["api.example.com"],
            filesystem=["/den/workspace"],
        )
        interceptor = PermissionInterceptor(perms)
        tool = HttpGetToolStub()
        interceptor.wrap(tool)
        # Should not raise
        result = tool(url="https://api.example.com/data")
        assert result["success"] is True

    def test_blocks_filesystem(self):
        perms = Permissions(filesystem=["/den/workspace"])
        interceptor = PermissionInterceptor(perms)
        tool = FileReadTool()
        interceptor.wrap(tool)

        with pytest.raises(ToolError, match="Filesystem access denied"):
            tool(path="/etc/passwd")

    def test_blocks_path_traversal(self):
        """Ensure /den/../../etc/passwd is blocked."""
        perms = Permissions(filesystem=["/den/workspace"])
        interceptor = PermissionInterceptor(perms)
        tool = FileReadTool()
        interceptor.wrap(tool)

        with pytest.raises(ToolError, match="Filesystem access denied"):
            tool(path="/den/../../etc/passwd")

    def test_blocks_bash_when_shell_false(self):
        perms = Permissions(shell=False)
        interceptor = PermissionInterceptor(perms)
        tool = BashTool()
        interceptor.wrap(tool)

        with pytest.raises(ToolError, match="Shell execution is not permitted"):
            tool(command="echo hi")


class HttpGetToolStub(DenTool):
    """Stub for testing network permission checks."""
    name = "http_get_stub"
    description = "Stub"
    version = "1.0.0"
    requires_network = True

    class Input(ToolOutput):
        url: str = ""

    class Output(ToolOutput):
        content: str = "ok"

    def execute(self, input):
        return self.Output()


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------


class TestFileTools:
    def test_file_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            writer = FileWriteTool()
            result = writer(path=path, content="hello world")
            assert result["success"]
            assert result["created"]

            reader = FileReadTool()
            result = reader(path=path)
            assert result["success"]
            assert "hello world" in result["content"]

    def test_file_read_with_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "code.py")
            FileWriteTool()(path=path, content="line 1\nfoo bar\nline 3\nbaz\nline 5\n")

            result = FileReadTool()(path=path, search="foo")
            assert result["success"]
            assert "foo bar" in result["content"]

    def test_file_read_not_found(self):
        with pytest.raises(ToolError, match="File not found"):
            FileReadTool()(path="/nonexistent/file.txt")

    def test_file_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.txt"), "w").close()
            open(os.path.join(tmpdir, "b.py"), "w").close()

            result = FileListTool()(path=tmpdir)
            assert result["success"]
            assert len(result["entries"]) == 2

    def test_file_list_with_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.txt"), "w").close()
            open(os.path.join(tmpdir, "b.py"), "w").close()

            result = FileListTool()(path=tmpdir, pattern="*.py")
            assert result["success"]
            assert len(result["entries"]) == 1
            assert result["entries"][0]["name"] == "b.py"


# ---------------------------------------------------------------------------
# JSON tool
# ---------------------------------------------------------------------------


class TestJsonParse:
    def test_parse_string(self):
        result = JsonParseTool()(content='{"name": "Den", "version": "1.0"}')
        assert result["success"]
        data = json.loads(result["data"])
        assert data["name"] == "Den"

    def test_query_dot_notation(self):
        result = JsonParseTool()(
            content='{"data": {"users": [{"name": "Alice"}, {"name": "Bob"}]}}',
            query="data.users.[0].name",
        )
        assert result["success"]
        assert "Alice" in result["data"]

    def test_parse_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            f.flush()
            result = JsonParseTool()(file_path=f.name)
            assert result["success"]
            assert "key" in result["keys"]
        os.unlink(f.name)

    def test_invalid_json(self):
        with pytest.raises(ToolError, match="Invalid JSON"):
            JsonParseTool()(content="{bad json}")


# ---------------------------------------------------------------------------
# Python exec
# ---------------------------------------------------------------------------


class TestPythonExec:
    def test_basic_exec(self):
        result = PythonExecTool()(code="print('hello from python')")
        assert result["success"]
        assert "hello from python" in result["stdout"]

    def test_math(self):
        result = PythonExecTool()(code="print(2 ** 10)")
        assert "1024" in result["stdout"]

    def test_error_handling(self):
        result = PythonExecTool()(code="raise ValueError('test error')")
        assert result["success"] is False
        assert "ValueError" in result["stderr"]


# ---------------------------------------------------------------------------
# CSV tool
# ---------------------------------------------------------------------------


class TestCsvAnalyze:
    def test_basic_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age,score\nAlice,30,95\nBob,25,87\nCharlie,35,92\n")
            f.flush()
            result = CsvAnalyzeTool()(path=f.name)
            assert result["success"]
            assert result["row_count"] == 3
            assert "name" in result["columns"]
            assert len(result["sample_rows"]) == 3
        os.unlink(f.name)

    def test_csv_filter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,score\nAlice,95\nBob,87\nCharlie,92\n")
            f.flush()
            result = CsvAnalyzeTool()(path=f.name, query="score > 90")
            assert result["success"]
            assert len(result["sample_rows"]) == 2  # Alice and Charlie
        os.unlink(f.name)

    def test_csv_not_found(self):
        with pytest.raises(ToolError, match="CSV file not found"):
            CsvAnalyzeTool()(path="/nonexistent.csv")
