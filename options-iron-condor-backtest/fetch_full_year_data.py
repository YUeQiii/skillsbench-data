"""
SPY Options Full Year Data Fetcher - iVolatility API
====================================================
Fetches one full year (2024) of SPY options EOD data with IV and Greeks

This script fetches data for the entire year to allow AI agents to:
- Analyze market regimes across different periods
- Identify optimal entry timing for each strategy
- Optimize independently for each options strategy

Requirements:
- pip install requests pandas openpyxl tqdm
"""

import requests
import pandas as pd
import gzip
import io
import time
from datetime import datetime, timedelta
from tqdm import tqdm
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

API_KEY = "K9G7iP3eH33lK3ro"
BASE_URL = "https://restapi.ivolatility.com"

TICKER = "SPY"
OUTPUT_FILE = "spy_options_with_iv.xlsx"

# Full year 2024
START_DATE = "2024-01-02"
END_DATE = "2024-12-31"

# Wide expiration range (to cover different DTE needs)
# Allow options expiring anywhere in 2024 or early 2025
EXP_FROM = "2024-01-01"
EXP_TO = "2025-03-31"

# Wide strike range (SPY ranged ~480-610 in 2024)
STRIKE_FROM = 400
STRIKE_TO = 700

# Fetch control
REQUEST_DELAY = 2.0  # seconds between requests (be nice to API)
BATCH_SIZE_DAYS = 30  # Fetch in monthly batches to avoid timeouts

# ============================================================================
# API HELPER FUNCTIONS
# ============================================================================

def make_request(endpoint, params):
    """Make API request and return JSON response"""
    params['apiKey'] = API_KEY
    url = f"{BASE_URL}{endpoint}"

    response = requests.get(url, params=params, timeout=120)
    response.raise_for_status()
    return response.json()


def download_data(request_uuid):
    """Download data from a completed request"""
    # First get the download info
    info_url = f"{BASE_URL}/data/info/{request_uuid}"
    params = {'apiKey': API_KEY}

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.get(info_url, params=params, timeout=60)
            info = response.json()

            if not info or len(info) == 0:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return None

            # Get download URL
            data_info = info[0].get('data', [])
            if not data_info:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return None

            download_url = data_info[0].get('urlForDownload')
            if not download_url:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return None

            # Download the gzip file
            download_response = requests.get(f"{download_url}?apiKey={API_KEY}", timeout=120)

            # Decompress and read CSV
            with gzip.GzipFile(fileobj=io.BytesIO(download_response.content)) as f:
                df = pd.read_csv(f)

            return df

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"    Retry {attempt + 1}/{max_retries}: {e}")
                time.sleep(3)
            else:
                raise


def fetch_with_download(endpoint, params, description="data"):
    """Fetch data, handling the async download pattern"""
    print(f"  {description}...")

    result = make_request(endpoint, params)

    records = result.get('status', {}).get('recordsFound', 0)
    code = result.get('status', {}).get('code', '')
    request_uuid = result.get('query', {}).get('requestUUID', '')

    print(f"    Status: {code}, Records: {records:,}")

    if records == 0:
        return pd.DataFrame()

    # Check if data is in response directly (small datasets)
    data = result.get('data', [])
    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        print(f"    Got inline data: {len(data)} rows")
        return pd.DataFrame(data)

    # Data needs to be downloaded (large datasets)
    if request_uuid:
        print(f"    Downloading from UUID: {request_uuid[:8]}...")
        time.sleep(1)  # Wait for file to be ready
        df = download_data(request_uuid)
        if df is not None:
            print(f"    ✓ Downloaded {len(df):,} rows")
            return df

    print(f"    ✗ No data available")
    return pd.DataFrame()


# ============================================================================
# FETCH STRATEGIES
# ============================================================================

