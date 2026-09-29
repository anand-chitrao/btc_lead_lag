from pathlib import Path
import polars as pl

VENUES = ["binance", "bybit", "deribit", "okx"]
BASE_DIR = Path(__file__).resolve().parent
CLEAN_ROOT = BASE_DIR / "btc_lead_lag_clean"
THINNED_ROOT = BASE_DIR / "btc_lead_lag_clean_thinned"
PANEL_ROOT = BASE_DIR / "btc_lead_lag_panel_thinned"

GRID_STEP_MS = 100
MAX_STALENESS_MS = 5000
PRICE_COL = "mid_price"
TS_COL = "timestamp"


def venue_root(venue: str) -> Path:
    root = THINNED_ROOT if venue == "deribit" else CLEAN_ROOT
    return root / venue / "book_snapshot_5"


def available_dates_per_venue() -> dict:
    dates = {}
    for ven in VENUES:
        d = venue_root(ven)
        dates[ven] = {p.stem for p in d.glob("*.parquet")} if d.exists() else set()
    return dates


def common_dates(dates_per_venue: dict) -> list:
    sets = list(dates_per_venue.values())
    return sorted(set.intersection(*sets))


def load_price_series(venue: str, date_str: str) -> pl.DataFrame:
    path = venue_root(venue) / f"{date_str}.parquet"
    df = pl.read_parquet(path, columns=[TS_COL, PRICE_COL])
    df = df.rename({TS_COL: f"{venue}_time", PRICE_COL: venue})
    df = df.with_columns(
        pl.from_epoch(f"{venue}_time", time_unit="us").alias(f"{venue}_time")
    )
    return df.sort(f"{venue}_time").unique(subset=[f"{venue}_time"], keep="last")


def build_day_panel(date_str: str) -> pl.DataFrame:
    y, m, d = int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10])
    day_start = pl.datetime(y, m, d, 0, 0, 0)
    day_end = day_start + pl.duration(days=1)

    panel = pl.DataFrame({
        "time": pl.datetime_range(
            day_start, day_end, interval=f"{GRID_STEP_MS}ms", eager=True, closed="left"
        )
    })

    for ven in VENUES:
        series = load_price_series(ven, date_str)
        panel = panel.join_asof(
            series, left_on="time", right_on=f"{ven}_time",
            strategy="backward", tolerance=f"{MAX_STALENESS_MS}ms",
        )
        panel = panel.drop(f"{ven}_time")

    return panel


def main():
    dates_per_venue = available_dates_per_venue()
    dates = common_dates(dates_per_venue)

    all_seen = set().union(*dates_per_venue.values())
    skipped = sorted(all_seen - set(dates))
    if skipped:
        print(f"Skipping {len(skipped)} date(s) missing from at least one venue: {skipped}")

    print(f"Building thinned panel for {len(dates)} common date(s), TS_COL={TS_COL}, grid={GRID_STEP_MS}ms")

    out_dir = PANEL_ROOT / TS_COL
    out_dir.mkdir(parents=True, exist_ok=True)

    for date_str in dates:
        try:
            panel = build_day_panel(date_str)
            panel.write_parquet(out_dir / f"{date_str}.parquet")
            n_complete = panel.select(pl.all_horizontal(pl.col(VENUES).is_not_null())).sum().item()
            print(f"OK   {date_str}: {panel.height} grid points, {n_complete} fully-populated across all 4 venues")
        except Exception as e:
            print(f"FAIL {date_str}: {e}")


if __name__ == "__main__":
    main()