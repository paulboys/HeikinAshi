"""One-off historical download into the local macro cache.

The dashboard is slow on its first deep lookback because the Treasury feed is
paginated by calendar year and the FRED CSV endpoint throttles rapid requests.
Running a backfill once pays that cost deliberately, with progress printed, so
later runs read from disk.

Completed calendar years and accumulated FRED history are kept permanently, so
a backfill never needs repeating for the range it covered.
"""

from __future__ import annotations

from datetime import date, timedelta

from stockcharts.macro.client import MacroClient
from stockcharts.macro.series import CORE_FRED_KEYS, SERIES, fred_series_id

EARLIEST_TREASURY_YEAR = 1995


def backfill_history(
    years: int = 10,
    client: MacroClient | None = None,
    verbose: bool = True,
) -> int:
    """Download and cache the requested span of history.

    Args:
        years: Years of history to retrieve.
        client: Reusable client.  A default one is created when omitted.
        verbose: Whether to print progress.

    Returns:
        Process exit code: 0 when everything succeeded, 1 if anything failed.
    """
    macro_client = client or MacroClient()
    today = date.today()
    # Derive the year span the same way fetch_treasury_history does, from the
    # lookback *window* rather than whole calendar years. A 10y window reaches
    # into the calendar year 10 years ago, so counting years alone leaves the
    # earliest one uncached and the first deep load still pays for it.
    start = today - timedelta(days=max(1, years) * 365)
    first_year = max(EARLIEST_TREASURY_YEAR, start.year)
    calendar_years = list(range(first_year, today.year + 1))
    fred_ids = [fred_series_id(key) for key in CORE_FRED_KEYS]
    total = len(calendar_years) * 2 + len(fred_ids)

    if verbose:
        print(
            f"Backfilling {years}y: {len(calendar_years)} Treasury years "
            f"(nominal + real) and {len(fred_ids)} FRED series -- {total} requests."
        )
        print("Completed years are cached permanently, so this runs once.\n")

    failures: list[str] = []
    step = 0

    for year in calendar_years:
        for real, label in ((False, "nominal"), (True, "real")):
            step += 1
            if verbose:
                print(f"[{step}/{total}] Treasury {label} {year}...", end=" ", flush=True)
            try:
                frame = macro_client.fetch_treasury_curve(year=year, real=real)
                print(f"[OK] {len(frame)} rows" if verbose else "", end="\n" if verbose else "")
            except Exception as error:
                failures.append(f"treasury {label} {year}: {type(error).__name__}: {error}")
                if verbose:
                    print(f"[ERROR] {type(error).__name__}")

    start = today - timedelta(days=max(1, years) * 365)
    for series_id in fred_ids:
        step += 1
        if verbose:
            print(f"[{step}/{total}] FRED {series_id}...", end=" ", flush=True)
        try:
            series = macro_client.fetch_series(series_id, start=start)
            if verbose:
                span = (
                    f"{series.index.min().date()} -> {series.index.max().date()}"
                    if len(series)
                    else "empty"
                )
                print(f"[OK] {len(series)} obs, {span}")
        except Exception as error:
            failures.append(f"{series_id}: {type(error).__name__}: {error}")
            if verbose:
                print(f"[ERROR] {type(error).__name__}")

    if verbose:
        print(f"\nCache directory: {macro_client.cache_dir}")
        if failures:
            print(f"{len(failures)} request(s) failed:")
            for failure in failures:
                print(f"    [WARN] {failure}")
            print("Re-run to retry only what is missing; cached items are skipped.")
        else:
            print("Backfill complete. The dashboard now reads this range from disk.")

    return 1 if failures else 0


def cache_summary(client: MacroClient | None = None) -> dict[str, object]:
    """Describe what the macro cache currently holds.

    Args:
        client: Reusable client, used only for its cache directory.

    Returns:
        A mapping of file count, total size and the covered Treasury years.
    """
    macro_client = client or MacroClient()
    directory = macro_client.cache_dir
    if not directory.exists():
        return {"files": 0, "size_mb": 0.0, "treasury_years": [], "fred_series": []}

    files = list(directory.glob("*.parquet"))
    treasury_years = sorted(
        {
            int(f.stem.rsplit("_", 1)[-1])
            for f in files
            if f.stem.startswith("treasury_") and f.stem.rsplit("_", 1)[-1].isdigit()
        }
    )
    fred_series = sorted(f.stem.removeprefix("fred_") for f in files if f.stem.startswith("fred_"))
    return {
        "files": len(files),
        "size_mb": round(sum(f.stat().st_size for f in files) / 1_048_576, 2),
        "treasury_years": treasury_years,
        "fred_series": fred_series,
        "manual_keys": sorted(k for k, s in SERIES.items() if s.source == "manual"),
    }


__all__ = ["EARLIEST_TREASURY_YEAR", "backfill_history", "cache_summary"]
