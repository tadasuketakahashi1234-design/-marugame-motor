This is the FIRST data-validation stage, NOT a complete prediction model.
Upload omura_data_audit.py to repo root.
Upload .github/workflows/omura_data_audit.yml to same path.
Then GitHub Actions -> Audit Omura prediction data -> Run workflow.
Inspect omura/docs/data_audit.json for actual schemas and unavailable datasets.
It checks live availability of race cards, motor histories, exhibition, weather, odds, results and payouts.
It does NOT yet include tide data, model training, leakage-safe backtesting, or ROI.
