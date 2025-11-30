import numpy as np
import pandas as pd
import pytest
from stockcharts.indicators.rsi import compute_rsi


def test_rsi_invalid_period():
    prices = pd.Series([100, 101, 102])
    with pytest.raises((ValueError, AssertionError, Exception)):
        compute_rsi(prices, period=0)


def test_rsi_constant_series():
    prices = pd.Series([100]*50)
    rsi = compute_rsi(prices, period=14)
    assert len(rsi) == len(prices)
    # RSI may be NaN at leading positions; ensure values are within bounds where not NaN
    valid = rsi.dropna()
    assert ((valid >= 0) & (valid <= 100)).all()


def test_rsi_with_nans():
    prices = pd.Series([100, np.nan, 101, 102, np.nan, 103])
    rsi = compute_rsi(prices, period=14)
    assert len(rsi) == len(prices)
    # Use pandas isna for Series; non-NaN values must be within [0,100]
    mask = pd.isna(rsi) | ((rsi >= 0) & (rsi <= 100))
    assert mask.all()
