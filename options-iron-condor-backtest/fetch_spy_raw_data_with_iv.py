"""
SPY Options Data Fetcher - WITH Pre-calculated IV (NO Greeks)
=============================================================
This script generates SPY options data with:
- Raw market data (Date, Strike, Expiry, Bid, Ask, Volume, OI)
- Pre-calculated Implied Volatility

AI must calculate Greeks using formulas from the skill!

This tests whether AI can:
1. Apply Black-Scholes Greeks formulas from skill
2. Construct Iron Condor strategy (25-30 delta)
3. Perform multi-day backtesting
4. Generate risk analysis

Requirements:
- pip install pandas openpyxl numpy scipy tqdm

Usage:
- python fetch_spy_data_with_iv.py
"""

import pandas as pd
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
from datetime import datetime, timedelta
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

TICKER = 'SPY'
OUTPUT_FILE = 'spy_options_with_iv.xlsx'

# Simulation parameters
HISTORICAL_DAYS = 252  # One year of trading days
BASE_PRICE = 450.0     # Starting SPY price

# Market parameters
RISK_FREE_RATE = 0.045  # 4.5% risk-free rate
DIVIDEND_YIELD = 0.015  # 1.5% SPY dividend yield
BASE_VOLATILITY = 0.18  # 18% base annual volatility

# Data quality parameters
BID_ASK_SPREAD_PCT = 0.02
VOLUME_SCALE = 1000

# Strike range - EXPANDED for better delta coverage
STRIKE_RANGE_PCT = 0.25  # ±25% from spot

# ============================================================================
# BLACK-SCHOLES IMPLEMENTATION (for data generation only)
# ============================================================================

def black_scholes_price(S, K, T, r, sigma, q, option_type='call'):
    """Calculate option price using Black-Scholes model with dividends"""
    if T <= 0:
        if option_type == 'call':
            return max(0, S - K)
        else:
            return max(0, K - S)

    if sigma <= 0:
        return np.nan

    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    d1 = np.clip(d1, -10, 10)
    d2 = np.clip(d2, -10, 10)

    if option_type == 'call':
        price = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)

    return max(0, price)


def calculate_implied_volatility(market_price, S, K, T, r, q, option_type='call'):
    """Calculate implied volatility using Brent's method"""
    if T <= 0 or market_price <= 0:
        return np.nan

    if option_type == 'call':
        intrinsic = max(0, S * np.exp(-q * T) - K * np.exp(-r * T))
    else:
        intrinsic = max(0, K * np.exp(-r * T) - S * np.exp(-q * T))

    if market_price < intrinsic * 0.99:
        return np.nan

    def objective(sigma):
        return black_scholes_price(S, K, T, r, sigma, q, option_type) - market_price

    try:
        iv = brentq(objective, 0.001, 3.0, xtol=1e-6)
        return iv
    except (ValueError, RuntimeError):
        return np.nan


# ============================================================================
# DATA GENERATION
# ============================================================================

def generate_realistic_spy_prices(days=252, start_price=450.0):
    """Generate realistic SPY price series using GBM"""
    np.random.seed(42)

    annual_return = 0.10
    annual_volatility = 0.18
    dt = 1/252

    drift = (annual_return - 0.5 * annual_volatility**2) * dt
    shock = annual_volatility * np.sqrt(dt) * np.random.randn(days)

    returns = drift + shock
    prices = start_price * np.exp(np.cumsum(returns))

    return prices


def generate_volatility_surface(base_vol=0.18, days=252):
    """Generate time-varying volatility with realistic patterns"""
    np.random.seed(43)

    vols = np.zeros(days)
    vols[0] = base_vol

    mean_reversion = 0.03
    vol_of_vol = 0.02

    for i in range(1, days):
        shock = np.random.randn() * vol_of_vol
        vols[i] = vols[i-1] + mean_reversion * (base_vol - vols[i-1]) + shock

        if np.random.rand() < 0.05:
            vols[i] *= np.random.uniform(1.2, 1.5)

        vols[i] = np.clip(vols[i], 0.10, 0.50)

    return vols


