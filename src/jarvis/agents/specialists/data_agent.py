from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive data analysis specialist
# ---------------------------------------------------------------------------

DATA_AGENT_SYSTEM_PROMPT = """\
You are a data analysis specialist within the JARVIS assistant system.

# Capabilities
- Data exploration, profiling, and quality assessment
- Statistical analysis (descriptive, inferential, correlation, regression)
- Data transformation, cleaning, and feature engineering
- Visualization design and chart recommendation
- Python/pandas/numpy code generation for data workflows
- SQL query generation and optimization

You have access to tools: python_execute, read_file, write_file, shell_execute.
Use Python for all data analysis tasks. Prefer pandas for tabular data, numpy for
numerical computation, and describe visualization with matplotlib/seaborn/plotly.

# Execution protocol
1. **Ingest** -- detect format, load data, inspect shape and dtypes.
2. **Profile** -- null counts, distributions, cardinality, outliers.
3. **Assess quality** -- run the data quality checklist (see below).
4. **Analyze** -- apply the appropriate analysis workflow.
5. **Visualize** -- recommend and generate the best chart type.
6. **Report** -- present findings with context, not just numbers.

# Data quality assessment checklist
When profiling a dataset, check:
- [ ] Schema consistency (column names, types stable across rows)
- [ ] Completeness (null/missing percentage per column)
- [ ] Uniqueness (duplicate rows, candidate key violations)
- [ ] Validity (values within expected ranges, regex for formats)
- [ ] Timeliness (data freshness, temporal gaps)
- [ ] Accuracy (cross-reference with known good sources if available)
- [ ] Consistency (referential integrity across related tables)

# Statistical analysis workflows

## Descriptive statistics
- Central tendency: mean, median, mode
- Dispersion: std, variance, IQR, range
- Shape: skewness, kurtosis
- Frequency tables for categorical variables

## Inferential statistics
- Hypothesis testing (t-test, chi-square, ANOVA)
- Confidence intervals
- Effect size (Cohen's d, eta-squared)
- Assumptions checking (normality, homoscedasticity)

## Correlation & regression
- Pearson, Spearman, Kendall correlations
- Correlation matrix / heatmap
- Simple and multiple linear regression
- Residual analysis

## Time series
- Trend decomposition (trend, seasonal, residual)
- Stationarity tests (ADF, KPSS)
- Autocorrelation (ACF, PACF)
- Moving averages and exponential smoothing

# Visualization recommendation engine
Choose chart type based on the analytical question:

| Question                          | Recommended chart          |
|-----------------------------------|----------------------------|
| Distribution of one variable      | Histogram, KDE, box plot   |
| Comparison across categories      | Bar chart, grouped bar     |
| Relationship between 2 numerics   | Scatter plot               |
| Trend over time                   | Line chart, area chart     |
| Part-to-whole composition         | Pie chart, stacked bar     |
| Correlation matrix                | Heatmap                    |
| Geographical data                 | Choropleth, bubble map     |
| High-dimensional exploration      | Pair plot, parallel coords |
| Ranking                           | Horizontal bar, lollipop   |

Always label axes, add titles, and use colorblind-friendly palettes.

# Python/pandas code patterns
- Use `pd.read_csv()` / `pd.read_json()` / `pd.read_excel()` for loading
- Chain operations: `df.pipe().assign().query().groupby()`
- Use `.describe()` for quick numeric summaries
- Use `.info()` and `.dtypes` for schema inspection
- Use `.isna().sum()` for missing-value audit
- For large datasets, use chunked reading or dask
"""

# ---------------------------------------------------------------------------
# Dataset format detection
# ---------------------------------------------------------------------------

_FORMAT_PATTERNS: dict[str, list[str]] = {
    "csv": ["csv", ".csv", "comma-separated", "tsv", ".tsv", "tab-separated"],
    "json": ["json", ".json", "jsonl", "ndjson"],
    "excel": ["excel", ".xlsx", ".xls", "spreadsheet", "workbook"],
    "sql": ["sql", "database", "mysql", "postgres", "sqlite", "query", "table"],
    "parquet": ["parquet", ".parquet", "arrow", "columnar"],
    "xml": ["xml", ".xml"],
}

# ---------------------------------------------------------------------------
# Analysis type definitions
# ---------------------------------------------------------------------------

_ANALYSIS_PROFILING = "profiling"
_ANALYSIS_STATISTICS = "statistics"
_ANALYSIS_TRANSFORM = "transform"
_ANALYSIS_VISUALIZATION = "visualization"
_ANALYSIS_CORRELATION = "correlation"
_ANALYSIS_TIMESERIES = "timeseries"
_ANALYSIS_GENERAL = "analysis"

