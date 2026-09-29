# Determining Lead/Lag Relationship Between BTC Perpetual Prices on Binance, Bybit, OKX, and Deribit.

## Summary

This project determines if there is a lead or lag relationship between the prices of BTC perpetuals on the 4 venues: Binance, Bybit, OKX, and Deribit. Whenever there is a lead or a lag, we also quantify how strong the lead or the lag is. We assess the stability of our result over time and show that the results are genuine and not an artifact of the data or the methodology.

The following table gives a summary of the lead/lag relationships:
```text
┌─────────┬─────────┬───────────────┐
│ venue_a ┆ venue_b ┆ median_lag_ms │
╞═════════╪═════════╪═══════════════╡
│ binance ┆ bybit   ┆ 3.166761      │
│ binance ┆ deribit ┆ -63.744664    │
│ binance ┆ okx     ┆ 12.275615     │
│ bybit   ┆ deribit ┆ -78.066913    │
│ bybit   ┆ okx     ┆ 8.405617      │
│ deribit ┆ okx     ┆ 93.281687     │
└─────────┴─────────┴───────────────┘
```
From the third column in the table above, we see that Deribit lags behind Binance, Bybit, and OKX. We also see that there is no significant lead or lag relationship between Binance, Bybit, and OKX. 

The Deribit-OKX relationship was the strongest. It proved robust across 4 of the 5 tests we conducted. 

The Deribit-Bybit relationship was weaker than the Deribit-OKX relationship, holding up in only 3 of the 5 robustness tests. Its failure in the remaining tests is likely explained by the large gap between the Bybit venue's exchange timestamps and its data-collection timestamps.

The Deribit-Binance relationship, by contrast, was more robust, passing 4 of the 5 tests. Where it failed, this can be attributed to Binance's book update frequency, which is roughly 16.4x slower (in median) than Deribit's.

Our method of determining these six lead/lag relationships, their strength, and robustness checks using 5 tests are explained in detail in [Report.md](Report.md).

## Reproducing the reports

We list down the scrips in order to produce the reports and the files necessary to produce the reports:
1. Files in "btc_lead_lag_clean/": `python3 run_pipeline.py`. Requires "btc_lead_lag/" and clean_books.py.
2. Files in "btc_lead_lag_clean_thinned/": `python3 thin_deribit.py`. Requires "btc_lead_lag_clean/deribit/book_snapshot_5/".
3. Files in "btc_lead_lag_panel/local_timestamp/" and "btc_lead_lag_panel/_panel_report_local_timestamp.csv": `python3 build_panel.py` with `TS_COL = "local_timestamp"`. Requires "btc_lead_lag_clean".
4. Files in "btc_lead_lag_panel/timestamp/" and "btc_lead_lag_panel/_panel_report_timestamp.csv": `python3 build_panel.py` with `TS_COL = "timestamp"`. Requires "btc_lead_lag_clean".
5. Files in "btc_lead_lag_panel_thinned/": `python3 build_panel_thinned.py`. Requires "btc_lead_lag_clean" and "btc_lead_lag_clean_thinned".
6. "bootstrap_peak_lag.parquet": `python3 bootstrap_peak_lag.py`. Requires "btc_lead_lag_panel/timestamp".
7. "ccf_peak_curves.png": `python3 plot_ccf_peak_curves.py`. Requires "ccf_results_timestamp.parquet" and "ccf_results_thinned.parquet".
8. "ccf_results_local_timestamp.parquet": `python3 compute_ccf.py` with TS_COL = "local_timestamp". Requires "btc_lead_lag_panel/local_timestamp".
9. "ccf_results_thinned.parquet": `python3 compute_ccf_thinned.py`. Requires "btc_lead_lag_panel_thinned/timestamp".
10. "ccf_results_timestamp.parquet": `python3 compute_ccf.py` with TS_COL = "timestamp". Requires "btc_lead_lag_panel/timestamp".
11. "peak_sharpness_thinned.parquet": `python3 peak_sharpness.py` with IN_PATH = BASE_DIR / "ccf_results_thinned.parquet" OUT_PATH = BASE_DIR / "peak_sharpness_thinned.parquet". Requires "ccf_results_thinned.parquet".
12. "peak_sharpness_timestamp.parquet": `python3 peak_sharpness.py` with TS_COL = "timestamp". Requires "ccf_results_timestamp.parquet".
13. "placebo_results_timestamp.parquet": `python3 placebo_ccf.py`. Requires "btc_lead_lag_panel/timestamp".
14. "placebo_summary_timestamp.parquet": `python3 summarize_placebo.py`. Requires "placebo_results_timestamp.parquet".

