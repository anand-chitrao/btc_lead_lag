from pathlib import Path
import polars as pl

from clean_books import clean_book_file

VENUES = ["binance", "bybit", "deribit", "okx"]
BASE_DIR = Path(__file__).resolve().parent
RAW_ROOT = BASE_DIR / "btc_lead_lag"
CLEAN_ROOT = BASE_DIR / "btc_lead_lag_clean"
REPORT_PATH = CLEAN_ROOT / "_cleaning_report.csv"


def find_jobs():
    """Return list of (data_type, venue, raw_path, clean_path) for every
    raw file currently on disk."""
    jobs = []
    for venue in VENUES:
        for data_type, subfolder, cleaner in [
            ("book", "book_snapshot_5", clean_book_file),
        ]:
            raw_dir = RAW_ROOT / venue / subfolder
            if not raw_dir.exists():
                continue
            for raw_path in sorted(raw_dir.glob("*.parquet")):
                clean_path = CLEAN_ROOT / venue / subfolder / raw_path.name
                jobs.append((data_type, venue, raw_path, clean_path, cleaner))
    return jobs


def load_existing_report():
    if REPORT_PATH.exists():
        return pl.read_csv(REPORT_PATH)
    return None


def main():
    jobs = find_jobs()
    if not jobs:
        print(f"No raw files found under {RAW_ROOT}. Nothing to do.")
        return

    print(f"Found {len(jobs)} raw files to clean.")

    new_rows = []
    for data_type, venue, raw_path, clean_path, cleaner in jobs:
        try:
            stats = cleaner(raw_path, clean_path)
            row = {"data_type": data_type, "venue": venue, "file": raw_path.name, **stats}
            new_rows.append(row)
            print(f"OK   [{data_type:5s}] {venue:8s} {raw_path.name}: {stats}")
        except Exception as e:
            print(f"FAIL [{data_type:5s}] {venue:8s} {raw_path.name}: {e}")

    if not new_rows:
        print("No files were successfully cleaned this run.")
        return

    new_report = pl.DataFrame(new_rows)

    # merge with any existing report from a previous (partial) run:
    # drop old rows for (data_type, venue, file) keys we just reprocessed,
    # then append the fresh ones -- so re-running never leaves stale entries.
    existing = load_existing_report()
    if existing is not None:
        key_cols = ["data_type", "venue", "file"]
        new_keys = new_report.select(key_cols)
        existing = existing.join(new_keys, on=key_cols, how="anti")
        combined = pl.concat([existing, new_report], how="vertical")
    else:
        combined = new_report

    CLEAN_ROOT.mkdir(parents=True, exist_ok=True)
    combined.write_csv(REPORT_PATH)
    print(f"\nCleaned {len(new_rows)} files this run. Full report ({combined.height} files total) at {REPORT_PATH}")


if __name__ == "__main__":
    main()