_ANALYSIS_KEYWORDS: list[tuple[list[str], str]] = [
    (["profile", "探索", "explore", "overview", "概览", "inspect", "shape", "info", "describe"], _ANALYSIS_PROFILING),
    (
        ["statistic", "统计", "mean", "median", "average", "均值", "方差", "std", "variance",
         "hypothesis", "t-test", "chi-square", "anova", "p-value", "confidence"],
        _ANALYSIS_STATISTICS,
    ),
    (
        ["transform", "clean", "清洗", "转换", "normalize", "归一化", "fill", "fillna",
         "drop", "merge", "join", "pivot", "melt", "encode", "scale", "impute"],
        _ANALYSIS_TRANSFORM,
    ),
    (
        ["chart", "图表", "plot", "visualiz", "可视化", "graph", "histogram", "scatter",
         "heatmap", "bar chart", "line chart", "pie", "dashboard"],
        _ANALYSIS_VISUALIZATION,
    ),
    (
        ["correlat", "相关", "regression", "回归", "relationship", "关系", "r-squared",
         "pearson", "spearman"],
        _ANALYSIS_CORRELATION,
    ),
    (
        ["time series", "时间序列", "trend", "趋势", "seasonal", "forecast", "预测",
         "moving average", "autocorrelation"],
        _ANALYSIS_TIMESERIES,
    ),
]

# ---------------------------------------------------------------------------
# Strategy-specific prompt augmentations
# ---------------------------------------------------------------------------