def generate_options_data_with_iv(days=252, start_price=450.0):
    """Generate options data WITH IV but WITHOUT Greeks"""
    print(f"Generating {days} days of options data WITH IV (no Greeks)...")
    print("=" * 70)

    spy_prices = generate_realistic_spy_prices(days, start_price)
    base_vols = generate_volatility_surface(BASE_VOLATILITY, days)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days * 1.4))
    dates = pd.date_range(start=start_date, end=end_date, freq='B')[:days]

    all_data = []

    for i, date in enumerate(tqdm(dates, desc="Generating data")):
        current_price = spy_prices[i]
        current_vol = base_vols[i]

        strike_min = round(current_price * (1 - STRIKE_RANGE_PCT) / 5) * 5
        strike_max = round(current_price * (1 + STRIKE_RANGE_PCT) / 5) * 5
        strikes = np.arange(strike_min, strike_max + 1, 5)

        expiry_offsets = [29, 44, 59]

        for offset in expiry_offsets:
            expiry_date = date + timedelta(days=offset)
            expiry_str = expiry_date.strftime('%Y-%m-%d')
            dte = offset
            T = dte / 365.0

            for strike in strikes:
                for option_type in ['call', 'put']:
                    moneyness = np.log(current_price / strike)

                    # Volatility skew
                    if option_type == 'put' and moneyness > 0:
                        skew_adjustment = 0.02 * moneyness * 10
                    elif option_type == 'call' and moneyness < 0:
                        skew_adjustment = 0.01 * abs(moneyness) * 5
                    else:
                        skew_adjustment = 0

                    term_adjustment = 0.001 * (dte - 30)

                    option_iv = current_vol + skew_adjustment + term_adjustment
                    option_iv = np.clip(option_iv, 0.08, 0.60)
                    option_iv *= (1 + np.random.normal(0, 0.02))
                    option_iv = np.clip(option_iv, 0.08, 0.60)

                    theo_price = black_scholes_price(
                        current_price, strike, T,
                        RISK_FREE_RATE, option_iv, DIVIDEND_YIELD,
                        option_type
                    )

                    if theo_price < 0.05:
                        continue

                    market_noise = np.random.normal(0, 0.03)
                    mid_price = theo_price * (1 + market_noise)
                    mid_price = max(0.05, mid_price)

                    spread_multiplier = 1 + 2 * abs(moneyness)
                    spread = mid_price * BID_ASK_SPREAD_PCT * spread_multiplier

                    bid = max(0.01, mid_price - spread/2)
                    ask = mid_price + spread/2

                    if bid < 3:
                        bid = round(bid * 20) / 20
                        ask = round(ask * 20) / 20
                    else:
                        bid = round(bid * 10) / 10
                        ask = round(ask * 10) / 10

                    mid_price = (bid + ask) / 2

                    # Calculate IV from mid_price for consistency
                    implied_vol = calculate_implied_volatility(
                        mid_price, current_price, strike, T,
                        RISK_FREE_RATE, DIVIDEND_YIELD, option_type
                    )

                    if np.isnan(implied_vol):
                        implied_vol = option_iv

                    atm_factor = np.exp(-5 * moneyness**2)
                    volume = int(np.random.poisson(VOLUME_SCALE * atm_factor))
                    open_interest = int(np.random.poisson(VOLUME_SCALE * atm_factor * 3))

                    # NO Greeks - AI must calculate them!
                    row = {
                        'date': date.strftime('%Y-%m-%d'),
                        'underlying_symbol': TICKER,
                        'underlying_price': round(current_price, 2),
                        'strike': float(strike),
                        'expiration': expiry_str,
                        'dte': dte,
                        'option_type': option_type,
                        'bid': round(bid, 2),
                        'ask': round(ask, 2),
                        'mid_price': round(mid_price, 2),
                        'volume': volume,
                        'open_interest': open_interest,
                        'implied_volatility': round(implied_vol, 4),
                    }

                    all_data.append(row)

    df = pd.DataFrame(all_data)

    print(f"\n✓ Generated {len(df):,} option records")
    print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"  Trading days: {df['date'].nunique()}")
    print(f"  Unique strikes: {df['strike'].nunique()}")

    return df


def add_data_quality_issues(df, missing_rate=0.01):
    """Add realistic data quality issues"""
    print("\nAdding realistic data quality issues...")

    df = df.copy()
    n = len(df)

    # Some missing bids/asks (1%)
    missing_indices = np.random.choice(n, size=int(n * missing_rate), replace=False)
    df.loc[missing_indices, 'bid'] = np.nan

    # Some crossed markets (0.3%)
    crossed_indices = np.random.choice(n, size=int(n * 0.003), replace=False)
    for idx in crossed_indices:
        df.loc[idx, 'bid'], df.loc[idx, 'ask'] = df.loc[idx, 'ask'], df.loc[idx, 'bid']

    print(f"  ✓ Added ~{missing_rate*100:.1f}% missing values")
    print(f"  ✓ Added ~0.3% crossed markets")

    return df


