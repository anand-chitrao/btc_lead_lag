from pathlib import Path
from itertools import combinations
import numpy as np
from scipy.signal import correlate
import polars as pl

VENUES = ["binance", "bybit", "deribit", "okx"]
BASE_DIR = Path(__file__).resolve().parent
TS_COL = "timestamp"
PANEL_DIR = BASE_DIR / "btc_lead_lag_panel" / TS_COL
OUT_PATH = BASE_DIR / f"placebo_results_{TS_COL}.parquet"

GRID_STEP_MS = 100
MAX_LAG_STEPS = 50           # +/- 5 seconds, same window as compute_ccf.py
N_SHIFTS = 20                # random misalignments per pair per day
MIN_OFFSET_STEPS = 500       # >= 50s, well clear of the +/-5s real lag window
SEED = 42                    # fixed for reproducibility; change/remove to re-randomize

rng = np.random.default_rng(SEED)


def peak_ccf(x: np.ndarray, y: np.ndarray, max_lag: int) -> tuple[int, float]:
    n = len(x)
    x_std, y_std = x.std(), y.std()
    if x_std == 0 or y_std == 0:
        return None  
    xs = (x - x.mean()) / x_std
    ys = (y - y.mean()) / y_std

    full = correlate(xs, ys, mode="full", method="fft") / n
    lags = np.arange(-(n - 1), n)

    mask = (lags >= -max_lag) & (lags <= max_lag)
    window_corr = full[mask]
    window_lags = lags[mask]

    peak_idx = np.argmax(np.abs(window_corr))
    return int(window_lags[peak_idx]), float(window_corr[peak_idx])


def truncated_shift(a: np.ndarray, b: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    if k > 0:
        return a[:-k], b[k:]
    elif k < 0:
        kk = -k
        return a[kk:], b[:-kk]
    return a, b


def process_day(path: Path) -> pl.DataFrame:
    date_str = path.stem
    df = pl.read_parquet(path)

    complete = df.filter(pl.all_horizontal(pl.col(VENUES).is_not_null()))
    returns = complete.select(
        [(pl.col(v).log().diff()).alias(v) for v in VENUES]
    ).drop_nulls()

    n_full = returns.height
    rows = []

    for venue_a, venue_b in combinations(VENUES, 2):
        x_full = returns[venue_a].to_numpy()
        y_full = returns[venue_b].to_numpy()

        result = peak_ccf(x_full, y_full, MAX_LAG_STEPS)
        if result is None:
            print(f"    SKIP {venue_a}-{venue_b}: zero-std on real (unshifted) series -- unexpected, investigate")
        else:
        # real, unshifted alignment
            lag_steps, corr = peak_ccf(x_full, y_full, MAX_LAG_STEPS)
            rows.append({
                "date": date_str, "venue_a": venue_a, "venue_b": venue_b,
                "shift_idx": 0, "offset_steps": 0,
                "peak_lag_ms": lag_steps * GRID_STEP_MS, "peak_corr": corr,
            })

        # random truncated-shift nulls
        max_offset = n_full - MIN_OFFSET_STEPS - 1
        if max_offset <= MIN_OFFSET_STEPS:
            continue  

        for shift_idx in range(1, N_SHIFTS + 1):
            magnitude = rng.integers(MIN_OFFSET_STEPS, max_offset + 1)
            sign = rng.choice([-1, 1])
            k = int(sign * magnitude)

            xa, yb = truncated_shift(x_full, y_full, k)
            result = peak_ccf(xa, yb, MAX_LAG_STEPS)
            if result is None:
                print(f"    SKIP {venue_a}-{venue_b} shift {shift_idx}: zero-std segment (offset={k})")
                continue
            lag_steps, corr = peak_ccf(xa, yb, MAX_LAG_STEPS)
            rows.append({
                "date": date_str, "venue_a": venue_a, "venue_b": venue_b,
                "shift_idx": shift_idx, "offset_steps": k,
                "peak_lag_ms": lag_steps * GRID_STEP_MS, "peak_corr": corr,
            })

    return pl.DataFrame(rows)


def main():
    panel_files = sorted(PANEL_DIR.glob("*.parquet"))
    if not panel_files:
        print(f"No panel files found in {PANEL_DIR}.")
        return

    print(f"Running placebo test ({N_SHIFTS} shifts/pair/day) for {len(panel_files)} day(s)...")
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
    print(f"\nWrote {result.height} rows to {OUT_PATH}")

    summary = (
        result.group_by(["venue_a", "venue_b", "shift_idx"])
        .agg(pl.col("peak_corr").median().alias("median_peak_corr"))
        .with_columns(
            pl.when(pl.col("shift_idx") == 0).then(pl.lit("real")).otherwise(pl.lit("null")).alias("kind")
        )
        .group_by(["venue_a", "venue_b", "kind"])
        .agg(pl.col("median_peak_corr").mean().alias("mean_of_medians"))
        .sort(["venue_a", "venue_b", "kind"])
    )
    print(summary)


if __name__ == "__main__":
    main()