_ANALYSIS_PROMPTS: dict[str, str] = {
    _ANALYSIS_PROFILING: (
        "Perform a thorough data profiling:\n"
        "1. Load the data and show shape, dtypes.\n"
        "2. Run `.describe()` for numeric and `.value_counts()` for categoricals.\n"
        "3. Check missing values with `.isna().sum()`.\n"
        "4. Identify potential outliers using IQR or z-scores.\n"
        "5. Summarize data quality using the checklist."
    ),
    _ANALYSIS_STATISTICS: (
        "Perform statistical analysis:\n"
        "1. Compute descriptive statistics (central tendency, dispersion, shape).\n"
        "2. Check assumptions (normality via Shapiro-Wilk, homoscedasticity via Levene).\n"
        "3. Apply the appropriate test based on the question and data type.\n"
        "4. Report effect size alongside p-values.\n"
        "5. State conclusions in plain language."
    ),
    _ANALYSIS_TRANSFORM: (
        "Perform data transformation:\n"
        "1. Document the current state of data issues.\n"
        "2. Handle missing values (drop, fill, impute -- justify the choice).\n"
        "3. Fix data types and parse dates.\n"
        "4. Normalize/scale numeric features if needed.\n"
        "5. Encode categorical variables (one-hot, label, ordinal).\n"
        "6. Verify transformations with before/after comparisons."
    ),
    _ANALYSIS_VISUALIZATION: (
        "Design and generate visualizations:\n"
        "1. Identify the analytical question being answered.\n"
        "2. Choose the optimal chart type from the recommendation table.\n"
        "3. Generate clean, publication-quality charts with matplotlib/seaborn.\n"
        "4. Use colorblind-friendly palettes (e.g. 'colorblind', 'viridis').\n"
        "5. Add proper labels, titles, legends, and annotations."
    ),
    _ANALYSIS_CORRELATION: (
        "Perform correlation and regression analysis:\n"
        "1. Compute pairwise correlations (Pearson for linear, Spearman for monotonic).\n"
        "2. Generate a correlation heatmap.\n"
        "3. Fit regression model if appropriate.\n"
        "4. Analyze residuals for model validity.\n"
        "5. Report R-squared and statistical significance."
    ),
    _ANALYSIS_TIMESERIES: (
        "Perform time series analysis:\n"
        "1. Parse and set datetime index.\n"
        "2. Resample to appropriate frequency.\n"
        "3. Decompose into trend, seasonal, and residual.\n"
        "4. Test stationarity (ADF test).\n"
        "5. Compute ACF/PACF.\n"
        "6. Suggest forecasting approach."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _ANALYSIS_PROFILING: (
        "Data profiled: 10 columns, 1,000 rows.\n"
        "- 2 columns with >5% missing values.\n"
        "- 3 potential outliers detected in 'amount' column (z > 3).\n"
        "- Candidate key: 'id' column is unique."
    ),
    _ANALYSIS_STATISTICS: (
        "Statistical summary computed:\n"
        "- mean=45.2, median=42.0, std=12.8 for 'value' column.\n"
        "- Distribution is right-skewed (skewness=1.3).\n"
        "- Shapiro-Wilk p=0.003 -- non-normal, use non-parametric tests."
    ),
    _ANALYSIS_TRANSFORM: (
        "Data transformation applied:\n"
        "- Filled 45 nulls in 'category' with mode.\n"
        "- Imputed 12 nulls in 'amount' with median.\n"
        "- Normalized 3 numeric columns to [0,1] range.\n"
        "- Encoded 2 categorical columns with one-hot."
    ),
    _ANALYSIS_VISUALIZATION: (
        "Chart recommendation:\n"
        "- Categorical comparison -> bar chart.\n"
        "- Temporal trend -> line chart with markers.\n"
        "- Distribution -> histogram with KDE overlay.\n"
        "- Correlation -> heatmap with annotations."
    ),
    _ANALYSIS_CORRELATION: (
        "Correlation analysis:\n"
        "- Pearson r=0.82 (p<0.001) between 'price' and 'quantity'.\n"
        "- R-squared=0.67 for linear regression model.\n"
        "- Residuals are approximately normal (Shapiro p=0.12)."
    ),
    _ANALYSIS_TIMESERIES: (
        "Time series analysis:\n"
        "- Strong upward trend detected.\n"
        "- Weekly seasonality with peaks on Mondays.\n"
        "- ADF test p=0.32 -- non-stationary, differencing needed.\n"
        "- Recommended: ARIMA(1,1,1) or exponential smoothing."
    ),
    _ANALYSIS_GENERAL: "Data analysis complete.",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def detect_dataset_format(text: str) -> str | None:
    """Detect the dataset format mentioned in *text*."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for fmt, patterns in _FORMAT_PATTERNS.items():
        score = sum(1 for p in patterns if p in lower)
        if score:
            scores[fmt] = score
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def recommend_chart(question_type: str) -> str:
    """Return a chart recommendation for the given analytical question type."""
    mapping: dict[str, str] = {
        "distribution": "histogram or KDE plot",
        "comparison": "bar chart or grouped bar chart",
        "relationship": "scatter plot",
        "trend": "line chart or area chart",
        "composition": "pie chart or stacked bar chart",
        "correlation": "heatmap",
        "ranking": "horizontal bar chart",
        "geographical": "choropleth map",
    }
    return mapping.get(question_type, "bar chart (default)")


def build_profiling_summary(stats: dict[str, Any]) -> str:
    """Build a human-readable profiling summary from computed statistics."""
    lines = [f"Dataset: {stats.get('rows', '?')} rows x {stats.get('cols', '?')} columns"]
    if stats.get("missing"):
        lines.append(f"Missing values: {stats['missing']} cells ({stats.get('missing_pct', '?')}%)")
    if stats.get("duplicates"):
        lines.append(f"Duplicate rows: {stats['duplicates']}")
    if stats.get("outliers"):
        lines.append(f"Outlier columns: {', '.join(stats['outliers'])}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DataAgent
# ---------------------------------------------------------------------------

class DataAgent(BaseAgent):
    """Specialist agent for data analysis and processing tasks.

    Supports multiple analysis workflows:
    - **profiling**: data exploration, shape, types, quality assessment
    - **statistics**: descriptive, inferential, hypothesis testing
    - **transform**: cleaning, normalization, encoding, imputation
    - **visualization**: chart recommendation and generation
    - **correlation**: pairwise correlations, regression analysis
    - **timeseries**: decomposition, stationarity, forecasting
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="data-agent",
            description="Data exploration, statistical analysis, and visualization",
            skills=["data-analysis", "statistics", "csv", "json", "pandas", "visualization"],
            input_modes=["text", "structured-data"],
            output_modes=["text", "structured-data"],
            domain="data",
            can_delegate=True,
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[DataAgent] Processing: %s", message[:80])

        analysis_type = self._classify(message)
        dataset_format = detect_dataset_format(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(analysis_type, dataset_format)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=8,
            )
            if result.success:
                return result
            logger.warning("[DataAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[DataAgent] Task type: '{analysis_type}'"
        if dataset_format:
            output += f", format='{dataset_format}'"
        output += ". "
        output += _MOCK_OUTPUTS.get(analysis_type, _MOCK_OUTPUTS[_ANALYSIS_GENERAL])

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "data", "数据", "csv", "json", "analyze", "分析",
            "statistics", "统计", "chart", "图表", "pandas", "excel",
            "table", "表格", "column", "列", "row", "行",
            "dataset", "数据集", "visualization", "可视化",
            "dataframe", "plot", "histogram", "aggregate", "聚合",
            "correlation", "regression", "time series", "forecast",
            "parquet", "sql query", "pivot", "groupby",
        ]
        msg = message.lower()
        hits = sum(1 for k in keywords if k in msg)
        return min(hits * 0.25, 1.0)

    # -- private helpers ---------------------------------------------------

    def _classify(self, message: str) -> str:
        msg = message.lower()
        for keywords, category in _ANALYSIS_KEYWORDS:
            if any(k in msg for k in keywords):
                return category
        return _ANALYSIS_GENERAL

    def _build_system_prompt(self, analysis_type: str, dataset_format: str | None) -> str:
        """Compose an analysis-specific system prompt with format context."""
        parts = [DATA_AGENT_SYSTEM_PROMPT]

        augmentation = _ANALYSIS_PROMPTS.get(analysis_type)
        if augmentation:
            parts.append(f"\n# Current analysis task: {analysis_type}\n{augmentation}")

        if dataset_format:
            parts.append(
                f"\n# Detected dataset format: {dataset_format}\n"
                f"Use the appropriate pandas reader for {dataset_format} files."
            )

        return "\n".join(parts)
