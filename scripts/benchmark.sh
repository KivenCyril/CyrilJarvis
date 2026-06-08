#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS - Benchmark Runner
# =============================================================================

PYTHON="${PYTHON:-.venv/bin/python}"
ITERATIONS="${1:-50}"
OUTPUT_DIR="benchmarks"

echo ""
echo "  JARVIS Benchmark Suite"
echo "  ======================"
echo ""

# --- Pre-flight checks ---
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: Python not found at $PYTHON"
    echo "Run 'make install' first."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$OUTPUT_DIR/bench_${TIMESTAMP}.json"

echo "Python:     $PYTHON"
echo "Iterations: $ITERATIONS"
echo "Output:     $RESULT_FILE"
echo ""

# --- Run benchmarks ---
echo "--- Core Benchmarks ---"
$PYTHON -c "
import asyncio, json, time

async def run():
    results = {}

    # Benchmark 1: Import time
    t0 = time.perf_counter()
    import jarvis
    results['import_time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
    print(f'Import time:        {results[\"import_time_ms\"]}ms')

    # Benchmark 2: App initialization
    from jarvis.app import JarvisApp
    t0 = time.perf_counter()
    app = JarvisApp()
    await app.initialize()
    results['init_time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
    print(f'Init time:          {results[\"init_time_ms\"]}ms')

    # Benchmark 3: Spec parsing (if available)
    try:
        from jarvis.spec.parser import SpecParser
        parser = SpecParser()
        sample = '''# Test Spec
## Steps
1. Do something
2. Do another thing
## Expected
- Result A
'''
        t0 = time.perf_counter()
        for _ in range($ITERATIONS):
            parser.parse(sample)
        elapsed = (time.perf_counter() - t0) * 1000
        results['spec_parse_avg_ms'] = round(elapsed / $ITERATIONS, 3)
        print(f'Spec parse avg:     {results[\"spec_parse_avg_ms\"]}ms ({$ITERATIONS} iterations)')
    except Exception as e:
        print(f'Spec parse:         skipped ({e})')

    # Benchmark 4: Router dispatch (if available)
    try:
        from jarvis.core.router import Router
        router = Router()
        t0 = time.perf_counter()
        for _ in range($ITERATIONS):
            router.route('test message')
        elapsed = (time.perf_counter() - t0) * 1000
        results['route_avg_ms'] = round(elapsed / $ITERATIONS, 3)
        print(f'Route dispatch avg: {results[\"route_avg_ms\"]}ms ({$ITERATIONS} iterations)')
    except Exception as e:
        print(f'Route dispatch:     skipped ({e})')

    # Write results
    with open('$RESULT_FILE', 'w') as f:
        json.dump({
            'timestamp': '$TIMESTAMP',
            'iterations': $ITERATIONS,
            'results': results
        }, f, indent=2)

    print(f'\nResults saved to $RESULT_FILE')

asyncio.run(run())
" 2>&1 || echo "Some benchmarks failed (this is expected if modules are not yet implemented)"

echo ""
echo "Benchmark run complete."