## Repo structure
Here is the structure of the local repository. Since the folders btc_lead_lag/, btc_lead_lag_clean/, btc_lead_lag_clean_thinned, btc_lead_lag_panel/, and btc_lead_lag_panel_thinned/ contain raw or processed data files, we are not ignoring those folders while pushing to the GitHub repository.

```yaml
lead_lag_BTC_prices/
├── btc_lead_lag/                               # Raw order book data
|   ├── binance/                                                    
|   |   └── book_snapshot_5/                           
│   ├── bybit/                                                     
|   |   └── book_snapshot_5/                              
│   ├── deribit/
|   |   └── book_snapshot_5/                      
│   └── okx/
|       └── book_snapshot_5/                     
├── btc_lead_lag_clean/                         # De-duped and feature extracted data files
|   ├── binance/                  
|   |   └── book_snapshot_5/
│   ├── bybit/                                                     
|   |   └── book_snapshot_5/
│   ├── deribit/                                          
|   |   └── book_snapshot_5/
│   ├── okx/                  
|   |   └── book_snapshot_5/
|   └── _cleaning_report.csv                    # A report generated by the cleaning script
├── btc_lead_lag_clean_thinned/                 # Deribit order book thinned
|   └── deribit/
|       └── book_snapshot_5/
├── btc_lead_lag_panel/                         # Date-wise collection of data from all venues
|   ├── local_timestamp/
|   ├── timestamp/
|   ├── _panel_report_local_timestamp.csv       
|   └── _panel_report_timestamp.csv
├── btc_lead_lag_panel_thinned/                 # Replacing Deribit's raw data by thinned data
|   └── timestamp/                              
├── bootstrap_peak_lag.parquet                  # Per-day/pair bootstrap CIs for peak lag (grid & refined)
├── bootstrap_peak_lag.py                       # Batch bootstrapping script with parabolic refinement
├── build_panel.py                              # Combines all venues' per day mid-prices, 100 ms grid
├── build_panel_thinned.py                      # Same as above, uses Deribit's thinned book
├── ccf_peak_curves.png                         # Near-peak ccf curves: Binance-Bybit, Binance-Deribit
├── ccf_results_local_timestamp.parquet         # Per-pair ccf curves, uses timestamps recorded by collector
├── ccf_results_thinned.parquet                 # Per-pair ccf curves, uses thinned Deribit order book
├── ccf_results_timestamp.parquet               # Per-pair ccf curves, native 100 ms grid
├── clean_books.py                              # De-dupes order books
├── compute_ccf.py                              # Computes the ccf on regular panel data
├── compute_ccf_thinned.py                      # Computes the ccf on thinned panel data
├── download_all.py                             # Data fetching script, provided by Teesta                  
├── peak_sharpness.py                           # Peak-vs-zero and peak-vs-neighbor drop metrics
├── peak_sharpness_timestamp.parquet
├── peak_sharpness_thinned.parquet
├── placebo_ccf.py                              # Compares real ccf peaks against noise
├── placebo_results_timestamp.parquet
├── placebo_summary_timestamp.parquet           # Real peak vs null distribution, summary per pair
├── plot_ccf_peak_curves.py                     # Plots near-peak CCF curves (native & thinned)
├── README.md
├── Report.md
├── requirements.txt                            # Library requirements
├── run_pipeline.py                             # Initiates cleaning process
├── summarize_placebo.py                        # Summary for the comparison between real peaks and noise
└── thin_deribit.py                             # Thins Deribit's order book to ~52 ms
```