def save_to_excel(df, filename):
    """Save to Excel with proper formatting"""
    print(f"\nSaving data to {filename}...")

    df = df.sort_values(['date', 'expiration', 'option_type', 'strike'])

    df['date'] = pd.to_datetime(df['date'])
    df['expiration'] = pd.to_datetime(df['expiration'])

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Options_Data', index=False)

        worksheet = writer.sheets['Options_Data']

        column_widths = {
            'A': 12, 'B': 18, 'C': 16, 'D': 10, 'E': 12, 'F': 8,
            'G': 12, 'H': 10, 'I': 10, 'J': 10, 'K': 12, 'L': 14,
            'M': 18
        }

        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width

    print(f"✓ Data saved successfully!")

    import os
    file_size_mb = os.path.getsize(filename) / 1024 / 1024
    print(f"  File size: {file_size_mb:.2f} MB")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("SPY OPTIONS DATA GENERATOR - WITH IV (NO GREEKS)")
    print("=" * 70)
    print("\nThis script generates options data WITH:")
    print("  ✓ Raw market data (Date, Strike, Expiry, Bid, Ask)")
    print("  ✓ Mid price")
    print("  ✓ Implied Volatility")
    print("\nNO Greeks included - AI must calculate them!")
    print("  ✗ Delta")
    print("  ✗ Gamma")
    print("  ✗ Theta")
    print("  ✗ Vega")
    print("  ✗ Rho")
    print("=" * 70)
    print()

    print("CONFIGURATION:")
    print(f"  Ticker: {TICKER}")
    print(f"  Historical days: {HISTORICAL_DAYS}")
    print(f"  Starting price: ${BASE_PRICE:.2f}")
    print(f"  Strike range: ±{STRIKE_RANGE_PCT*100:.0f}% from spot")
    print(f"  Risk-free rate: {RISK_FREE_RATE*100:.1f}%")
    print(f"  Dividend yield: {DIVIDEND_YIELD*100:.1f}%")
    print(f"  Output file: {OUTPUT_FILE}")
    print()

    df = generate_options_data_with_iv(
        days=HISTORICAL_DAYS,
        start_price=BASE_PRICE
    )

    df = add_data_quality_issues(df)

    print("\n" + "=" * 70)
    print("SAMPLE DATA (first 10 rows)")
    print("=" * 70)
    print(df.head(10).to_string(index=False))

    save_to_excel(df, OUTPUT_FILE)

    print("\n" + "=" * 70)
    print("DATA SUMMARY")
    print("=" * 70)
    print(f"Total records: {len(df):,}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"Trading days: {df['date'].nunique()}")
    print(f"Price range: ${df['underlying_price'].min():.2f} - ${df['underlying_price'].max():.2f}")
    print(f"Strike range: ${df['strike'].min():.2f} - ${df['strike'].max():.2f}")
    print(f"IV range: {df['implied_volatility'].min():.2%} - {df['implied_volatility'].max():.2%}")

    print("\n" + "=" * 70)
    print("WHAT AI MUST IMPLEMENT")
    print("=" * 70)
    print("1. Data Cleaning:")
    print("   - Handle missing values")
    print("   - Fix crossed markets")
    print()
    print("2. Greeks Calculation (using skill formulas):")
    print("   - Delta: d(Price)/d(Spot)")
    print("   - Gamma: d(Delta)/d(Spot)")
    print("   - Theta: d(Price)/d(Time)")
    print("   - Vega: d(Price)/d(Volatility)")
    print("   - Rho: d(Price)/d(Rate)")
    print()
    print("3. Iron Condor Construction:")
    print("   - Select options with 25-30 delta")
    print("   - Build 4-leg position")
    print("   - Calculate entry credit")
    print()
    print("4. Backtesting:")
    print("   - Track daily P&L")
    print("   - Monitor Greeks evolution")
    print("   - Apply stop-loss rules")
    print()
    print("5. Risk Analysis:")
    print("   - Max profit/loss calculation")
    print("   - Breakeven points")
    print("   - Return on risk metrics")
    print("=" * 70)
    print()
    print("✓ Data ready for Iron Condor backtesting task!")


if __name__ == "__main__":
    main()
