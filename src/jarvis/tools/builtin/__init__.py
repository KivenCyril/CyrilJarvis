"""Built-in tools shipped with JARVIS.

Importing this module registers every built-in tool in the global
``tool_registry``.
"""

from jarvis.tools.registry import tool_registry

from jarvis.tools.builtin.shell import ShellTool
from jarvis.tools.builtin.file_ops import ReadFileTool, WriteFileTool
from jarvis.tools.builtin.web_search import WebSearchTool
from jarvis.tools.builtin.python_exec import PythonExecTool

# --- New tool imports ---
from jarvis.tools.builtin.git_ops import GitStatusTool, GitDiffTool, GitLogTool
from jarvis.tools.builtin.http_client import HttpRequestTool, HttpDownloadTool
from jarvis.tools.builtin.json_ops import JsonQueryTool, YamlToJsonTool
from jarvis.tools.builtin.text_processing import RegexTool, TextSummaryTool, DiffTool
from jarvis.tools.builtin.system_info import SystemInfoTool, ProcessListTool
from jarvis.tools.builtin.directory_ops import ListDirectoryTool, FindFilesTool
from jarvis.tools.builtin.clipboard import ClipboardTool

# --- Batch 2 tool imports ---
from jarvis.tools.builtin.docker_ops import (
    DockerListTool, DockerLogsTool, DockerExecTool, DockerImagesTool,
)
from jarvis.tools.builtin.database_ops import (
    SQLiteQueryTool, SQLiteSchemasTool, CSVToSQLiteTool,
)
from jarvis.tools.builtin.image_ops import ImageInfoTool, ImageResizeTool, ScreenshotTool
from jarvis.tools.builtin.archive_ops import ZipCreateTool, ZipExtractTool
from jarvis.tools.builtin.network_ops import PingTool, DNSLookupTool, PortCheckTool
from jarvis.tools.builtin.math_ops import CalculatorTool, UnitConvertTool
from jarvis.tools.builtin.encoding_ops import Base64Tool, HashTool, URLEncodeTool
from jarvis.tools.builtin.datetime_ops import DateTimeTool, DateCalcTool
from jarvis.tools.builtin.template_ops import TemplateTool

# --- Batch 3 tool imports ---
from jarvis.tools.builtin.cron_ops import CronParseTool, CronValidateTool
from jarvis.tools.builtin.markdown_ops import MarkdownToHTMLTool, MarkdownTableTool
from jarvis.tools.builtin.jwt_ops import JWTDecodeTool, JWTValidateTool
from jarvis.tools.builtin.env_ops import EnvVarTool, EnvListTool
from jarvis.tools.builtin.uuid_ops import UUIDGenerateTool, UUIDValidateTool

# --- Batch 4 tool imports ---
from jarvis.tools.builtin.csv_ops import CSVReadTool, CSVWriteTool, CSVStatsTool
from jarvis.tools.builtin.xml_ops import XMLToJsonTool, XMLQueryTool
from jarvis.tools.builtin.color_ops import ColorConvertTool, ColorPaletteTool
from jarvis.tools.builtin.random_ops import RandomStringTool, RandomNumberTool, RandomChoiceTool

_BUILTIN_TOOLS = [
    # Original tools
    ShellTool(),
    ReadFileTool(),
    WriteFileTool(),
    WebSearchTool(),
    PythonExecTool(),
    # Git operations
    GitStatusTool(),
    GitDiffTool(),
    GitLogTool(),
    # HTTP client
    HttpRequestTool(),
    HttpDownloadTool(),
    # JSON/YAML processing
    JsonQueryTool(),
    YamlToJsonTool(),
    # Text processing
    RegexTool(),
    TextSummaryTool(),
    DiffTool(),
    # System information
    SystemInfoTool(),
    ProcessListTool(),
    # Directory operations
    ListDirectoryTool(),
    FindFilesTool(),
    # Clipboard
    ClipboardTool(),
    # --- Batch 2 ---
    # Docker operations
    DockerListTool(),
    DockerLogsTool(),
    DockerExecTool(),
    DockerImagesTool(),
    # Database operations
    SQLiteQueryTool(),
    SQLiteSchemasTool(),
    CSVToSQLiteTool(),
    # Image operations
    ImageInfoTool(),
    ImageResizeTool(),
    ScreenshotTool(),
    # Archive operations
    ZipCreateTool(),
    ZipExtractTool(),
    # Network operations
    PingTool(),
    DNSLookupTool(),
    PortCheckTool(),
    # Math operations
    CalculatorTool(),
    UnitConvertTool(),
    # Encoding/hashing
    Base64Tool(),
    HashTool(),
    URLEncodeTool(),
    # Date/time
    DateTimeTool(),
    DateCalcTool(),
    # Template rendering
    TemplateTool(),
    # --- Batch 3 ---
    # Cron operations
    CronParseTool(),
    CronValidateTool(),
    # Markdown operations
    MarkdownToHTMLTool(),
    MarkdownTableTool(),
    # JWT operations
    JWTDecodeTool(),
    JWTValidateTool(),
    # Environment variables
    EnvVarTool(),
    EnvListTool(),
    # UUID operations
    UUIDGenerateTool(),
    UUIDValidateTool(),
    # --- Batch 4 ---
    # CSV operations
    CSVReadTool(),
    CSVWriteTool(),
    CSVStatsTool(),
    # XML operations
    XMLToJsonTool(),
    XMLQueryTool(),
    # Color operations
    ColorConvertTool(),
    ColorPaletteTool(),
    # Random operations
    RandomStringTool(),
    RandomNumberTool(),
    RandomChoiceTool(),
]

for _tool in _BUILTIN_TOOLS:
    tool_registry.register(_tool)
