from pathlib import Path
import polars as pl

BASE_DIR = Path(__file__).resolve().parent
TS_COL = "timestamp"
IN_PATH = BASE_DIR / f"placebo_results_{TS_COL}.parquet"
OUT_PATH = BASE_DIR / f"placebo_summary_{TS_COL}.parquet"


def main():
    if not IN_PATH.exists():
        print(f"{IN_PATH} not found -- run placebo_ccf.py first.")
        return

    r = pl.read_parquet(IN_PATH).with_columns(
        pl.col("peak_corr").abs().alias("abs_peak_corr")
    )

    real = (
        r.filter(pl.col("shift_idx") == 0)
        .select(["date", "venue_a", "venue_b", "abs_peak_corr"])
        .rename({"abs_peak_corr": "real_abs_corr"})
    )

    nulls = r.filter(pl.col("shift_idx") > 0)

    null_stats = nulls.group_by(["date", "venue_a", "venue_b"]).agg([
        pl.col("abs_peak_corr").mean().alias("null_mean"),
        pl.col("abs_peak_corr").std().alias("null_std"),
        pl.len().alias("n_nulls"),
    ])

    day_level = real.join(null_stats, on=["date", "venue_a", "venue_b"], how="inner")

    joined_nulls = nulls.join(real, on=["date", "venue_a", "venue_b"], how="inner")
    percentile = (
        joined_nulls.with_columns(
            (pl.col("abs_peak_corr") <= pl.col("real_abs_corr")).alias("le_real")
        )
        .group_by(["date", "venue_a", "venue_b"])
        .agg((pl.col("le_real").sum() / pl.len() * 100).alias("percentile"))
    )

    day_level = day_level.join(percentile, on=["date", "venue_a", "venue_b"], how="inner")
    day_level = day_level.with_columns(
        ((pl.col("real_abs_corr") - pl.col("null_mean")) / pl.col("null_std")).alias("z_score"),
        (pl.col("percentile") == 100.0).alias("beat_all_nulls"),
    )

    day_level.write_parquet(OUT_PATH)

    summary = (
        day_level.group_by(["venue_a", "venue_b"])
        .agg([
            pl.col("real_abs_corr").median().alias("median_real_corr"),
            pl.col("percentile").median().alias("median_percentile"),
            pl.col("percentile").min().alias("worst_day_percentile"),
            pl.col("z_score").median().alias("median_z_score"),
            pl.col("beat_all_nulls").mean().alias("frac_days_beat_all_nulls"),
            pl.len().alias("n_days"),
        ])
        .sort(["venue_a", "venue_b"])
    )

    print(f"Wrote day-level placebo summary ({day_level.height} rows) to {OUT_PATH}\n")
    print(summary)


if __name__ == "__main__":
    main()