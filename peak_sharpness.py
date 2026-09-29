from pathlib import Path
import polars as pl

BASE_DIR = Path(__file__).resolve().parent
TS_COL = "timestamp"
IN_PATH = BASE_DIR / f"ccf_results_{TS_COL}.parquet"
OUT_PATH = BASE_DIR / f"peak_sharpness_{TS_COL}.parquet"
# IN_PATH = BASE_DIR / "ccf_results_thinned.parquet"                  # Use this for the thinned part of the test
# OUT_PATH = BASE_DIR / "peak_sharpness_thinned.parquet"

GRID_STEP_MS = 100


def process_pair_day(df: pl.DataFrame) -> dict:
    peak_row = df.sort("corr", descending=True).head(1)
    peak_lag_ms = peak_row["lag_ms"].item()
    peak_corr = peak_row["corr"].item()

    zero_row = df.filter(pl.col("lag_ms") == 0)
    corr_at_zero = zero_row["corr"].item() if zero_row.height == 1 else None

    left = df.filter(pl.col("lag_ms") == peak_lag_ms - GRID_STEP_MS)
    right = df.filter(pl.col("lag_ms") == peak_lag_ms + GRID_STEP_MS)
    neighbor_corrs = []
    if left.height == 1:
        neighbor_corrs.append(left["corr"].item())
    if right.height == 1:
        neighbor_corrs.append(right["corr"].item())
    neighbor_avg_corr = sum(neighbor_corrs) / len(neighbor_corrs) if neighbor_corrs else None

    drop_to_zero = peak_corr - corr_at_zero if corr_at_zero is not None else None
    drop_to_neighbor = peak_corr - neighbor_avg_corr if neighbor_avg_corr is not None else None

    return {
        "peak_lag_ms": peak_lag_ms,
        "peak_corr": peak_corr,
        "corr_at_zero": corr_at_zero,
        "neighbor_avg_corr": neighbor_avg_corr,
        "drop_to_zero_abs": drop_to_zero,
        "drop_to_zero_rel": (drop_to_zero / peak_corr) if (drop_to_zero is not None and peak_corr) else None,
        "drop_to_neighbor_abs": drop_to_neighbor,
        "drop_to_neighbor_rel": (drop_to_neighbor / peak_corr) if (drop_to_neighbor is not None and peak_corr) else None,
    }


def main():
    if not IN_PATH.exists():
        print(f"{IN_PATH} not found -- run compute_ccf.py first.")
        return

    r = pl.read_parquet(IN_PATH)

    rows = []
    for (date, venue_a, venue_b), df in r.group_by(["date", "venue_a", "venue_b"]):
        stats = process_pair_day(df)
        rows.append({"date": date, "venue_a": venue_a, "venue_b": venue_b, **stats})

    result = pl.DataFrame(rows).sort(["venue_a", "venue_b", "date"])
    result.write_parquet(OUT_PATH)
    print(f"Wrote {result.height} rows to {OUT_PATH}\n")

    summary = (
        result.group_by(["venue_a", "venue_b"])
        .agg([
            pl.col("peak_lag_ms").median().alias("median_peak_lag_ms"),
            pl.col("peak_corr").median().alias("median_peak_corr"),
            pl.col("drop_to_zero_abs").median().alias("median_drop_to_zero_abs"),
            pl.col("drop_to_zero_rel").median().alias("median_drop_to_zero_rel"),
            pl.col("drop_to_neighbor_abs").median().alias("median_drop_to_neighbor_abs"),
            pl.col("drop_to_neighbor_rel").median().alias("median_drop_to_neighbor_rel"),
        ])
        .sort(["venue_a", "venue_b"])
    )
    print(summary)


if __name__ == "__main__":
    main()