"""
SPY Options Data Fetcher - iVolatility API
===========================================
Fetches real SPY options historical data with IV and Greeks
"""

import requests
import pandas as pd
import gzip
import io
import time
from datetime import datetime
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

API_KEY = "K9G7iP3eH33lK3ro"
BASE_URL = "https://restapi.ivolatility.com"

TICKER = "SPY"
OUTPUT_FILE = "spy_options_with_iv.xlsx"

# Date range for backtest
# Entry: ~45 DTE before expiration, hold to expiration
START_DATE = "2024-12-01"
END_DATE = "2025-01-17"

# Target expiration range for Iron Condor
EXP_FROM = "2025-01-17"
EXP_TO = "2025-03-21"

# Strike range (SPY ~590-600)
STRIKE_FROM = 550
STRIKE_TO = 650

REQUEST_DELAY = 1.0  # seconds between requests


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

    response = requests.get(info_url, params=params, timeout=60)
    info = response.json()

    if not info or len(info) == 0:
        return None

    # Get download URL
    data_info = info[0].get('data', [])
    if not data_info:
        return None

    download_url = data_info[0].get('urlForDownload')
    if not download_url:
        return None

    # Download the gzip file
    download_response = requests.get(f"{download_url}?apiKey={API_KEY}", timeout=120)

    # Decompress and read CSV
    with gzip.GzipFile(fileobj=io.BytesIO(download_response.content)) as f:
        df = pd.read_csv(f)

    return df


def fetch_with_download(endpoint, params, description="data"):
    """Fetch data, handling the async download pattern"""
    print(f"  Fetching {description}...")

    result = make_request(endpoint, params)

    records = result.get('status', {}).get('recordsFound', 0)
    code = result.get('status', {}).get('code', '')
    request_uuid = result.get('query', {}).get('requestUUID', '')

    print(f"    Found {records} records (status: {code})")

    if records == 0:
        return pd.DataFrame()

    # Check if data is in response directly
    data = result.get('data', [])
    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        # Data is inline
        return pd.DataFrame(data)

    # Data needs to be downloaded
    if request_uuid:
        print(f"    Downloading from server...")
        time.sleep(0.5)  # Wait for file to be ready
        df = download_data(request_uuid)
        if df is not None:
            print(f"    Downloaded {len(df)} rows")
            return df

    return pd.DataFrame()


# ============================================================================
# MAIN DATA FETCHING
# ============================================================================

def fetch_options_raw_iv(symbol, from_date, to_date):
    """
    Fetch EOD options chain with Raw IV and Greeks
    Endpoint: /equities/eod/options-rawiv
    """
    params = {
        'symbol': symbol,
        'from': from_date,
        'to': to_date
    }

    return fetch_with_download(
        '/equities/eod/options-rawiv',
        params,
        f"{symbol} options {from_date} to {to_date}"
    )


def fetch_single_option_raw_iv(option_symbol, from_date, to_date):
    """
    Fetch single option with Raw IV and Greeks
    Endpoint: /equities/eod/single-stock-option-raw-iv
    """
    params = {
        'symbol': option_symbol,
        'from': from_date,
        'to': to_date
    }

    return fetch_with_download(
        '/equities/eod/single-stock-option-raw-iv',
        params,
        f"option {option_symbol}"
    )


