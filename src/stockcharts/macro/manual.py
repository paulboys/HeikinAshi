"""Hand-entered macro values and scenario checklist state.

Two watchlist inputs have no free API -- hyperscaler bond order coverage
(syndicate data) and S&P 500 trailing EPS -- so they are entered by hand.
Defaults live in :mod:`stockcharts.macro.config` so the dashboard is populated
on first run and the repository records where the numbers came from; overrides
are written to JSON.

JSON rather than CSV because ``.gitignore`` excludes ``*.csv`` globally, which
would make the file invisible and easy to lose.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from stockcharts.macro.config import MANUAL_DEFAULTS, ManualEntry, scenario_sign_keys

SCHEMA_VERSION = 1

_DEFAULT_MANUAL_PATH = Path(
    os.environ.get(
        "STOCKCHARTS_MACRO_DATA",
        str(Path(__file__).resolve().parents[3] / "cache" / "macro" / "manual_inputs.json"),
    )
)


@dataclass
class ManualInputs:
    """Hand-entered values and checklist ticks.

    Attributes:
        entries: Manual values keyed by series key.
        checklists: Ticked scenario signs, keyed by scenario then sign.
        warnings: Non-fatal problems encountered while loading.
    """

    entries: dict[str, ManualEntry] = field(default_factory=dict)
    checklists: dict[str, dict[str, bool]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def value(self, key: str) -> float | None:
        """Return a manual value, or None when unset.

        Args:
            key: Series key.

        Returns:
            The entered value, or None.
        """
        entry = self.entries.get(key)
        return entry.value if entry else None

    def as_of(self, key: str) -> date | None:
        """Return the as-of date for a manual value.

        Args:
            key: Series key.

        Returns:
            The as-of date, or None when unset.
        """
        entry = self.entries.get(key)
        return entry.as_of if entry else None

    def is_ticked(self, scenario: str, sign: str) -> bool:
        """Return whether a scenario sign is ticked.

        Args:
            scenario: Scenario key, such as ``"A"``.
            sign: Sign key.

        Returns:
            True when the sign has been ticked.
        """
        return bool(self.checklists.get(scenario, {}).get(sign, False))


def default_manual_path() -> Path:
    """Return the manual-input file location.

    Returns:
        Path honouring ``STOCKCHARTS_MACRO_DATA``.
    """
    return Path(os.environ.get("STOCKCHARTS_MACRO_DATA", str(_DEFAULT_MANUAL_PATH)))


def load_manual_inputs(path: Path | None = None) -> ManualInputs:
    """Load manual inputs, falling back to defaults.

    A missing or corrupt file is not an error: the defaults are returned with
    an explanatory warning, so a bad write can never take the dashboard down.

    Args:
        path: Override for the JSON file location.

    Returns:
        Manual inputs, with defaults filled in for anything unset.
    """
    target = path or default_manual_path()
    inputs = ManualInputs(entries=dict(MANUAL_DEFAULTS))

    if not target.exists():
        return inputs

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        inputs.warnings.append(f"Could not read {target.name}, using defaults: {error}")
        return inputs

    if not isinstance(payload, dict):
        inputs.warnings.append(f"{target.name} is not a JSON object, using defaults")
        return inputs

    stored = payload.get("entries")
    if isinstance(stored, dict):
        for key, raw in stored.items():
            if key not in MANUAL_DEFAULTS:
                inputs.warnings.append(f"Ignoring unknown manual key {key!r}")
                continue
            if not isinstance(raw, dict):
                continue
            try:
                inputs.entries[key] = ManualEntry(
                    value=float(raw["value"]),
                    as_of=date.fromisoformat(str(raw.get("as_of", date.today().isoformat()))),
                    note=str(raw.get("note", "")),
                )
            except (KeyError, TypeError, ValueError) as error:
                inputs.warnings.append(f"Ignoring malformed entry {key!r}: {error}")

    ticks = payload.get("checklists")
    if isinstance(ticks, dict):
        valid = set(scenario_sign_keys())
        for scenario, signs in ticks.items():
            if not isinstance(signs, dict):
                continue
            inputs.checklists[str(scenario)] = {
                str(k): bool(v) for k, v in signs.items() if str(k) in valid
            }

    return inputs


def save_manual_inputs(inputs: ManualInputs, path: Path | None = None) -> Path:
    """Write manual inputs atomically.

    The write goes to a temporary file in the same directory and is then moved
    into place, so a crash mid-write cannot leave a truncated store behind.

    Args:
        inputs: Values to persist.
        path: Override for the JSON file location.

    Returns:
        The path written.
    """
    from stockcharts.macro.client import utc_now_iso

    target = path or default_manual_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
        "entries": {
            key: {"value": entry.value, "as_of": entry.as_of.isoformat(), "note": entry.note}
            for key, entry in sorted(inputs.entries.items())
        },
        "checklists": {k: dict(v) for k, v in sorted(inputs.checklists.items())},
    }

    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(target.parent),
        prefix=".manual_",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
        os.replace(handle.name, target)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return target


def set_manual_value(
    key: str,
    value: float,
    as_of: date | None = None,
    note: str = "",
    path: Path | None = None,
) -> ManualInputs:
    """Set one manual value and persist the result.

    Args:
        key: Series key, which must be a known manual input.
        value: New value.
        as_of: Date the value refers to.  Defaults to today.
        note: Free-text provenance note.
        path: Override for the JSON file location.

    Returns:
        The updated inputs.

    Raises:
        KeyError: If the key is not a known manual input.
    """
    if key not in MANUAL_DEFAULTS:
        raise KeyError(f"{key!r} is not a manual input; known keys: {sorted(MANUAL_DEFAULTS)}")
    inputs = load_manual_inputs(path)
    inputs.entries[key] = ManualEntry(value=value, as_of=as_of or date.today(), note=note)
    save_manual_inputs(inputs, path)
    return inputs


def set_checklist(
    scenario: str,
    ticked: dict[str, bool],
    path: Path | None = None,
) -> ManualInputs:
    """Replace one scenario's checklist state and persist it.

    Args:
        scenario: Scenario key.
        ticked: Sign key to ticked state.
        path: Override for the JSON file location.

    Returns:
        The updated inputs.
    """
    inputs = load_manual_inputs(path)
    valid = set(scenario_sign_keys())
    inputs.checklists[scenario] = {k: bool(v) for k, v in ticked.items() if k in valid}
    save_manual_inputs(inputs, path)
    return inputs


__all__ = [
    "SCHEMA_VERSION",
    "ManualInputs",
    "default_manual_path",
    "load_manual_inputs",
    "save_manual_inputs",
    "set_checklist",
    "set_manual_value",
]
