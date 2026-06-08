"""Tool Chain Demo.

Demonstrates chaining multiple tools together to build
complex data processing pipelines. Shows how to compose
tool outputs as inputs to subsequent tools.

Usage:
    python examples/advanced/tool_chain_demo.py
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Tool Chain Models
# ---------------------------------------------------------------------------

@dataclass
class ToolStep:
    """A step in a tool chain that runs a specific tool."""
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    input_mapping: dict[str, str] = field(default_factory=dict)
    output_key: str = "result"
    description: str = ""


@dataclass
class ChainResult:
    """Result of executing a tool chain."""
    steps_executed: int = 0
    outputs: dict[str, Any] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    success: bool = True
    total_duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "steps_executed": self.steps_executed,
            "outputs": self.outputs,
            "errors": self.errors,
            "success": self.success,
            "total_duration_ms": self.total_duration_ms,
        }


class ToolChain:
    """Chain multiple tools together into a pipeline."""

    def __init__(self, name: str = "chain"):
        self.name = name
        self.steps: list[ToolStep] = []

    def add_step(self, tool_name: str, arguments: dict | None = None,
                 input_mapping: dict | None = None,
                 output_key: str = "result",
                 description: str = "") -> "ToolChain":
        self.steps.append(ToolStep(
            tool_name=tool_name,
            arguments=arguments or {},
            input_mapping=input_mapping or {},
            output_key=output_key,
            description=description,
        ))
        return self

    def describe(self) -> str:
        lines = [f"Tool Chain: {self.name} ({len(self.steps)} steps)"]
        for i, step in enumerate(self.steps):
            desc = step.description or step.tool_name
            lines.append(f"  {i+1}. {desc} (tool: {step.tool_name})")
            if step.input_mapping:
                for target, source in step.input_mapping.items():
                    lines.append(f"     Input: {target} <- {source}")
            lines.append(f"     Output: -> {step.output_key}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Example Chains
# ---------------------------------------------------------------------------

def build_data_analysis_chain() -> ToolChain:
    """Build a chain that reads CSV, computes stats, and generates a report."""
    return (
        ToolChain("Data Analysis Pipeline")
        .add_step(
            "csv_read",
            arguments={"data": "name,score\nAlice,95\nBob,87\nCharlie,92\nDiana,88\nEve,91"},
            output_key="csv_data",
            description="Read CSV data",
        )
        .add_step(
            "csv_stats",
            input_mapping={"data": "csv_data.csv"},
            output_key="stats",
            description="Compute column statistics",
        )
        .add_step(
            "random_string",
            arguments={"length": 8, "charset": "hex"},
            output_key="report_id",
            description="Generate report ID",
        )
    )


def build_color_palette_chain() -> ToolChain:
    """Build a chain that converts a color and generates a palette."""
    return (
        ToolChain("Color Palette Pipeline")
        .add_step(
            "color_convert",
            arguments={"value": "52,152,219", "from_format": "rgb"},
            output_key="base_color",
            description="Convert RGB to all formats",
        )
        .add_step(
            "color_palette",
            arguments={"count": 5, "palette_type": "analogous"},
            input_mapping={"base_color": "base_color.hex"},
            output_key="palette",
            description="Generate analogous palette",
        )
    )


def build_xml_to_csv_chain() -> ToolChain:
    """Build a chain that converts XML to JSON then processes it."""
    return (
        ToolChain("XML Processing Pipeline")
        .add_step(
            "xml_to_json",
            arguments={
                "xml": "<catalog><book id='1'><title>Python Guide</title><price>29.99</price></book>"
                       "<book id='2'><title>JS Guide</title><price>24.99</price></book></catalog>",
            },
            output_key="json_data",
            description="Convert XML to JSON",
        )
        .add_step(
            "xml_query",
            arguments={
                "xml": "<catalog><book id='1'><title>Python Guide</title></book>"
                       "<book id='2'><title>JS Guide</title></book></catalog>",
                "query": ".//book",
            },
            output_key="books",
            description="Query books from XML",
        )
    )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main():
    """Demonstrate tool chaining."""
    chains = [
        build_data_analysis_chain(),
        build_color_palette_chain(),
        build_xml_to_csv_chain(),
    ]

    for chain in chains:
        print("=" * 50)
        print(chain.describe())
        print("=" * 50)
        print()

    print("Tool chain definitions ready!")
    print(f"Total chains: {len(chains)}")
    print(f"Total steps: {sum(len(c.steps) for c in chains)}")
    print("\nNote: In production, these chains would be executed")
    print("through the JARVIS tool registry with actual tool calls.")


if __name__ == "__main__":
    main()
