import yfinance as yf


def screen_nasdaq(min_volume=1000000, min_price=5.0):
    """
    Screen NASDAQ stocks based on volume and price criteria.

    Args:
        min_volume: Minimum average volume threshold
        min_price: Minimum stock price threshold

    Returns:
        List of ticker symbols that meet the criteria
    """
    # Fetch NASDAQ tickers
    tickers = yf.Tickers("^IXIC").tickers

    passing_tickers = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Get current price
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if current_price is None or current_price < min_price:
                continue

            # Get volume
            avg_volume = info.get("averageVolume") or info.get(
                "averageDailyVolume10Day"
            )
            if avg_volume and avg_volume >= min_volume:
                passing_tickers.append(ticker)
        except Exception as e:
            continue

    return passing_tickers


def screen_ticker(ticker, min_volume=1000000, min_price=5.0):
    """
    Screen a single ticker based on volume and price criteria.

    Args:
        ticker: Stock ticker symbol
        min_volume: Minimum average volume threshold
        min_price: Minimum stock price threshold

    Returns:
        True if ticker meets criteria, False otherwise
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Check current price
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if current_price is None or current_price < min_price:
            return False

        # Check volume
        avg_volume = info.get("averageVolume") or info.get("averageDailyVolume10Day")
        if avg_volume and avg_volume >= min_volume:
            return True
    except Exception as e:
        return False

    return False
