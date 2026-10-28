# ProPublica Nonprofit Explorer data

This directory is intentionally separate from the IRS EO BMF source files.
ProPublica records are joined to IRS records by the nine-digit EIN.

Generated contents:

- `raw/<EIN>.json` — unmodified response from the organization-detail endpoint.
- `fetch-manifest.jsonl` — timestamped request successes and failures.
- `irs-propublica-comparison.csv` — field-by-field comparison produced by the analyzer.
- `analysis-summary.json` — aggregate agreement, field-presence, and form-type counts.

Run a small research sample:

```powershell
python scripts/fetch_propublica_nonprofits.py --per-ntee 2
python scripts/analyze_propublica_categories.py
```

Reproduce the two live spot checks documented in the crosswalk:

```powershell
python scripts/fetch_propublica_nonprofits.py --eins 20-2860877 20-3140552
python scripts/analyze_propublica_categories.py
```

Run all EINs after reviewing the sample:

```powershell
python scripts/fetch_propublica_nonprofits.py --all
python scripts/analyze_propublica_categories.py
```

Existing valid response files are skipped. Use `--refresh` only when the cached
API response should be replaced. No ProPublica API key is required by the
documented v2 API.

The raw API cache can be large and contains public tax-filing information. A
deployment should publish only the derived fields actually needed by the map.
