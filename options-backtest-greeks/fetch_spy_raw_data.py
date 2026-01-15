"""
SPY Options Raw Data Fetcher - Excel Output for SkillsBench
===========================================================
This script fetches ONLY the raw market data for SPY options:
- Date, Strike, Expiry, Type (Call/Put)
- Bid, Ask prices
- Volume, Open Interest
- Underlying SPY price

NO Greeks, NO Implied Volatility - AI must calculate these!

This is designed for AI agent performance comparison:
- Without skills: AI must implement everything from scratch
- With skills: AI follows best practices for options pricing

Requirements:
- pip install yfinance pandas openpyxl numpy tqdm

Usage:
- python fetch_spy_raw_data.py
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

TICKER = 'SPY'
OUTPUT_FILE = 'spy_options_raw.xlsx'  # Excel format for SkillsBench

# Simulation parameters for historical data generation
HISTORICAL_DAYS = 252  # One year of trading days
BASE_PRICE = 450.0     # Starting SPY price

# Market microstructure parameters
BID_ASK_SPREAD_PCT = 0.02  # 2% typical spread (wider for OTM options)
VOLUME_SCALE = 1000        # Base volume for ATM options

# ============================================================================
# DATA GENERATION FUNCTIONS
# ============================================================================

def generate_realistic_spy_prices(days=252, start_price=450.0):
    """
    Generate realistic SPY price series using geometric Brownian motion
    with realistic parameters based on historical SPY behavior
    """
    np.random.seed(42)  # For reproducibility

    # SPY historical parameters (approximate)
    annual_return = 0.10      # 10% annual return
    annual_volatility = 0.18  # 18% annual volatility

    dt = 1/252  # Daily time step

    # Generate returns
    drift = (annual_return - 0.5 * annual_volatility**2) * dt
    shock = annual_volatility * np.sqrt(dt) * np.random.randn(days)

    # Price path
    returns = drift + shock
    prices = start_price * np.exp(np.cumsum(returns))

    return prices


def calculate_option_theoretical_value(S, K, T, option_type='call'):
    """
    Simple intrinsic value + time value approximation
    This is NOT Black-Scholes - just a rough approximation for generating data
    AI must implement proper pricing!
    """
    intrinsic = max(0, S - K) if option_type == 'call' else max(0, K - S)

    # Rough time value based on moneyness and time
    moneyness = S / K
    time_value_factor = np.sqrt(T / 365) * 0.15  # Simplified

    if option_type == 'call':
        if moneyness > 1:  # ITM
            time_value = K * time_value_factor * 0.5
        else:  # OTM
            time_value = S * time_value_factor * np.exp(-2 * (1 - moneyness)**2)
    else:  # put
        if moneyness < 1:  # ITM
            time_value = K * time_value_factor * 0.5
        else:  # OTM
            time_value = S * time_value_factor * np.exp(-2 * (moneyness - 1)**2)

    return intrinsic + time_value


def generate_raw_options_data(days=252, start_price=450.0):
    """
    Generate raw options market data WITHOUT Greeks or IV
    This simulates what real market data looks like
    """
    print(f"Generating {days} days of raw options market data...")
    print("=" * 70)

    # Generate underlying price series
    spy_prices = generate_realistic_spy_prices(days, start_price)

    # Generate trading dates (business days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days * 1.4))  # Account for weekends
    dates = pd.date_range(start=start_date, end=end_date, freq='B')[:days]

    all_data = []

    # For each date, create options chain
    for i, date in enumerate(tqdm(dates, desc="Generating data")):
        current_price = spy_prices[i]

        # Generate strikes around current price (±20%, $5 intervals)
        strike_min = round(current_price * 0.80 / 5) * 5
        strike_max = round(current_price * 1.20 / 5) * 5
        strikes = np.arange(strike_min, strike_max + 1, 5)

        # Generate multiple expiration dates
        # Standard monthly expiries: 30, 45, 60 DTE
        expiry_dates = [
            (date + timedelta(days=30)).strftime('%Y-%m-%d'),
            (date + timedelta(days=45)).strftime('%Y-%m-%d'),
            (date + timedelta(days=60)).strftime('%Y-%m-%d'),
        ]

        for expiry_str in expiry_dates:
            expiry = pd.to_datetime(expiry_str)
            dte = (expiry - date).days

            for strike in strikes:
                for option_type in ['call', 'put']:

                    # Calculate approximate mid price
                    mid_price = calculate_option_theoretical_value(
                        current_price, strike, dte, option_type
                    )

                    # Add some randomness
                    mid_price *= (1 + np.random.normal(0, 0.05))
                    mid_price = max(0.01, mid_price)  # Minimum price

                    # Calculate bid-ask spread (wider for OTM options)
                    moneyness = current_price / strike if option_type == 'call' else strike / current_price
                    spread_multiplier = 1 + 2 * abs(1 - moneyness)  # Wider spread for OTM
                    spread = mid_price * BID_ASK_SPREAD_PCT * spread_multiplier

                    bid = max(0.01, mid_price - spread/2)
                    ask = mid_price + spread/2

                    # Round to realistic tick sizes
                    if bid < 3:
                        bid = round(bid * 20) / 20  # $0.05 ticks
                        ask = round(ask * 20) / 20
                    else:
                        bid = round(bid * 10) / 10  # $0.10 ticks
                        ask = round(ask * 10) / 10

                    # Generate volume (higher for ATM options)
                    atm_factor = np.exp(-5 * (moneyness - 1)**2)
                    volume = int(np.random.poisson(VOLUME_SCALE * atm_factor))
                    open_interest = int(np.random.poisson(VOLUME_SCALE * atm_factor * 3))

                    # Create data row
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
                        'volume': volume,
                        'open_interest': open_interest,
                    }

                    all_data.append(row)

    df = pd.DataFrame(all_data)

    print(f"\n✓ Generated {len(df):,} option records")
    print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"  Trading days: {df['date'].nunique()}")
    print(f"  Unique strikes: {df['strike'].nunique()}")
    print(f"  Unique expiries: {df['expiration'].nunique()}")

    return df


def add_data_quality_issues(df, missing_rate=0.02, outlier_rate=0.01):
    """
    Add realistic data quality issues that AI must handle:
    - Some missing bid/ask
    - Occasional outliers
    - Crossed markets (bid > ask) occasionally

    This tests AI's data validation and cleaning abilities
    """
    print("\nAdding realistic data quality issues...")

    df = df.copy()
    n = len(df)

    # 1. Introduce some missing bids/asks (2% of data)
    missing_indices = np.random.choice(n, size=int(n * missing_rate), replace=False)
    df.loc[missing_indices, 'bid'] = np.nan

    missing_indices = np.random.choice(n, size=int(n * missing_rate), replace=False)
    df.loc[missing_indices, 'ask'] = np.nan

    # 2. Introduce some outliers (1% of data)
    outlier_indices = np.random.choice(n, size=int(n * outlier_rate), replace=False)
    df.loc[outlier_indices, 'bid'] *= np.random.uniform(2, 5)

    outlier_indices = np.random.choice(n, size=int(n * outlier_rate), replace=False)
    df.loc[outlier_indices, 'ask'] *= np.random.uniform(2, 5)

    # 3. Introduce some crossed markets (0.5% of data)
    crossed_indices = np.random.choice(n, size=int(n * 0.005), replace=False)
    for idx in crossed_indices:
        # Swap bid and ask to create crossed market
        df.loc[idx, 'bid'], df.loc[idx, 'ask'] = df.loc[idx, 'ask'], df.loc[idx, 'bid']

    print(f"  ✓ Added ~{missing_rate*100:.1f}% missing values")
    print(f"  ✓ Added ~{outlier_rate*100:.1f}% price outliers")
    print(f"  ✓ Added ~0.5% crossed markets")
    print("  → AI must detect and handle these issues!")

    return df


def validate_data(df):
    """Show data quality summary"""
    print("\n" + "=" * 70)
    print("DATA QUALITY SUMMARY")
    print("=" * 70)

    total = len(df)

    # Missing values
    missing_bid = df['bid'].isna().sum()
    missing_ask = df['ask'].isna().sum()
    print(f"Missing bids: {missing_bid:,} ({missing_bid/total*100:.2f}%)")
    print(f"Missing asks: {missing_ask:,} ({missing_ask/total*100:.2f}%)")

    # Crossed markets
    crossed = (df['bid'] > df['ask']).sum()
    print(f"Crossed markets: {crossed:,} ({crossed/total*100:.2f}%)")

    # Zero prices
    zero_prices = ((df['bid'] == 0) | (df['ask'] == 0)).sum()
    print(f"Zero prices: {zero_prices:,} ({zero_prices/total*100:.2f}%)")

    # Outliers (bid/ask > 20% of underlying)
    df_clean = df.dropna(subset=['bid', 'ask'])
    outliers = ((df_clean['bid'] > df_clean['underlying_price'] * 0.20) |
                (df_clean['ask'] > df_clean['underlying_price'] * 0.20)).sum()
    print(f"Potential outliers: {outliers:,} ({outliers/len(df_clean)*100:.2f}%)")

    print("=" * 70)


def save_to_excel(df, filename):
    """Save to Excel format with proper formatting"""
    print(f"\nSaving data to {filename}...")

    # Sort by date, expiration, type, strike for easier processing
    df = df.sort_values(['date', 'expiration', 'option_type', 'strike'])

    # Convert date columns to datetime for proper Excel formatting
    df['date'] = pd.to_datetime(df['date'])
    df['expiration'] = pd.to_datetime(df['expiration'])

    # Save to Excel with formatting
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Options_Data', index=False)

        # Get the worksheet
        worksheet = writer.sheets['Options_Data']

        # Set column widths for better readability
        column_widths = {
            'A': 12,  # date
            'B': 18,  # underlying_symbol
            'C': 16,  # underlying_price
            'D': 10,  # strike
            'E': 12,  # expiration
            'F': 8,   # dte
            'G': 12,  # option_type
            'H': 10,  # bid
            'I': 10,  # ask
            'J': 12,  # volume
            'K': 14,  # open_interest
        }

        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width

    print(f"✓ Data saved successfully!")
    print(f"  File: {filename}")
    print(f"  Size: {len(df):,} rows × {len(df.columns)} columns")

    # Get file size
    import os
    file_size_mb = os.path.getsize(filename) / 1024 / 1024
    print(f"  File size: {file_size_mb:.2f} MB")

    if file_size_mb > 100:
        print(f"  ⚠️  WARNING: File is larger than 100MB - GitHub may have issues")
        print(f"     Consider reducing HISTORICAL_DAYS or strike range")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function"""
    print("=" * 70)
    print("SPY OPTIONS RAW DATA GENERATOR - EXCEL OUTPUT")
    print("=" * 70)
    print("\nThis script generates RAW market data ONLY:")
    print("  ✓ Date, Strike, Expiry, Type")
    print("  ✓ Bid, Ask prices")
    print("  ✓ Volume, Open Interest")
    print("  ✓ Underlying price")
    print("\n  ✗ NO Greeks (delta, gamma, theta, vega)")
    print("  ✗ NO Implied Volatility")
    print("  ✗ NO Options pricing calculations")
    print("\n→ AI agent must calculate these from scratch!")
    print("=" * 70)
    print()

    # Configuration summary
    print("CONFIGURATION:")
    print(f"  Ticker: {TICKER}")
    print(f"  Historical days: {HISTORICAL_DAYS}")
    print(f"  Starting price: ${BASE_PRICE:.2f}")
    print(f"  Output file: {OUTPUT_FILE}")
    print()

    # Generate data
    df = generate_raw_options_data(
        days=HISTORICAL_DAYS,
        start_price=BASE_PRICE
    )

    # Add realistic data quality issues
    df = add_data_quality_issues(df)

    # Validate and show summary
    validate_data(df)

    # Show sample data
    print("\n" + "=" * 70)
    print("SAMPLE DATA (first 20 rows)")
    print("=" * 70)
    print(df.head(20).to_string(index=False))

    # Save to Excel
    save_to_excel(df, OUTPUT_FILE)

    # Final summary
    print("\n" + "=" * 70)
    print("DATA CHARACTERISTICS")
    print("=" * 70)
    print(f"Total records: {len(df):,}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"Trading days: {df['date'].nunique()}")
    print(f"Price range: ${df['underlying_price'].min():.2f} - ${df['underlying_price'].max():.2f}")
    print(f"Strike range: ${df['strike'].min():.2f} - ${df['strike'].max():.2f}")
    print(f"DTE range: {df['dte'].min()} - {df['dte'].max()} days")
    print(f"Avg daily options: {len(df) / df['date'].nunique():.0f}")

    print("\n" + "=" * 70)
    print("WHAT AI MUST IMPLEMENT")
    print("=" * 70)
    print("1. Data Cleaning:")
    print("   - Handle missing bid/ask values")
    print("   - Detect and fix crossed markets")
    print("   - Filter outliers")
    print("   - Validate data consistency")
    print()
    print("2. Options Pricing:")
    print("   - Implement Black-Scholes model")
    print("   - Calculate implied volatility from market prices")
    print("   - Handle American vs European options")
    print("   - Deal with numerical stability issues")
    print()
    print("3. Greeks Calculation:")
    print("   - Derive and implement delta, gamma, theta, vega")
    print("   - Handle edge cases (T→0, deep ITM/OTM)")
    print("   - Validate calculations")
    print()
    print("4. Strategy Implementation:")
    print("   - Parse and apply entry/exit rules")
    print("   - Track multi-leg positions")
    print("   - Calculate P&L accurately")
    print("   - Generate performance metrics")
    print("=" * 70)
    print()
    print("✓ Raw data ready for AI agent backtesting challenge!")
    print()


if __name__ == "__main__":
    main()
