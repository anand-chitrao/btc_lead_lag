from pathlib import Path
from itertools import combinations
import numpy as np
from scipy.signal import correlate
import polars as pl

VENUES = ["binance", "bybit", "deribit", "okx"]
BASE_DIR = Path(__file__).resolve().parent
TS_COL = "timestamp"
PANEL_DIR = BASE_DIR / "btc_lead_lag_panel" / TS_COL
OUT_PATH = BASE_DIR / f"ccf_results_{TS_COL}.parquet"

GRID_STEP_MS = 100
MAX_LAG_STEPS = 50  # +/- 5 seconds at 100ms grid


def ccf_fft(x: np.ndarray, y: np.ndarray, max_lag: int) -> np.ndarray:
    n = len(x)
    xs = (x - x.mean()) / x.std()
    ys = (y - y.mean()) / y.std()

    full = correlate(xs, ys, mode="full", method="fft")
    lags = np.arange(-(n - 1), n)

    mask = (lags >= -max_lag) & (lags <= max_lag)
    return full[mask] / n


def process_day(path: Path) -> pl.DataFrame:
    date_str = path.stem
    df = pl.read_parquet(path)

    complete = df.filter(pl.all_horizontal(pl.col(VENUES).is_not_null()))
    returns = complete.select(
        [(pl.col(v).log().diff()).alias(v) for v in VENUES]
    ).drop_nulls()

    rows = []
    for a, b in combinations(VENUES, 2):
        x = returns[a].to_numpy()
        y = returns[b].to_numpy()
        corrs = ccf_fft(x, y, MAX_LAG_STEPS)
        lag_steps = np.arange(-MAX_LAG_STEPS, MAX_LAG_STEPS + 1)
        rows.append(pl.DataFrame({
            "date": [date_str] * len(lag_steps),
            "venue_a": [a] * len(lag_steps),
            "venue_b": [b] * len(lag_steps),
            "lag_steps": lag_steps,
            "lag_ms": lag_steps * GRID_STEP_MS,
            "corr": corrs,
        }))
    return pl.concat(rows, how="vertical")


def main():
    panel_files = sorted(PANEL_DIR.glob("*.parquet"))
    if not panel_files:
        print(f"No panel files found in {PANEL_DIR}.")
        return

    print(f"Computing CCF for {len(panel_files)} day(s)...")
    all_days = []
    for path in panel_files:
        try:
            day_result = process_day(path)
            all_days.append(day_result)
            print(f"OK   {path.stem}")
        except Exception as e:
            print(f"FAIL {path.stem}: {e}")

    result = pl.concat(all_days, how="vertical")
    result.write_parquet(OUT_PATH)
    print(f"\nWrote {result.height} rows ({len(panel_files)} days x 6 pairs x 101 lags) to {OUT_PATH}")


if __name__ == "__main__":
    main()