def fetch_option_series_on_date(symbol, date, exp_from, exp_to, strike_from, strike_to):
    """
    Fetch option series (contracts) on a specific date
    Endpoint: /equities/eod/option-series-on-date
    """
    params = {
        'symbol': symbol,
        'date': date,
        'expFrom': exp_from,
        'expTo': exp_to,
        'strikeFrom': strike_from,
        'strikeTo': strike_to
    }

    return fetch_with_download(
        '/equities/eod/option-series-on-date',
        params,
        f"{symbol} contracts on {date}"
    )


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("SPY OPTIONS DATA FETCHER - iVolatility API")
    print("=" * 70)
    print(f"Symbol: {TICKER}")
    print(f"Date range: {START_DATE} to {END_DATE}")
    print(f"Expiration range: {EXP_FROM} to {EXP_TO}")
    print(f"Strike range: {STRIKE_FROM} to {STRIKE_TO}")
    print()

    # =========================================================================
    # Method 1: Try fetching full options chain with IV/Greeks
    # =========================================================================
    print("=" * 70)
    print("Method 1: Fetch full options chain with IV and Greeks")
    print("=" * 70)

    try:
        # Try fetching for a shorter date range first
        df = fetch_options_raw_iv(TICKER, '2025-01-10', '2025-01-17')

        if len(df) > 0:
            print(f"\n✓ SUCCESS! Got {len(df)} records")
            print(f"Columns: {df.columns.tolist()}")
            print(f"\nSample data:")
            print(df.head(10))

            # Save to Excel
            print(f"\nSaving to {OUTPUT_FILE}...")
            df.to_excel(OUTPUT_FILE, index=False)
            print("✓ Saved!")

            # Summary
            print("\n" + "=" * 70)
            print("DATA SUMMARY")
            print("=" * 70)
            print(f"Total records: {len(df):,}")

            for col in ['date', 'tradeDate', 'Date']:
                if col in df.columns:
                    print(f"Date range: {df[col].min()} to {df[col].max()}")
                    print(f"Trading days: {df[col].nunique()}")
                    break

            for col in ['expiration', 'expirationDate', 'Expiration']:
                if col in df.columns:
                    print(f"Expirations: {df[col].nunique()}")
                    break

            for col in ['strike', 'Strike']:
                if col in df.columns:
                    print(f"Strike range: {df[col].min()} - {df[col].max()}")
                    break

            return

    except requests.exceptions.HTTPError as e:
        if '403' in str(e):
            print(f"\n✗ Access denied (403) - this endpoint may require a higher tier plan")
        else:
            print(f"\n✗ HTTP Error: {e}")
    except Exception as e:
        print(f"\n✗ Error: {e}")

    # =========================================================================
    # Method 2: Fetch individual options with IV/Greeks
    # =========================================================================
    print("\n" + "=" * 70)
    print("Method 2: Fetch individual options with IV and Greeks")
    print("=" * 70)

    try:
        # First get the list of option contracts
        print("\nStep 1: Get option contracts list...")
        contracts_df = fetch_option_series_on_date(
            TICKER, '2025-01-15',
            EXP_FROM, EXP_TO,
            STRIKE_FROM, STRIKE_TO
        )

        if len(contracts_df) == 0:
            print("No contracts found!")
            return

        print(f"\nFound {len(contracts_df)} contracts")
        print(f"Columns: {contracts_df.columns.tolist()}")
        print(contracts_df.head())

        # Filter to manageable number of contracts
        # Focus on key strikes for Iron Condor (e.g., every $5)
        if 'strike' in contracts_df.columns:
            contracts_df = contracts_df[contracts_df['strike'] % 5 == 0]
        elif 'Strike' in contracts_df.columns:
            contracts_df = contracts_df[contracts_df['Strike'] % 5 == 0]

        print(f"\nFiltered to {len(contracts_df)} contracts (every $5 strike)")

        # Step 2: Fetch historical data for each contract
        print("\nStep 2: Fetch historical data for each contract...")

        all_data = []
        option_col = 'OptionSymbol' if 'OptionSymbol' in contracts_df.columns else 'optionSymbol'

        # Fetch ALL filtered contracts (for complete backtest data)
        contracts_to_fetch = contracts_df[option_col].unique()
        print(f"Will fetch {len(contracts_to_fetch)} contracts...")

        for i, option_symbol in enumerate(contracts_to_fetch):
            print(f"\n  [{i+1}/{len(contracts_to_fetch)}] {option_symbol}")

            try:
                option_df = fetch_single_option_raw_iv(option_symbol, START_DATE, END_DATE)
                if len(option_df) > 0:
                    all_data.append(option_df)
                time.sleep(REQUEST_DELAY)
            except requests.exceptions.HTTPError as e:
                if '403' in str(e):
                    print(f"    Access denied - trying without IV/Greeks...")
                    # Try basic endpoint
                    try:
                        params = {
                            'symbol': option_symbol,
                            'from': START_DATE,
                            'to': END_DATE
                        }
                        option_df = fetch_with_download(
                            '/equities/eod/single-stock-option',
                            params,
                            f"option {option_symbol} (basic)"
                        )
                        if len(option_df) > 0:
                            all_data.append(option_df)
                    except Exception as e2:
                        print(f"    Basic endpoint also failed: {e2}")
                else:
                    print(f"    Error: {e}")
            except Exception as e:
                print(f"    Error: {e}")

        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            print(f"\n\n✓ Collected {len(final_df)} total records")
            print(f"Columns: {final_df.columns.tolist()}")

            # Save
            print(f"\nSaving to {OUTPUT_FILE}...")
            final_df.to_excel(OUTPUT_FILE, index=False)
            print("✓ Saved!")

            # Summary
            print("\n" + "=" * 70)
            print("DATA SUMMARY")
            print("=" * 70)
            print(f"Total records: {len(final_df):,}")
            print(final_df.head(10))
        else:
            print("\nNo data collected!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
