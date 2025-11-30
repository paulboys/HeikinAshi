import pandas as pd

from stockcharts.charts.heiken_ashi import heiken_ashi


def test_heiken_ashi_basic():
    # Simple deterministic dataset of 3 candles
    data = {
        "Open": [10.0, 11.0, 12.0],
        "High": [11.0, 12.0, 13.0],
        "Low": [9.0, 10.5, 11.5],
        "Close": [10.5, 11.5, 12.5],
    }
    df = pd.DataFrame(data)
    ha = heiken_ashi(df)
    assert list(ha.columns) == ["HA_Open", "HA_High", "HA_Low", "HA_Close"]
    assert len(ha) == 3
    # First HA_Open equals (O0 + C0)/2
    assert ha.iloc[0]["HA_Open"] == (10.0 + 10.5) / 2
    # HA_Close row 0 equals (O+H+L+C)/4
    expected_close0 = (10.0 + 11.0 + 9.0 + 10.5) / 4
    assert ha.iloc[0]["HA_Close"] == expected_close0
