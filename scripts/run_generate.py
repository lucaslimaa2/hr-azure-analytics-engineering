"""Generate ONE month's full-roster snapshot and land it in raw (the CI generate step).

This is what the Generate Azure Function would do on each run — executed here in
GitHub Actions instead, because the subscription can't host the Function. Auth to the
lake is via the service principal: on the runner, `DefaultAzureCredential` picks up the
AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID env vars (set from GitHub
Secrets) and authenticates as the `hr-github-actions` robot.

Usage:  python scripts/run_generate.py --year 2026 --month 6
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import date

# Make the Function's `shared/` package importable (same trick as land_months.py).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "functions"))

from shared.config import Config, gen_config_from_env  # noqa: E402
from shared.generate import generate_month  # noqa: E402
from shared.storage import RawAlreadyExistsError, Storage  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate one month's roster into raw.")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    args = ap.parse_args()

    run_month = date(args.year, args.month, 1)
    records = generate_month(args.year, args.month, gen_config_from_env())
    storage = Storage(Config.from_env())

    try:
        path = storage.write_raw(run_month, records)
        print(f"[ok] wrote {path}  ({len(records)} records)")
    except RawAlreadyExistsError:
        # Raw is immutable: a re-run for an existing month is a no-op success.
        print(f"[skip] raw for {run_month:%Y-%m} already exists (immutable) — no-op")


if __name__ == "__main__":
    main()
