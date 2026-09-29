from pathlib import Path
import polars as pl

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "btc_lead_lag_clean" / "deribit" / "book_snapshot_5"
OUT_DIR = BASE_DIR / "btc_lead_lag_clean_thinned" / "deribit" / "book_snapshot_5"

THIN_WINDOW_US = 52_000  # ~Binance's median update gap, in microseconds


def thin_file(path: Path, out_path: Path):
    df = pl.read_parquet(path)
    df = df.with_columns((pl.col("timestamp") // THIN_WINDOW_US).alias("_bin"))
    df = df.sort("timestamp").group_by("_bin", maintain_order=True).last()
    df = df.drop("_bin").sort("timestamp")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path)
    return df.height


def main():
    files = sorted(SRC_DIR.glob("*.parquet"))
    if not files:
        print(f"No files found in {SRC_DIR}.")
        return

    for f in files:
        n = thin_file(f, OUT_DIR / f.name)
        print(f"OK   {f.name}: thinned to {n} rows")

    print(f"\nThinned {len(files)} file(s) to {OUT_DIR}")


if __name__ == "__main__":
    main()