def fetch_full_chain_monthly(symbol, year=2024):
    """
    Fetch full options chain month by month
    This is the most efficient approach for large date ranges
    """
    all_data = []

    # Split into monthly batches
    months = []
    for month in range(1, 13):
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year, 12, 31)
        else:
            end = datetime(year, month + 1, 1) - timedelta(days=1)

        months.append((start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'), month))

    print(f"\n{'='*70}")
    print(f"Fetching {symbol} options chain for {year}")
    print(f"Strategy: Monthly batches ({len(months)} months)")
    print(f"{'='*70}\n")

    for start_date, end_date, month_num in tqdm(months, desc="Months"):
        try:
            params = {
                'symbol': symbol,
                'from': start_date,
                'to': end_date
            }

            df = fetch_with_download(
                '/equities/eod/options-rawiv',
                params,
                f"Month {month_num:02d} ({start_date} to {end_date})"
            )

            if len(df) > 0:
                all_data.append(df)

            time.sleep(REQUEST_DELAY)

        except requests.exceptions.HTTPError as e:
            if '403' in str(e):
                print(f"    ✗ 403 Forbidden - endpoint may require premium access")
                return None  # Signal to try alternative method
            else:
                print(f"    ✗ HTTP Error: {e}")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            import traceback
            traceback.print_exc()

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        return final_df

    return pd.DataFrame()


def fetch_contracts_and_history(symbol, sample_dates, exp_from, exp_to, strike_from, strike_to, start_date, end_date):
    """
    Alternative method: Get contract list, then fetch each contract's history
    More API calls but works with lower-tier access
    """
    print(f"\n{'='*70}")
    print(f"Alternative Method: Fetch contracts then individual histories")
    print(f"{'='*70}\n")

    # Step 1: Get contracts from a few representative dates
    all_contracts = []

    print("Step 1: Discovering available contracts...")
    for date in sample_dates:
        print(f"\n  Fetching contracts for {date}...")
        try:
            params = {
                'symbol': symbol,
                'date': date,
                'expFrom': exp_from,
                'expTo': exp_to,
                'strikeFrom': strike_from,
                'strikeTo': strike_to
            }

            df = fetch_with_download(
                '/equities/eod/option-series-on-date',
                params,
                f"Contracts on {date}"
            )

            if len(df) > 0:
                all_contracts.append(df)

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"    Error: {e}")

    if not all_contracts:
        print("\n✗ Could not fetch contract lists!")
        return pd.DataFrame()

    # Combine and deduplicate
    contracts_df = pd.concat(all_contracts, ignore_index=True)

    # Find the option symbol column
    option_col = None
    for col in ['OptionSymbol', 'optionSymbol', 'option_symbol', 'Symbol', 'symbol']:
        if col in contracts_df.columns:
            option_col = col
            break

    if not option_col:
        print(f"\n✗ Cannot find option symbol column. Available: {contracts_df.columns.tolist()}")
        return pd.DataFrame()

    unique_contracts = contracts_df[option_col].unique()

    # Filter to reduce API calls (every $5 strike, limit expirations)
    # This is a simplified filter - adjust as needed
    print(f"\nFound {len(unique_contracts)} unique contracts")
    print(f"Filtering to manageable subset...")

    # Aggressive filtering to reduce API calls to ~1500-2000 contracts (target 1-2 hours)

    strike_col = None
    exp_col = None

    # Filter 1: Keep only every $20 strike (wider spacing)
    if 'strike' in contracts_df.columns or 'Strike' in contracts_df.columns:
        strike_col = 'strike' if 'strike' in contracts_df.columns else 'Strike'
        contracts_df = contracts_df[contracts_df[strike_col] % 20 == 0]
        print(f"After $20 strike filter: {len(contracts_df)} rows")

    # Filter 2: Tighter strike range around realistic trading zone
    # SPY 2024: ~480-610, so keep 460-640 (±20% buffer)
    if strike_col:
        contracts_df = contracts_df[
            (contracts_df[strike_col] >= 460) &
            (contracts_df[strike_col] <= 640)
        ]
        print(f"After strike range filter (460-640): {len(contracts_df)} rows")

    # Filter 3: Keep only monthly expirations (3rd Friday)
    if 'expiration' in contracts_df.columns or 'Expiration' in contracts_df.columns:
        exp_col = 'expiration' if 'expiration' in contracts_df.columns else 'Expiration'
        contracts_df[exp_col] = pd.to_datetime(contracts_df[exp_col])
        # Monthly expirations: day 15-21
        contracts_df = contracts_df[contracts_df[exp_col].dt.day.between(15, 21)]
        print(f"After monthly expiration filter: {len(contracts_df)} rows")

    # Filter 4: Keep only quarterly expirations (reduce further if still too many)
    # Quarterly: March, June, September, December
    if exp_col:
        quarterly_months = [3, 6, 9, 12]
        contracts_df = contracts_df[contracts_df[exp_col].dt.month.isin(quarterly_months)]
        print(f"After quarterly expiration filter: {len(contracts_df)} rows")

    unique_contracts = contracts_df[option_col].unique()
    print(f"\nFinal contract count: {len(unique_contracts)} contracts")

    print(f"\nStep 2: Fetching history for {len(unique_contracts)} contracts...")
    print(f"This will take approximately {len(unique_contracts) * REQUEST_DELAY / 60:.1f} minutes")

    all_data = []
    failed = 0

    for i, option_symbol in enumerate(tqdm(unique_contracts, desc="Contracts")):
        try:
            params = {
                'symbol': option_symbol,
                'from': start_date,
                'to': end_date
            }

            # Try with IV/Greeks first
            try:
                df = fetch_with_download(
                    '/equities/eod/single-stock-option-raw-iv',
                    params,
                    f"{option_symbol}"
                )
            except requests.exceptions.HTTPError as e:
                if '403' in str(e):
                    # Fall back to basic endpoint
                    df = fetch_with_download(
                        '/equities/eod/single-stock-option',
                        params,
                        f"{option_symbol} (basic)"
                    )
                else:
                    raise

            if len(df) > 0:
                all_data.append(df)
            else:
                failed += 1

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            failed += 1
            if i < 5:  # Show first few errors
                print(f"\n  Error fetching {option_symbol}: {e}")

    print(f"\n\nCompleted: {len(all_data)} successful, {failed} failed")

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        return final_df

    return pd.DataFrame()


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("SPY OPTIONS FULL YEAR DATA FETCHER")
    print("=" * 70)
    print(f"Symbol: {TICKER}")
    print(f"Date range: {START_DATE} to {END_DATE}")
    print(f"Expiration range: {EXP_FROM} to {EXP_TO}")
    print(f"Strike range: ${STRIKE_FROM} to ${STRIKE_TO}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    # Try Method 1: Full chain by month
    print("\n" + "=" * 70)
    print("METHOD 1: Fetching full options chain (monthly batches)")
    print("=" * 70)

    df = fetch_full_chain_monthly(TICKER, year=2024)

    if df is None:
        # Method 1 not available (403), try Method 2
        print("\n⚠️  Full chain endpoint not accessible, trying alternative method...")

        # Sample dates across the year
        sample_dates = [
            '2024-01-15', '2024-02-15', '2024-03-15',
            '2024-04-15', '2024-05-15', '2024-06-15',
            '2024-07-15', '2024-08-15', '2024-09-15',
            '2024-10-15', '2024-11-15', '2024-12-15'
        ]

        df = fetch_contracts_and_history(
            TICKER, sample_dates,
            EXP_FROM, EXP_TO,
            STRIKE_FROM, STRIKE_TO,
            START_DATE, END_DATE
        )

    # Save results
    if len(df) > 0:
        print(f"\n{'='*70}")
        print("SUCCESS!")
        print(f"{'='*70}")
        print(f"Total records: {len(df):,}")
        print(f"\nColumns: {df.columns.tolist()}")
        print(f"\nFirst few rows:")
        print(df.head())

        # Data summary
        print(f"\n{'='*70}")
        print("DATA SUMMARY")
        print(f"{'='*70}")

        # Find date columns
        date_cols = [c for c in df.columns if 'date' in c.lower() or 'Date' in c]
        if date_cols:
            date_col = date_cols[0]
            print(f"Date column: {date_col}")
            print(f"  Date range: {df[date_col].min()} to {df[date_col].max()}")
            print(f"  Trading days: {df[date_col].nunique()}")

        # Expirations
        exp_cols = [c for c in df.columns if 'expir' in c.lower() or 'Expir' in c]
        if exp_cols:
            exp_col = exp_cols[0]
            print(f"\nExpiration column: {exp_col}")
            print(f"  Unique expirations: {df[exp_col].nunique()}")
            print(f"  Range: {df[exp_col].min()} to {df[exp_col].max()}")

        # Strikes
        strike_cols = [c for c in df.columns if c.lower() == 'strike']
        if strike_cols:
            strike_col = strike_cols[0]
            print(f"\nStrike column: {strike_col}")
            print(f"  Strike range: ${df[strike_col].min()} to ${df[strike_col].max()}")
            print(f"  Unique strikes: {df[strike_col].nunique()}")

        # Save
        print(f"\n{'='*70}")
        print(f"Saving to {OUTPUT_FILE}...")
        df.to_excel(OUTPUT_FILE, index=False)
        print("✓ Saved successfully!")
        print(f"\nFile size: {os.path.getsize(OUTPUT_FILE) / 1024 / 1024:.1f} MB")

    else:
        print(f"\n{'='*70}")
        print("FAILED - No data collected")
        print(f"{'='*70}")
        print("\nPossible issues:")
        print("1. API key may not have access to historical data")
        print("2. Date range may be outside available data")
        print("3. Network/API issues")
        print("\nCheck API documentation and account permissions.")


if __name__ == "__main__":
    main()
