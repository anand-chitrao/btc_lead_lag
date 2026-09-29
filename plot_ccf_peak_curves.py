from pathlib import Path
import polars as pl
import matplotlib.pyplot as plt
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
NATIVE_PATH = BASE_DIR / "ccf_results_timestamp.parquet"
THINNED_PATH = BASE_DIR / "ccf_results_thinned.parquet"
OUT_PATH = BASE_DIR / "ccf_peak_curves.png"

WINDOW_MS = 500  # plot range: +/- this many ms around 0



def pair_median_curve(df: pl.DataFrame, venue_a: str, venue_b: str) -> pl.DataFrame:
    sub = df.filter(
        (pl.col("venue_a") == venue_a) & (pl.col("venue_b") == venue_b)
        & (pl.col("lag_ms").abs() <= WINDOW_MS)
    )
    if sub.height == 0:
        raise ValueError(f"No rows found for pair {venue_a}-{venue_b} in this file.")
    return (
        sub.group_by("lag_ms")
        .agg([
            pl.col("corr").median().alias("median_corr"),
            pl.col("corr").quantile(0.25).alias("q25_corr"),
            pl.col("corr").quantile(0.75).alias("q75_corr"),
        ])
        .sort("lag_ms")
    )


def plot_curve(ax, curve: pl.DataFrame, label: str, color: str):
    lag = curve["lag_ms"].to_numpy()
    med = curve["median_corr"].to_numpy()
    q25 = curve["q25_corr"].to_numpy()
    q75 = curve["q75_corr"].to_numpy()
    ax.plot(lag, med, marker="o", label=label, color=color)
    ax.fill_between(lag, q25, q75, alpha=0.15, color=color)


def main():
    native = pl.read_parquet(NATIVE_PATH)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)

    # --- Binance-Bybit (native only) ---
    bb_curve = pair_median_curve(native, "binance", "bybit")
    plot_curve(axes[0], bb_curve, "Binance-Bybit (native)", "tab:blue")
    axes[0].axvline(0, color="gray", linestyle="--", linewidth=0.8)
    axes[0].set_title("Binance-Bybit")
    axes[0].set_xlabel("Lag (ms)")
    axes[0].set_ylabel("Correlation (median across days, IQR band)")
    axes[0].legend()

    # --- Binance-Deribit (native + thinned overlay) ---
    bd_curve = pair_median_curve(native, "binance", "deribit")
    plot_curve(axes[1], bd_curve, "Binance-Deribit (native)", "tab:orange")

    if THINNED_PATH.exists():
        thinned = pl.read_parquet(THINNED_PATH)
        bd_thinned_curve = pair_median_curve(thinned, "binance", "deribit")
        plot_curve(axes[1], bd_thinned_curve, "Binance-Deribit (thinned)", "tab:green")
    else:
        print(f"Note: {THINNED_PATH} not found, skipping thinned overlay.")

    axes[1].axvline(0, color="gray", linestyle="--", linewidth=0.8)
    axes[1].set_title("Binance-Deribit: native vs. thinned")
    axes[1].set_xlabel("Lag (ms)")
    axes[1].legend()

    ticks = np.arange(-500, 501, 100) 
    axes[0].set_xticks(ticks)
    axes[1].set_xticks(ticks)

    fig.suptitle(f"CCF curves near peak (\u00b1{WINDOW_MS}ms window)")
    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=150)
    print(f"Saved plot to {OUT_PATH.resolve()}")
    plt.show()


if __name__ == "__main__":
    main()