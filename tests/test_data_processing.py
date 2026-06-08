"""Data processing pipeline tests.

Tests data transformation, aggregation, filtering, sorting,
format conversion, and pipeline composition.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

import pytest


# ---------------------------------------------------------------------------
# Data Processing Models
# ---------------------------------------------------------------------------

@dataclass
class DataColumn:
    name: str
    values: list[Any] = field(default_factory=list)
    dtype: str = "auto"  # auto, string, number, boolean, datetime

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def non_null_count(self) -> int:
        return sum(1 for v in self.values if v is not None and v != "")

    @property
    def null_count(self) -> int:
        return self.count - self.non_null_count

    @property
    def unique_count(self) -> int:
        return len(set(v for v in self.values if v is not None))

    def numeric_values(self) -> list[float]:
        result = []
        for v in self.values:
            if v is None or v == "":
                continue
            try:
                result.append(float(v))
            except (ValueError, TypeError):
                pass
        return result

    @property
    def is_numeric(self) -> bool:
        nums = self.numeric_values()
        return len(nums) == self.non_null_count and nums

    def stats(self) -> dict[str, Any]:
        if self.is_numeric:
            nums = self.numeric_values()
            return {
                "type": "numeric",
                "count": len(nums),
                "min": min(nums),
                "max": max(nums),
                "mean": round(statistics.mean(nums), 4),
                "median": round(statistics.median(nums), 4),
                "stdev": round(statistics.stdev(nums), 4) if len(nums) >= 2 else 0,
                "sum": round(sum(nums), 4),
            }
        else:
            return {
                "type": "text",
                "count": self.count,
                "unique": self.unique_count,
                "null_count": self.null_count,
                "most_common": max(set(self.values), key=self.values.count) if self.values else None,
            }


@dataclass
class DataFrame:
    """Simple DataFrame for data processing."""
    columns: dict[str, DataColumn] = field(default_factory=dict)
    _row_count: int = 0

    @classmethod
    def from_records(cls, records: list[dict]) -> "DataFrame":
        if not records:
            return cls()
        df = cls()
        all_keys = set()
        for r in records:
            all_keys.update(r.keys())
        for key in all_keys:
            values = [r.get(key) for r in records]
            df.columns[key] = DataColumn(name=key, values=values)
        df._row_count = len(records)
        return df

    @classmethod
    def from_csv_string(cls, csv_str: str, delimiter: str = ",") -> "DataFrame":
        import csv
        import io
        reader = csv.DictReader(io.StringIO(csv_str), delimiter=delimiter)
        records = list(reader)
        return cls.from_records(records)

    @property
    def row_count(self) -> int:
        return self._row_count

    @property
    def column_names(self) -> list[str]:
        return list(self.columns.keys())

    @property
    def shape(self) -> tuple[int, int]:
        return (self.row_count, len(self.columns))

    def select(self, column_names: list[str]) -> "DataFrame":
        df = DataFrame()
        for name in column_names:
            if name in self.columns:
                df.columns[name] = DataColumn(
                    name=name, values=list(self.columns[name].values),
                )
        df._row_count = self.row_count
        return df

    def filter(self, column: str, predicate: Callable) -> "DataFrame":
        if column not in self.columns:
            return DataFrame()
        col = self.columns[column]
        mask = [predicate(v) for v in col.values]
        df = DataFrame()
        for name, col in self.columns.items():
            filtered_values = [v for v, m in zip(col.values, mask) if m]
            df.columns[name] = DataColumn(name=name, values=filtered_values)
        df._row_count = sum(mask)
        return df

    def sort_by(self, column: str, ascending: bool = True) -> "DataFrame":
        if column not in self.columns:
            return self
        col = self.columns[column]
        indices = list(range(len(col.values)))
        try:
            indices.sort(key=lambda i: float(col.values[i]) if col.values[i] else float('inf'),
                        reverse=not ascending)
        except (ValueError, TypeError):
            indices.sort(key=lambda i: str(col.values[i] or ""),
                        reverse=not ascending)
        df = DataFrame()
        for name, c in self.columns.items():
            df.columns[name] = DataColumn(
                name=name, values=[c.values[i] for i in indices],
            )
        df._row_count = self.row_count
        return df

    def add_column(self, name: str, values: list[Any]) -> None:
        self.columns[name] = DataColumn(name=name, values=values)

    def rename_column(self, old_name: str, new_name: str) -> bool:
        if old_name not in self.columns:
            return False
        col = self.columns.pop(old_name)
        col.name = new_name
        self.columns[new_name] = col
        return True

    def drop_column(self, name: str) -> bool:
        if name in self.columns:
            del self.columns[name]
            return True
        return False

    def head(self, n: int = 5) -> list[dict]:
        records = []
        for i in range(min(n, self.row_count)):
            record = {}
            for name, col in self.columns.items():
                record[name] = col.values[i] if i < len(col.values) else None
            records.append(record)
        return records

    def describe(self) -> dict[str, dict]:
        return {name: col.stats() for name, col in self.columns.items()}

    def to_records(self) -> list[dict]:
        return self.head(self.row_count)

    def group_by(self, column: str) -> dict[str, "DataFrame"]:
        if column not in self.columns:
            return {}
        groups: dict[str, list[int]] = {}
        for i, v in enumerate(self.columns[column].values):
            key = str(v)
            groups.setdefault(key, []).append(i)

        result = {}
        for key, indices in groups.items():
            df = DataFrame()
            for name, col in self.columns.items():
                df.columns[name] = DataColumn(
                    name=name, values=[col.values[i] for i in indices],
                )
            df._row_count = len(indices)
            result[key] = df
        return result


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class DataPipeline:
    """Composable data processing pipeline."""

    def __init__(self):
        self.steps: list[tuple[str, Callable]] = []

    def add_step(self, name: str, transform: Callable) -> "DataPipeline":
        self.steps.append((name, transform))
        return self

    def execute(self, df: DataFrame) -> DataFrame:
        result = df
        for name, transform in self.steps:
            result = transform(result)
        return result

    @property
    def step_count(self) -> int:
        return len(self.steps)


# ---------------------------------------------------------------------------
# Tests: DataColumn
# ---------------------------------------------------------------------------

class TestDataColumn:
    def test_create_column(self):
        col = DataColumn(name="age", values=[25, 30, 35])
        assert col.count == 3
        assert col.name == "age"

    def test_numeric_detection(self):
        col = DataColumn(name="val", values=[1, 2, 3])
        nums = col.numeric_values()
        assert len(nums) == 3

    def test_text_detection(self):
        col = DataColumn(name="name", values=["Alice", "Bob"])
        assert col.is_numeric is False

    def test_null_count(self):
        col = DataColumn(name="val", values=[1, None, 3, None])
        assert col.null_count == 2
        assert col.non_null_count == 2

    def test_unique_count(self):
        col = DataColumn(name="val", values=[1, 2, 2, 3, 3, 3])
        assert col.unique_count == 3

    def test_numeric_stats(self):
        col = DataColumn(name="val", values=["10", "20", "30"])
        stats = col.stats()
        assert stats["type"] == "numeric"
        assert stats["min"] == 10
        assert stats["max"] == 30
        assert stats["mean"] == 20

    def test_text_stats(self):
        col = DataColumn(name="color", values=["red", "blue", "red"])
        stats = col.stats()
        assert stats["type"] == "text"
        assert stats["unique"] == 2
        assert stats["most_common"] == "red"

    def test_empty_column(self):
        col = DataColumn(name="empty", values=[])
        assert col.count == 0
        assert col.null_count == 0


# ---------------------------------------------------------------------------
# Tests: DataFrame - Creation
# ---------------------------------------------------------------------------

class TestDataFrameCreation:
    def test_from_records(self):
        records = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        df = DataFrame.from_records(records)
        assert df.row_count == 2
        assert df.shape == (2, 2)

    def test_from_csv_string(self):
        csv = "name,age\nAlice,30\nBob,25"
        df = DataFrame.from_csv_string(csv)
        assert df.row_count == 2
        assert "name" in df.column_names

    def test_empty_records(self):
        df = DataFrame.from_records([])
        assert df.row_count == 0

    def test_column_names(self):
        records = [{"a": 1, "b": 2, "c": 3}]
        df = DataFrame.from_records(records)
        assert set(df.column_names) == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# Tests: DataFrame - Operations
# ---------------------------------------------------------------------------

class TestDataFrameOperations:
    @pytest.fixture
    def sample_df(self):
        return DataFrame.from_records([
            {"name": "Alice", "age": "30", "city": "NYC"},
            {"name": "Bob", "age": "25", "city": "LA"},
            {"name": "Charlie", "age": "35", "city": "NYC"},
            {"name": "Diana", "age": "28", "city": "LA"},
            {"name": "Eve", "age": "32", "city": "NYC"},
        ])

    def test_select_columns(self, sample_df):
        df = sample_df.select(["name", "city"])
        assert set(df.column_names) == {"name", "city"}
        assert df.row_count == 5

    def test_select_nonexistent_column(self, sample_df):
        df = sample_df.select(["name", "nonexistent"])
        assert "name" in df.column_names
        assert "nonexistent" not in df.column_names

    def test_filter_rows(self, sample_df):
        df = sample_df.filter("city", lambda v: v == "NYC")
        assert df.row_count == 3

    def test_filter_numeric(self, sample_df):
        df = sample_df.filter("age", lambda v: int(v) >= 30)
        assert df.row_count == 3

    def test_sort_ascending(self, sample_df):
        df = sample_df.sort_by("age", ascending=True)
        ages = df.columns["age"].values
        assert ages[0] == "25"
        assert ages[-1] == "35"

    def test_sort_descending(self, sample_df):
        df = sample_df.sort_by("age", ascending=False)
        ages = df.columns["age"].values
        assert ages[0] == "35"

    def test_add_column(self, sample_df):
        sample_df.add_column("score", [90, 85, 95, 80, 88])
        assert "score" in sample_df.column_names

    def test_rename_column(self, sample_df):
        assert sample_df.rename_column("name", "full_name") is True
        assert "full_name" in sample_df.column_names
        assert "name" not in sample_df.column_names

    def test_rename_nonexistent(self, sample_df):
        assert sample_df.rename_column("missing", "new") is False

    def test_drop_column(self, sample_df):
        assert sample_df.drop_column("city") is True
        assert "city" not in sample_df.column_names

    def test_drop_nonexistent(self, sample_df):
        assert sample_df.drop_column("missing") is False

    def test_head(self, sample_df):
        records = sample_df.head(2)
        assert len(records) == 2

    def test_head_exceeds_rows(self, sample_df):
        records = sample_df.head(100)
        assert len(records) == 5

    def test_describe(self, sample_df):
        desc = sample_df.describe()
        assert "name" in desc
        assert "age" in desc
        assert desc["age"]["type"] == "numeric"
        assert desc["name"]["type"] == "text"

    def test_to_records(self, sample_df):
        records = sample_df.to_records()
        assert len(records) == 5
        assert "name" in records[0]

    def test_group_by(self, sample_df):
        groups = sample_df.group_by("city")
        assert "NYC" in groups
        assert "LA" in groups
        assert groups["NYC"].row_count == 3
        assert groups["LA"].row_count == 2

    def test_group_by_nonexistent(self, sample_df):
        groups = sample_df.group_by("missing")
        assert groups == {}


# ---------------------------------------------------------------------------
# Tests: DataFrame - Chaining
# ---------------------------------------------------------------------------

class TestDataFrameChaining:
    def test_filter_then_sort(self):
        df = DataFrame.from_records([
            {"name": "Alice", "score": "90"},
            {"name": "Bob", "score": "70"},
            {"name": "Charlie", "score": "85"},
            {"name": "Diana", "score": "95"},
        ])
        result = df.filter("score", lambda v: int(v) >= 80).sort_by("score", ascending=False)
        assert result.row_count == 3
        assert result.columns["score"].values[0] == "95"

    def test_select_then_filter(self):
        df = DataFrame.from_records([
            {"name": "Alice", "age": "30", "city": "NYC"},
            {"name": "Bob", "age": "25", "city": "LA"},
        ])
        result = df.select(["name", "age"]).filter("age", lambda v: int(v) > 25)
        assert result.row_count == 1
        assert "city" not in result.column_names


# ---------------------------------------------------------------------------
# Tests: DataPipeline
# ---------------------------------------------------------------------------

class TestDataPipeline:
    def test_empty_pipeline(self):
        pipeline = DataPipeline()
        df = DataFrame.from_records([{"a": 1}])
        result = pipeline.execute(df)
        assert result.row_count == 1

    def test_single_step(self):
        pipeline = DataPipeline()
        pipeline.add_step("filter", lambda df: df.filter("age", lambda v: int(v) >= 30))

        df = DataFrame.from_records([
            {"name": "A", "age": "25"},
            {"name": "B", "age": "35"},
        ])
        result = pipeline.execute(df)
        assert result.row_count == 1

    def test_multi_step_pipeline(self):
        pipeline = DataPipeline()
        pipeline.add_step("filter", lambda df: df.filter("score", lambda v: int(v) >= 50))
        pipeline.add_step("sort", lambda df: df.sort_by("score", ascending=False))
        pipeline.add_step("select", lambda df: df.select(["name", "score"]))

        df = DataFrame.from_records([
            {"name": "A", "score": "90", "extra": "x"},
            {"name": "B", "score": "30", "extra": "y"},
            {"name": "C", "score": "75", "extra": "z"},
        ])
        result = pipeline.execute(df)
        assert result.row_count == 2
        assert "extra" not in result.column_names
        assert result.columns["score"].values[0] == "90"

    def test_pipeline_chaining(self):
        pipeline = (
            DataPipeline()
            .add_step("step1", lambda df: df)
            .add_step("step2", lambda df: df)
        )
        assert pipeline.step_count == 2

    def test_pipeline_step_count(self):
        pipeline = DataPipeline()
        assert pipeline.step_count == 0
        pipeline.add_step("a", lambda df: df)
        assert pipeline.step_count == 1


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------

class TestDataProcessingEdgeCases:
    def test_single_row(self):
        df = DataFrame.from_records([{"a": "1"}])
        assert df.row_count == 1
        assert df.columns["a"].stats()["type"] == "numeric"

    def test_all_nulls(self):
        df = DataFrame.from_records([{"a": None}, {"a": None}])
        assert df.columns["a"].null_count == 2

    def test_mixed_types(self):
        df = DataFrame.from_records([
            {"val": "10"},
            {"val": "abc"},
            {"val": "30"},
        ])
        assert df.columns["val"].is_numeric is False

    def test_large_dataset(self):
        records = [{"id": str(i), "val": str(i * 10)} for i in range(1000)]
        df = DataFrame.from_records(records)
        assert df.row_count == 1000
        # Columns from DictReader are always strings
        nums = df.columns["val"].numeric_values()
        assert len(nums) == 1000

    def test_empty_string_values(self):
        df = DataFrame.from_records([{"a": ""}, {"a": "x"}, {"a": ""}])
        assert df.columns["a"].non_null_count == 1

    def test_special_characters(self):
        df = DataFrame.from_records([
            {"name": "O'Brien"},
            {"name": "von D."},
            {"name": "Test, Jr."},
        ])
        assert df.row_count == 3
