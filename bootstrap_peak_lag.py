from pathlib import Path
from itertools import combinations
import numpy as np
from scipy.signal import correlate
import polars as pl

VENUES = ["binance", "bybit", "deribit", "okx"]
BASE_DIR = Path(__file__).resolve().parent
PANEL_DIR = BASE_DIR / "btc_lead_lag_panel" / "timestamp"
OUT_PATH = BASE_DIR / "bootstrap_peak_lag.parquet"

GRID_STEP_MS = 100
MAX_LAG_STEPS = 50          # +/- 5 seconds, same window as compute_ccf.py
N_RESAMPLES = 200
N_SAMPLE_DAYS = 61          # <-- change this to run on more/all days
SEED = 42

rng = np.random.default_rng(SEED)


def parabolic_refine(window_corr: np.ndarray, peak_idx: int) -> float:
    if peak_idx <= 0 or peak_idx >= len(window_corr) - 1:
        return 0.0
    y_left = window_corr[peak_idx - 1]
    y_center = window_corr[peak_idx]
    y_right = window_corr[peak_idx + 1]
    denom = (y_left - 2 * y_center + y_right)
    if denom == 0:
        return 0.0
    return 0.5 * (y_left - y_right) / denom


def peak_lag(x: np.ndarray, y: np.ndarray, max_lag: int) -> tuple[int, float]:
    n = len(x)
    xs = (x - x.mean()) / x.std()
    ys = (y - y.mean()) / y.std()
    full = correlate(xs, ys, mode="full", method="fft") / n
    lags = np.arange(-(n - 1), n)
    mask = (lags >= -max_lag) & (lags <= max_lag)
    window_corr = full[mask]
    window_lags = lags[mask]
    peak_idx = int(np.argmax(window_corr))
    grid_lag = int(window_lags[peak_idx])
    offset = parabolic_refine(window_corr, peak_idx)
    return grid_lag, grid_lag + offset


def block_bootstrap_peak_lags(x: np.ndarray, y: np.ndarray, block_len: int,
                               n_resamples: int, max_lag: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(x)
    n_blocks_needed = int(np.ceil(n / block_len))
    n_possible_starts = n - block_len + 1  # allow overlapping block start points

    grid_results = np.empty(n_resamples, dtype=np.int64)
    refined_results = np.empty(n_resamples, dtype=np.float64)
    for i in range(n_resamples):
        starts = rng.integers(0, n_possible_starts, size=n_blocks_needed)
        x_res = np.concatenate([x[s:s + block_len] for s in starts])[:n]
        y_res = np.concatenate([y[s:s + block_len] for s in starts])[:n]
        grid_results[i], refined_results[i] = peak_lag(x_res, y_res, max_lag)
    return grid_results, refined_results


def select_sample_dates(all_dates: list[str], n: int) -> list[str]:
    if n >= len(all_dates):
        return all_dates
    idx = np.linspace(0, len(all_dates) - 1, n).round().astype(int)
    return [all_dates[i] for i in sorted(set(idx))]


def process_day(path: Path) -> list[dict]:
    date_str = path.stem
    df = pl.read_parquet(path)
    complete = df.filter(pl.all_horizontal(pl.col(VENUES).is_not_null()))
    returns = complete.select(
        [(pl.col(v).log().diff()).alias(v) for v in VENUES]
    ).drop_nulls()

    rows = []
    for venue_a, venue_b in combinations(VENUES, 2):
        x = returns[venue_a].to_numpy()
        y = returns[venue_b].to_numpy()

        block_len = 100

        real_grid_peak, real_refined_peak = peak_lag(x, y, MAX_LAG_STEPS)
        boot_grid_lags, boot_refined_lags = block_bootstrap_peak_lags(
            x, y, block_len, N_RESAMPLES, MAX_LAG_STEPS
        )

        ci_low, ci_high = np.percentile(boot_grid_lags, [2.5, 97.5])
        ci_low_ref, ci_high_ref = np.percentile(boot_refined_lags, [2.5, 97.5])
        rows.append({
            "date": date_str, "venue_a": venue_a, "venue_b": venue_b,
            "block_len_steps": block_len, "block_len_ms": block_len * GRID_STEP_MS,
            "real_peak_lag_ms": real_grid_peak * GRID_STEP_MS,
            "real_refined_lag_ms": real_refined_peak * GRID_STEP_MS,
            "boot_median_lag_ms": float(np.median(boot_grid_lags)) * GRID_STEP_MS,
            "boot_median_refined_lag_ms": float(np.median(boot_refined_lags)) * GRID_STEP_MS,
            "ci_low_ms": float(ci_low) * GRID_STEP_MS,
            "ci_high_ms": float(ci_high) * GRID_STEP_MS,
            "ci_low_refined_ms": float(ci_low_ref) * GRID_STEP_MS,
            "ci_high_refined_ms": float(ci_high_ref) * GRID_STEP_MS,
            "ci_includes_zero": bool(ci_low <= 0 <= ci_high),
        })
        print(f"    {venue_a}-{venue_b}: block_len={block_len} steps "
              f"({block_len * GRID_STEP_MS}ms), real_peak={real_grid_peak * GRID_STEP_MS}ms "
              f"(refined={real_refined_peak * GRID_STEP_MS:.1f}ms), "
              f"CI=[{ci_low * GRID_STEP_MS:.0f}, {ci_high * GRID_STEP_MS:.0f}]ms "
              f"(refined CI=[{ci_low_ref * GRID_STEP_MS:.1f}, {ci_high_ref * GRID_STEP_MS:.1f}]ms)")

    return rows


def main():
    panel_files = sorted(PANEL_DIR.glob("*.parquet"))
    if not panel_files:
        print(f"No panel files found in {PANEL_DIR}.")
        return

    all_dates = [p.stem for p in panel_files]
    sample_dates = select_sample_dates(all_dates, N_SAMPLE_DAYS)
    print(f"Bootstrapping {N_RESAMPLES} resamples/pair on {len(sample_dates)} "
          f"of {len(all_dates)} available day(s): {sample_dates}\n")

    all_rows = []
    for date_str in sample_dates:
        path = PANEL_DIR / f"{date_str}.parquet"
        print(f"  {date_str}:")
        all_rows.extend(process_day(path))

    result = pl.DataFrame(all_rows).sort(["venue_a", "venue_b", "date"])
    result.write_parquet(OUT_PATH)
    print(f"\nWrote {result.height} rows to {OUT_PATH}\n")

    summary = (
        result.group_by(["venue_a", "venue_b"])
        .agg([
            pl.col("real_peak_lag_ms").median(),
            pl.col("real_refined_lag_ms").median(),
            pl.col("ci_low_ms").median().alias("median_ci_low_ms"),
            pl.col("ci_high_ms").median().alias("median_ci_high_ms"),
            pl.col("ci_low_refined_ms").median().alias("median_ci_low_refined_ms"),
            pl.col("ci_high_refined_ms").median().alias("median_ci_high_refined_ms"),
            pl.col("ci_includes_zero").mean().alias("frac_days_ci_includes_zero"),
            pl.col("block_len_ms").median().alias("median_block_len_ms"),
        ])
        .sort(["venue_a", "venue_b"])
    )
    print(summary)


if __name__ == "__main__":
    main()