import polars as pl

SYMBOL_MAP = {
    "BTCUSDT": "BTC-PERP",          # binance, bybit
    "BTC-USDT-SWAP": "BTC-PERP",    # okx
    "BTC-PERPETUAL": "BTC-PERP",    # deribit (inverse/coin-margined; others are linear/USDT)
}

BOOK_LEVEL_COLS = [
    f"{side}[{lvl}].{field}"
    for side in ("bids", "asks")
    for lvl in range(5)
    for field in ("price", "amount")
]


def clean_book_file(input_path, output_path) -> dict:
    df = pl.read_parquet(input_path)
    n_raw = df.height

    # cheap sanity checks -- catch a mislabeled/misplaced file early
    present_symbols = set(df.get_column("symbol").unique().to_list())
    unmapped = present_symbols - set(SYMBOL_MAP.keys())
    if unmapped:
        raise ValueError(f"{input_path.name}: unexpected symbol(s) {unmapped}")
    missing_cols = [c for c in BOOK_LEVEL_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"{input_path.name}: missing columns {missing_cols}")

    df = df.with_columns(pl.col("symbol").replace(SYMBOL_MAP).alias("symbol_common"))

    # content dedup
    df = df.with_columns((pl.col("local_timestamp") >= pl.col("timestamp")).alias("_sane"))
    n_bad_ts = n_raw - int(df.get_column("_sane").sum())  # count only, not kept as a column

    df = df.sort(["_sane", "local_timestamp"], descending=[True, False])
    df = df.unique(subset=["timestamp"] + BOOK_LEVEL_COLS, keep="first", maintain_order=True)
    n_content_dupes_dropped = n_raw - df.height

    n_before_full = df.height
    df = df.unique(maintain_order=True)
    df = df.drop("_sane")
    n_full_dupes_dropped = n_before_full - df.height

    # mid / micro price from level-0 book
    df = df.with_columns(
        ((pl.col("bids[0].price") + pl.col("asks[0].price")) / 2).alias("mid_price")
    )
    df = df.with_columns(
        (
            (pl.col("bids[0].price") * pl.col("asks[0].amount")
             + pl.col("asks[0].price") * pl.col("bids[0].amount"))
            / (pl.col("bids[0].amount") + pl.col("asks[0].amount"))
        ).alias("micro_price")
    )

    df = df.sort("timestamp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(output_path)

    return {
        "n_raw": n_raw,
        "n_content_dupes_dropped": n_content_dupes_dropped,
        "n_full_dupes_dropped": n_full_dupes_dropped,
        "n_bad_ts": n_bad_ts,
        "n_final": df.height,
    }