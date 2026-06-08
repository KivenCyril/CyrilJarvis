"""Random generation tools: strings, numbers, and choices."""

from __future__ import annotations

import json
import random
import secrets
import string
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class RandomStringTool(BaseTool):
    """Generate random strings with configurable character sets."""

    name = "random_string"
    description = (
        "Generate a random string with configurable length and character set. "
        "Useful for passwords, tokens, identifiers, and test data. "
        "Uses cryptographically secure random when 'secure' is true."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "length": {
                "type": "integer",
                "description": "Length of the string to generate (default: 16, max: 10000).",
            },
            "charset": {
                "type": "string",
                "enum": [
                    "alphanumeric",
                    "alpha",
                    "digits",
                    "hex",
                    "lowercase",
                    "uppercase",
                    "printable",
                    "custom",
                ],
                "description": "Character set to use (default: 'alphanumeric').",
            },
            "custom_chars": {
                "type": "string",
                "description": "Custom character set when charset is 'custom'.",
            },
            "count": {
                "type": "integer",
                "description": "Number of strings to generate (default: 1, max: 100).",
            },
            "secure": {
                "type": "boolean",
                "description": "Use cryptographically secure random (default: false).",
            },
            "prefix": {
                "type": "string",
                "description": "Optional prefix to prepend to each generated string.",
            },
            "suffix": {
                "type": "string",
                "description": "Optional suffix to append to each generated string.",
            },
            "separator": {
                "type": "string",
                "description": (
                    "Insert this separator every N characters within the random "
                    "portion (e.g. '-' every 4 chars for 'abcd-efgh')."
                ),
            },
            "separator_every": {
                "type": "integer",
                "description": "Insert separator every N characters (default: 4).",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        length: int = min(arguments.get("length", 16), 10000)
        charset_name: str = arguments.get("charset", "alphanumeric")
        custom_chars: str = arguments.get("custom_chars", "")
        count: int = min(arguments.get("count", 1), 100)
        secure: bool = arguments.get("secure", False)
        prefix: str = arguments.get("prefix", "")
        suffix: str = arguments.get("suffix", "")
        separator: str | None = arguments.get("separator")
        separator_every: int = arguments.get("separator_every", 4)

        charset_map = {
            "alphanumeric": string.ascii_letters + string.digits,
            "alpha": string.ascii_letters,
            "digits": string.digits,
            "hex": string.hexdigits[:16],
            "lowercase": string.ascii_lowercase,
            "uppercase": string.ascii_uppercase,
            "printable": string.printable.strip(),
            "custom": custom_chars,
        }

        chars = charset_map.get(charset_name, "")
        if not chars:
            return ToolResult(
                success=False,
                output=f"Empty character set. For 'custom', provide custom_chars.",
            )

        if length < 1:
            return ToolResult(success=False, output="Length must be at least 1.")

        results: list[str] = []
        for _ in range(count):
            if secure:
                raw = "".join(secrets.choice(chars) for _ in range(length))
            else:
                raw = "".join(random.choice(chars) for _ in range(length))

            # Apply separator
            if separator and separator_every > 0:
                chunks = [
                    raw[i: i + separator_every]
                    for i in range(0, len(raw), separator_every)
                ]
                raw = separator.join(chunks)

            results.append(f"{prefix}{raw}{suffix}")

        if count == 1:
            output = results[0]
        else:
            output = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(results))

        return ToolResult(
            success=True,
            output=output,
            data={"strings": results, "count": count, "length": length},
        )


class RandomNumberTool(BaseTool):
    """Generate random numbers (integers or floats) within a range."""

    name = "random_number"
    description = (
        "Generate random numbers within a specified range. Supports both "
        "integer and floating-point numbers. Can generate multiple numbers "
        "at once and optionally ensure uniqueness."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "min": {
                "type": "number",
                "description": "Minimum value (inclusive, default: 0).",
            },
            "max": {
                "type": "number",
                "description": "Maximum value (inclusive, default: 100).",
            },
            "count": {
                "type": "integer",
                "description": "How many numbers to generate (default: 1, max: 1000).",
            },
            "type": {
                "type": "string",
                "enum": ["integer", "float"],
                "description": "Number type (default: 'integer').",
            },
            "precision": {
                "type": "integer",
                "description": "Decimal places for floats (default: 2).",
            },
            "unique": {
                "type": "boolean",
                "description": "Ensure all generated numbers are unique (default: false).",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility (optional).",
            },
            "distribution": {
                "type": "string",
                "enum": ["uniform", "normal", "triangular"],
                "description": "Distribution type (default: 'uniform').",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        min_val: float = arguments.get("min", 0)
        max_val: float = arguments.get("max", 100)
        count: int = min(arguments.get("count", 1), 1000)
        num_type: str = arguments.get("type", "integer")
        precision: int = arguments.get("precision", 2)
        unique: bool = arguments.get("unique", False)
        seed: int | None = arguments.get("seed")
        distribution: str = arguments.get("distribution", "uniform")

        if min_val > max_val:
            return ToolResult(
                success=False, output=f"min ({min_val}) must be <= max ({max_val})"
            )

        rng = random.Random(seed)

        if num_type == "integer":
            int_min = int(min_val)
            int_max = int(max_val)

            if unique and count > (int_max - int_min + 1):
                return ToolResult(
                    success=False,
                    output=(
                        f"Cannot generate {count} unique integers in range "
                        f"[{int_min}, {int_max}] (only {int_max - int_min + 1} possible)."
                    ),
                )

            if unique:
                population = list(range(int_min, int_max + 1))
                rng.shuffle(population)
                numbers: list[int | float] = population[:count]
            else:
                numbers = [rng.randint(int_min, int_max) for _ in range(count)]
        else:
            numbers = []
            seen: set[float] = set()
            attempts = 0
            max_attempts = count * 100

            while len(numbers) < count and attempts < max_attempts:
                attempts += 1
                if distribution == "normal":
                    mid = (min_val + max_val) / 2
                    stddev = (max_val - min_val) / 6
                    val = rng.gauss(mid, stddev)
                    val = max(min_val, min(max_val, val))
                elif distribution == "triangular":
                    val = rng.triangular(min_val, max_val)
                else:
                    val = rng.uniform(min_val, max_val)

                val = round(val, precision)

                if unique:
                    if val not in seen:
                        seen.add(val)
                        numbers.append(val)
                else:
                    numbers.append(val)

            if len(numbers) < count:
                return ToolResult(
                    success=False,
                    output=f"Could only generate {len(numbers)} unique floats in range.",
                )

        if count == 1:
            output = str(numbers[0])
        else:
            output = json.dumps(numbers)

        return ToolResult(
            success=True,
            output=output,
            data={"numbers": numbers, "count": count, "min": min_val, "max": max_val},
        )


class RandomChoiceTool(BaseTool):
    """Randomly pick one or more items from a list."""

    name = "random_choice"
    description = (
        "Randomly select one or more items from a provided list. "
        "Supports weighted selection and sampling with or without "
        "replacement. Useful for randomising task assignment, picks, "
        "A/B testing splits, etc."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The list of items to choose from.",
            },
            "count": {
                "type": "integer",
                "description": "Number of items to select (default: 1).",
            },
            "weights": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Optional weights for each item (must match items length). "
                    "Higher weight = higher probability of selection."
                ),
            },
            "replacement": {
                "type": "boolean",
                "description": (
                    "Sample with replacement (same item can be picked multiple "
                    "times). Default: false."
                ),
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility (optional).",
            },
            "shuffle": {
                "type": "boolean",
                "description": (
                    "Instead of picking, return the full list in random order. "
                    "Ignores count and weights when true. Default: false."
                ),
            },
        },
        "required": ["items"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        items: list[str] = arguments["items"]
        count: int = arguments.get("count", 1)
        weights: list[float] | None = arguments.get("weights")
        replacement: bool = arguments.get("replacement", False)
        seed: int | None = arguments.get("seed")
        do_shuffle: bool = arguments.get("shuffle", False)

        if not items:
            return ToolResult(success=False, output="Items list is empty.")

        rng = random.Random(seed)

        if do_shuffle:
            shuffled = list(items)
            rng.shuffle(shuffled)
            output = json.dumps(shuffled)
            return ToolResult(
                success=True,
                output=output,
                data={"selected": shuffled, "mode": "shuffle"},
            )

        if weights and len(weights) != len(items):
            return ToolResult(
                success=False,
                output=f"Weights length ({len(weights)}) must match items length ({len(items)}).",
            )

        if not replacement and count > len(items):
            return ToolResult(
                success=False,
                output=(
                    f"Cannot select {count} unique items from a list of {len(items)} "
                    f"without replacement."
                ),
            )

        if replacement:
            if weights:
                selected = rng.choices(items, weights=weights, k=count)
            else:
                selected = rng.choices(items, k=count)
        else:
            if weights:
                # Weighted sampling without replacement
                pool = list(zip(items, weights))
                selected = []
                for _ in range(count):
                    remaining_items = [p[0] for p in pool]
                    remaining_weights = [p[1] for p in pool]
                    chosen = rng.choices(
                        remaining_items, weights=remaining_weights, k=1
                    )[0]
                    selected.append(chosen)
                    pool = [p for p in pool if p[0] != chosen]
            else:
                selected = rng.sample(items, count)

        if count == 1:
            output = selected[0]
        else:
            output = json.dumps(selected)

        return ToolResult(
            success=True,
            output=output,
            data={"selected": selected, "count": count, "from_total": len(items)},
        )
