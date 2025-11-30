import pandas as pd
import numpy as np
from stockcharts.indicators.pivots import ema_derivative_pivots


def _df(prices, rsis):
    return pd.DataFrame({'Close': prices, 'RSI': rsis}, index=pd.date_range('2025-01-01', periods=len(prices)))


def test_pivots_with_short_series():
    df = _df([100, 101], [50, 51])
    piv = ema_derivative_pivots(df, price_span=5, rsi_span=5)
    assert 'price_highs' in piv and 'rsi_highs' in piv


def test_pivots_flat_series():
    df = _df([100]*100, [50]*100)
    piv = ema_derivative_pivots(df, price_span=5, rsi_span=5)
    # Expect few or zero pivots on flat series
    assert isinstance(piv['price_highs'], pd.Index)
    assert isinstance(piv['rsi_highs'], pd.Index)


def test_pivots_extreme_values():
    df = _df(list(np.linspace(1e-3, 1e6, 200)), list(np.clip(np.linspace(0, 200, 200), 0, 100)))
    piv = ema_derivative_pivots(df, price_span=10, rsi_span=10)
    assert 'price_highs' in piv and 'rsi_highs' in piv
