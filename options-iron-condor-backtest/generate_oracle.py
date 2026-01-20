"""
Generate Oracle Data for Options Strategy Backtesting
======================================================
Uses iVolatility backtesting API to backtest 5 options strategies
"""

import requests
import pandas as pd
import json
import time
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

API_KEY = "K9G7iP3eH33lK3ro"
BASE_URL = "https://restapi.ivolatility.com"

TICKER = "SPY"
START_DATE = "2024-12-16"  # Entry date
END_DATE = "2025-01-17"    # Last available data date
TARGET_DTE = 45            # Days to expiration at entry

ORACLE_DIR = "tests/oracle"

# ============================================================================
# API FUNCTIONS
# ============================================================================

def delta_to_moneyness(delta, option_type):
    """
    Convert delta to approximate moneyness for API calls
    Moneyness formula from API docs:
    - For calls: K/S*100-100
    - For puts: 100-K/S*100

    Delta to moneyness mapping (approximate):
    - Calls: delta 0.5 (ATM) → moneyness 0, delta 0.3 → moneyness +5, delta 0.15 → moneyness +10
    - Puts: delta -0.5 (ATM) → moneyness 0, delta -0.3 → moneyness -5, delta -0.15 → moneyness -10
    """
    abs_delta = abs(delta)

    if option_type == 'C':
        # Call: higher delta = lower moneyness (ITM)
        if abs_delta >= 0.60:
            return -5  # ITM
        elif abs_delta >= 0.45:
            return 0   # ATM
        elif abs_delta >= 0.30:
            return 5   # Slight OTM
        elif abs_delta >= 0.20:
            return 10  # OTM
        else:
            return 15  # Far OTM
    else:  # Put
        # Put: higher delta magnitude = lower moneyness (ITM)
        if abs_delta >= 0.60:
            return 5   # ITM
        elif abs_delta >= 0.45:
            return 0   # ATM
        elif abs_delta >= 0.30:
            return -5  # Slight OTM
        elif abs_delta >= 0.20:
            return -10 # OTM
        else:
            return -15 # Far OTM


def fetch_backtest_data(symbol, dte, delta, cp, start_date, end_date):
    """
    Fetch backtesting data using nearest-option-tickers-with-prices endpoint
    This returns historical prices and Greeks for options matching criteria

    Uses delta for calls, moneyness for puts (API limitation workaround)
    """
    url = f"{BASE_URL}/equities/eod/nearest-option-tickers-with-prices"
    params = {
        'apiKey': API_KEY,
        'symbol': symbol,
        'dte': dte,
        'cp': cp,
        'startDate': start_date,
        'endDate': end_date
    }

    # Use moneyness for puts, delta for calls
    if cp == 'P':
        params['moneyness'] = delta_to_moneyness(delta, cp)
    else:
        params['delta'] = abs(delta)

    response = requests.get(url, params=params, timeout=120)
    response.raise_for_status()
    result = response.json()

    data = result.get('data', [])
    if data:
        return pd.DataFrame(data)
    return pd.DataFrame()


# ============================================================================
# STRATEGY BUILDERS
# ============================================================================

def build_iron_condor():
    """
    Iron Condor: Sell 25-30 delta put spread + call spread
    """
    print("\n" + "="*70)
    print("Building Iron Condor Strategy")
    print("="*70)

    # Fetch short put (~-0.28 delta)
    short_put_df = fetch_backtest_data(TICKER, TARGET_DTE, -0.28, 'P', START_DATE, END_DATE)
    time.sleep(1)

    # Fetch long put (~-0.15 delta, further OTM)
    long_put_df = fetch_backtest_data(TICKER, TARGET_DTE, -0.15, 'P', START_DATE, END_DATE)
    time.sleep(1)

    # Fetch short call (~0.28 delta)
    short_call_df = fetch_backtest_data(TICKER, TARGET_DTE, 0.28, 'C', START_DATE, END_DATE)
    time.sleep(1)

    # Fetch long call (~0.15 delta, further OTM)
    long_call_df = fetch_backtest_data(TICKER, TARGET_DTE, 0.15, 'C', START_DATE, END_DATE)
    time.sleep(1)

    if len(short_put_df) == 0 or len(long_put_df) == 0 or len(short_call_df) == 0 or len(long_call_df) == 0:
        print("Failed to fetch all legs")
        return None, None

    # Get entry prices from first day
    entry = short_put_df.iloc[0]

    position = {
        'strategy': 'iron_condor',
        'entry_date': START_DATE,
        'expiration': entry['expiration_date'],
        'dte': TARGET_DTE,
        'underlying_price': float(entry['start_date_forward_price']),
        'legs': [
            {
                'action': 'SELL',
                'option_type': 'PUT',
                'strike': float(short_put_df.iloc[0]['price_strike']),
                'quantity': 1,
                'option_symbol': short_put_df.iloc[0]['option_symbol'],
                'entry_price': float(short_put_df.iloc[0]['Bid']),
                'delta': float(short_put_df.iloc[0]['delta']),
                'gamma': float(short_put_df.iloc[0]['gamma']),
                'theta': float(short_put_df.iloc[0]['theta']),
                'vega': float(short_put_df.iloc[0]['vega']),
                'iv': float(short_put_df.iloc[0]['iv'])
            },
            {
                'action': 'BUY',
                'option_type': 'PUT',
                'strike': float(long_put_df.iloc[0]['price_strike']),
                'quantity': 1,
                'option_symbol': long_put_df.iloc[0]['option_symbol'],
                'entry_price': float(long_put_df.iloc[0]['Ask']),
                'delta': float(long_put_df.iloc[0]['delta']),
                'gamma': float(long_put_df.iloc[0]['gamma']),
                'theta': float(long_put_df.iloc[0]['theta']),
                'vega': float(long_put_df.iloc[0]['vega']),
                'iv': float(long_put_df.iloc[0]['iv'])
            },
            {
                'action': 'SELL',
                'option_type': 'CALL',
                'strike': float(short_call_df.iloc[0]['price_strike']),
                'quantity': 1,
                'option_symbol': short_call_df.iloc[0]['option_symbol'],
                'entry_price': float(short_call_df.iloc[0]['Bid']),
                'delta': float(short_call_df.iloc[0]['delta']),
                'gamma': float(short_call_df.iloc[0]['gamma']),
                'theta': float(short_call_df.iloc[0]['theta']),
                'vega': float(short_call_df.iloc[0]['vega']),
                'iv': float(short_call_df.iloc[0]['iv'])
            },
            {
                'action': 'BUY',
                'option_type': 'CALL',
                'strike': float(long_call_df.iloc[0]['price_strike']),
                'quantity': 1,
                'option_symbol': long_call_df.iloc[0]['option_symbol'],
                'entry_price': float(long_call_df.iloc[0]['Ask']),
                'delta': float(long_call_df.iloc[0]['delta']),
                'gamma': float(long_call_df.iloc[0]['gamma']),
                'theta': float(long_call_df.iloc[0]['theta']),
                'vega': float(long_call_df.iloc[0]['vega']),
                'iv': float(long_call_df.iloc[0]['iv'])
            }
        ]
    }

    entry_credit = (position['legs'][0]['entry_price'] - position['legs'][1]['entry_price'] +
                   position['legs'][2]['entry_price'] - position['legs'][3]['entry_price'])
    position['entry_credit'] = float(entry_credit)

    print(f"✓ Iron Condor built:")
    print(f"  Put spread: {position['legs'][1]['strike']}/{position['legs'][0]['strike']}")
    print(f"  Call spread: {position['legs'][2]['strike']}/{position['legs'][3]['strike']}")
    print(f"  Entry credit: ${entry_credit:.2f}")

    # Build backtest data
    backtest_data = []
    for date in short_put_df['t_date'].unique():
        day_short_put = short_put_df[short_put_df['t_date'] == date].iloc[0]
        day_long_put = long_put_df[long_put_df['t_date'] == date].iloc[0]
        day_short_call = short_call_df[short_call_df['t_date'] == date].iloc[0]
        day_long_call = long_call_df[long_call_df['t_date'] == date].iloc[0]

        # Calculate position value (market value of all legs)
        position_value = (
            -day_short_put['price'] +  # SELL put
            day_long_put['price'] +     # BUY put
            -day_short_call['price'] +  # SELL call
            day_long_call['price']      # BUY call
        )

        # P&L = entry credit + position value (negative because we'd close it)
        pnl = entry_credit - (-position_value)

        # Greeks
        delta = -day_short_put['delta'] + day_long_put['delta'] - day_short_call['delta'] + day_long_call['delta']
        gamma = -day_short_put['gamma'] + day_long_put['gamma'] - day_short_call['gamma'] + day_long_call['gamma']
        theta = -day_short_put['theta'] + day_long_put['theta'] - day_short_call['theta'] + day_long_call['theta']
        vega = -day_short_put['vega'] + day_long_put['vega'] - day_short_call['vega'] + day_long_call['vega']

        backtest_data.append({
            'date': str(date),
            'underlying_price': float(day_short_put['start_date_forward_price']),
            'position_value': float(-position_value),
            'pnl': float(pnl),
            'delta': float(delta),
            'gamma': float(gamma),
            'theta': float(theta),
            'vega': float(vega)
        })

    return position, backtest_data


def build_iron_butterfly():
    """Iron Butterfly: Sell ATM straddle + buy wings"""
    print("\n" + "="*70)
    print("Building Iron Butterfly Strategy")
    print("="*70)

    # ATM options (delta ~0.50)
    atm_call_df = fetch_backtest_data(TICKER, TARGET_DTE, 0.50, 'C', START_DATE, END_DATE)
    time.sleep(1)
    atm_put_df = fetch_backtest_data(TICKER, TARGET_DTE, -0.50, 'P', START_DATE, END_DATE)
    time.sleep(1)

    # Wings (delta ~0.20)
    wing_call_df = fetch_backtest_data(TICKER, TARGET_DTE, 0.20, 'C', START_DATE, END_DATE)
    time.sleep(1)
    wing_put_df = fetch_backtest_data(TICKER, TARGET_DTE, -0.20, 'P', START_DATE, END_DATE)
    time.sleep(1)

    if len(atm_call_df) == 0 or len(atm_put_df) == 0 or len(wing_call_df) == 0 or len(wing_put_df) == 0:
        print("Failed to fetch all legs")
        return None, None

    position = {
        'strategy': 'iron_butterfly',
        'entry_date': START_DATE,
        'expiration': atm_call_df.iloc[0]['expiration_date'],
        'dte': TARGET_DTE,
        'underlying_price': float(atm_call_df.iloc[0]['start_date_forward_price']),
        'legs': [
            {'action': 'SELL', 'option_type': 'PUT', 'strike': float(atm_put_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': atm_put_df.iloc[0]['option_symbol'],
             'entry_price': float(atm_put_df.iloc[0]['Bid']), 'delta': float(atm_put_df.iloc[0]['delta']),
             'gamma': float(atm_put_df.iloc[0]['gamma']), 'theta': float(atm_put_df.iloc[0]['theta']),
             'vega': float(atm_put_df.iloc[0]['vega']), 'iv': float(atm_put_df.iloc[0]['iv'])},
            {'action': 'BUY', 'option_type': 'PUT', 'strike': float(wing_put_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': wing_put_df.iloc[0]['option_symbol'],
             'entry_price': float(wing_put_df.iloc[0]['Ask']), 'delta': float(wing_put_df.iloc[0]['delta']),
             'gamma': float(wing_put_df.iloc[0]['gamma']), 'theta': float(wing_put_df.iloc[0]['theta']),
             'vega': float(wing_put_df.iloc[0]['vega']), 'iv': float(wing_put_df.iloc[0]['iv'])},
            {'action': 'SELL', 'option_type': 'CALL', 'strike': float(atm_call_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': atm_call_df.iloc[0]['option_symbol'],
             'entry_price': float(atm_call_df.iloc[0]['Bid']), 'delta': float(atm_call_df.iloc[0]['delta']),
             'gamma': float(atm_call_df.iloc[0]['gamma']), 'theta': float(atm_call_df.iloc[0]['theta']),
             'vega': float(atm_call_df.iloc[0]['vega']), 'iv': float(atm_call_df.iloc[0]['iv'])},
            {'action': 'BUY', 'option_type': 'CALL', 'strike': float(wing_call_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': wing_call_df.iloc[0]['option_symbol'],
             'entry_price': float(wing_call_df.iloc[0]['Ask']), 'delta': float(wing_call_df.iloc[0]['delta']),
             'gamma': float(wing_call_df.iloc[0]['gamma']), 'theta': float(wing_call_df.iloc[0]['theta']),
             'vega': float(wing_call_df.iloc[0]['vega']), 'iv': float(wing_call_df.iloc[0]['iv'])}
        ]
    }

    entry_credit = sum([
        position['legs'][0]['entry_price'],
        -position['legs'][1]['entry_price'],
        position['legs'][2]['entry_price'],
        -position['legs'][3]['entry_price']
    ])
    position['entry_credit'] = float(entry_credit)

    print(f"✓ Iron Butterfly built, entry credit: ${entry_credit:.2f}")

    # Build backtest
    backtest_data = []
    for date in atm_call_df['t_date'].unique():
        rows = [
            atm_put_df[atm_put_df['t_date'] == date].iloc[0],
            wing_put_df[wing_put_df['t_date'] == date].iloc[0],
            atm_call_df[atm_call_df['t_date'] == date].iloc[0],
            wing_call_df[wing_call_df['t_date'] == date].iloc[0]
        ]

        position_value = -rows[0]['price'] + rows[1]['price'] - rows[2]['price'] + rows[3]['price']
        pnl = entry_credit - (-position_value)
        delta = -rows[0]['delta'] + rows[1]['delta'] - rows[2]['delta'] + rows[3]['delta']
        gamma = -rows[0]['gamma'] + rows[1]['gamma'] - rows[2]['gamma'] + rows[3]['gamma']
        theta = -rows[0]['theta'] + rows[1]['theta'] - rows[2]['theta'] + rows[3]['theta']
        vega = -rows[0]['vega'] + rows[1]['vega'] - rows[2]['vega'] + rows[3]['vega']

        backtest_data.append({
            'date': str(date),
            'underlying_price': float(rows[0]['start_date_forward_price']),
            'position_value': float(-position_value),
            'pnl': float(pnl),
            'delta': float(delta),
            'gamma': float(gamma),
            'theta': float(theta),
            'vega': float(vega)
        })

    return position, backtest_data


def build_short_strangle():
    """Short Strangle: Sell OTM put + call"""
    print("\n" + "="*70)
    print("Building Short Strangle Strategy")
    print("="*70)

    short_put_df = fetch_backtest_data(TICKER, TARGET_DTE, -0.30, 'P', START_DATE, END_DATE)
    time.sleep(1)
    short_call_df = fetch_backtest_data(TICKER, TARGET_DTE, 0.30, 'C', START_DATE, END_DATE)
    time.sleep(1)

    if len(short_put_df) == 0 or len(short_call_df) == 0:
        return None, None

    position = {
        'strategy': 'short_strangle',
        'entry_date': START_DATE,
        'expiration': short_put_df.iloc[0]['expiration_date'],
        'dte': TARGET_DTE,
        'underlying_price': float(short_put_df.iloc[0]['start_date_forward_price']),
        'legs': [
            {'action': 'SELL', 'option_type': 'PUT', 'strike': float(short_put_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': short_put_df.iloc[0]['option_symbol'],
             'entry_price': float(short_put_df.iloc[0]['Bid']), 'delta': float(short_put_df.iloc[0]['delta']),
             'gamma': float(short_put_df.iloc[0]['gamma']), 'theta': float(short_put_df.iloc[0]['theta']),
             'vega': float(short_put_df.iloc[0]['vega']), 'iv': float(short_put_df.iloc[0]['iv'])},
            {'action': 'SELL', 'option_type': 'CALL', 'strike': float(short_call_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': short_call_df.iloc[0]['option_symbol'],
             'entry_price': float(short_call_df.iloc[0]['Bid']), 'delta': float(short_call_df.iloc[0]['delta']),
             'gamma': float(short_call_df.iloc[0]['gamma']), 'theta': float(short_call_df.iloc[0]['theta']),
             'vega': float(short_call_df.iloc[0]['vega']), 'iv': float(short_call_df.iloc[0]['iv'])}
        ]
    }

    entry_credit = position['legs'][0]['entry_price'] + position['legs'][1]['entry_price']
    position['entry_credit'] = float(entry_credit)

    print(f"✓ Short Strangle built, entry credit: ${entry_credit:.2f}")

    backtest_data = []
    for date in short_put_df['t_date'].unique():
        put = short_put_df[short_put_df['t_date'] == date].iloc[0]
        call = short_call_df[short_call_df['t_date'] == date].iloc[0]

        position_value = -put['price'] - call['price']
        pnl = entry_credit - (-position_value)

        backtest_data.append({
            'date': str(date),
            'underlying_price': float(put['start_date_forward_price']),
            'position_value': float(-position_value),
            'pnl': float(pnl),
            'delta': float(-put['delta'] - call['delta']),
            'gamma': float(-put['gamma'] - call['gamma']),
            'theta': float(-put['theta'] - call['theta']),
            'vega': float(-put['vega'] - call['vega'])
        })

    return position, backtest_data


def build_long_straddle():
    """Long Straddle: Buy ATM call + put"""
    print("\n" + "="*70)
    print("Building Long Straddle Strategy")
    print("="*70)

    atm_call_df = fetch_backtest_data(TICKER, TARGET_DTE, 0.50, 'C', START_DATE, END_DATE)
    time.sleep(1)
    atm_put_df = fetch_backtest_data(TICKER, TARGET_DTE, -0.50, 'P', START_DATE, END_DATE)
    time.sleep(1)

    if len(atm_call_df) == 0 or len(atm_put_df) == 0:
        return None, None

    position = {
        'strategy': 'long_straddle',
        'entry_date': START_DATE,
        'expiration': atm_call_df.iloc[0]['expiration_date'],
        'dte': TARGET_DTE,
        'underlying_price': float(atm_call_df.iloc[0]['start_date_forward_price']),
        'legs': [
            {'action': 'BUY', 'option_type': 'CALL', 'strike': float(atm_call_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': atm_call_df.iloc[0]['option_symbol'],
             'entry_price': float(atm_call_df.iloc[0]['Ask']), 'delta': float(atm_call_df.iloc[0]['delta']),
             'gamma': float(atm_call_df.iloc[0]['gamma']), 'theta': float(atm_call_df.iloc[0]['theta']),
             'vega': float(atm_call_df.iloc[0]['vega']), 'iv': float(atm_call_df.iloc[0]['iv'])},
            {'action': 'BUY', 'option_type': 'PUT', 'strike': float(atm_put_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': atm_put_df.iloc[0]['option_symbol'],
             'entry_price': float(atm_put_df.iloc[0]['Ask']), 'delta': float(atm_put_df.iloc[0]['delta']),
             'gamma': float(atm_put_df.iloc[0]['gamma']), 'theta': float(atm_put_df.iloc[0]['theta']),
             'vega': float(atm_put_df.iloc[0]['vega']), 'iv': float(atm_put_df.iloc[0]['iv'])}
        ]
    }

    entry_debit = position['legs'][0]['entry_price'] + position['legs'][1]['entry_price']
    position['entry_debit'] = float(entry_debit)

    print(f"✓ Long Straddle built, entry debit: ${entry_debit:.2f}")

    backtest_data = []
    for date in atm_call_df['t_date'].unique():
        call = atm_call_df[atm_call_df['t_date'] == date].iloc[0]
        put = atm_put_df[atm_put_df['t_date'] == date].iloc[0]

        position_value = call['price'] + put['price']
        pnl = position_value - entry_debit

        backtest_data.append({
            'date': str(date),
            'underlying_price': float(call['start_date_forward_price']),
            'position_value': float(position_value),
            'pnl': float(pnl),
            'delta': float(call['delta'] + put['delta']),
            'gamma': float(call['gamma'] + put['gamma']),
            'theta': float(call['theta'] + put['theta']),
            'vega': float(call['vega'] + put['vega'])
        })

    return position, backtest_data


def build_bull_call_spread():
    """Bull Call Spread: Buy ITM call, sell OTM call"""
    print("\n" + "="*70)
    print("Building Bull Call Spread Strategy")
    print("="*70)

    long_call_df = fetch_backtest_data(TICKER, TARGET_DTE, 0.65, 'C', START_DATE, END_DATE)
    time.sleep(1)
    short_call_df = fetch_backtest_data(TICKER, TARGET_DTE, 0.35, 'C', START_DATE, END_DATE)
    time.sleep(1)

    if len(long_call_df) == 0 or len(short_call_df) == 0:
        return None, None

    position = {
        'strategy': 'bull_call_spread',
        'entry_date': START_DATE,
        'expiration': long_call_df.iloc[0]['expiration_date'],
        'dte': TARGET_DTE,
        'underlying_price': float(long_call_df.iloc[0]['start_date_forward_price']),
        'legs': [
            {'action': 'BUY', 'option_type': 'CALL', 'strike': float(long_call_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': long_call_df.iloc[0]['option_symbol'],
             'entry_price': float(long_call_df.iloc[0]['Ask']), 'delta': float(long_call_df.iloc[0]['delta']),
             'gamma': float(long_call_df.iloc[0]['gamma']), 'theta': float(long_call_df.iloc[0]['theta']),
             'vega': float(long_call_df.iloc[0]['vega']), 'iv': float(long_call_df.iloc[0]['iv'])},
            {'action': 'SELL', 'option_type': 'CALL', 'strike': float(short_call_df.iloc[0]['price_strike']),
             'quantity': 1, 'option_symbol': short_call_df.iloc[0]['option_symbol'],
             'entry_price': float(short_call_df.iloc[0]['Bid']), 'delta': float(short_call_df.iloc[0]['delta']),
             'gamma': float(short_call_df.iloc[0]['gamma']), 'theta': float(short_call_df.iloc[0]['theta']),
             'vega': float(short_call_df.iloc[0]['vega']), 'iv': float(short_call_df.iloc[0]['iv'])}
        ]
    }

    entry_debit = position['legs'][0]['entry_price'] - position['legs'][1]['entry_price']
    position['entry_debit'] = float(entry_debit)

    print(f"✓ Bull Call Spread built, entry debit: ${entry_debit:.2f}")

    backtest_data = []
    for date in long_call_df['t_date'].unique():
        long = long_call_df[long_call_df['t_date'] == date].iloc[0]
        short = short_call_df[short_call_df['t_date'] == date].iloc[0]

        position_value = long['price'] - short['price']
        pnl = position_value - entry_debit

        backtest_data.append({
            'date': str(date),
            'underlying_price': float(long['start_date_forward_price']),
            'position_value': float(position_value),
            'pnl': float(pnl),
            'delta': float(long['delta'] - short['delta']),
            'gamma': float(long['gamma'] - short['gamma']),
            'theta': float(long['theta'] - short['theta']),
            'vega': float(long['vega'] - short['vega'])
        })

    return position, backtest_data


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("="*70)
    print("GENERATING ORACLE DATA - iVolatility Backtesting API")
    print("="*70)

    os.makedirs(ORACLE_DIR, exist_ok=True)

    strategies_results = {}

    # Build all 5 strategies
    strategies_funcs = [
        ('iron_condor', build_iron_condor),
        ('iron_butterfly', build_iron_butterfly),
        ('short_strangle', build_short_strangle),
        ('long_straddle', build_long_straddle),
        ('bull_call_spread', build_bull_call_spread)
    ]

    for strategy_name, build_func in strategies_funcs:
        try:
            position, backtest = build_func()

            if position and backtest:
                # Save position
                with open(f"{ORACLE_DIR}/{strategy_name}_position.json", 'w') as f:
                    json.dump(position, f, indent=2)
                print(f"✓ Saved {strategy_name}_position.json")

                # Save backtest
                pd.DataFrame(backtest).to_csv(f"{ORACLE_DIR}/{strategy_name}_backtest.csv", index=False)
                print(f"✓ Saved {strategy_name}_backtest.csv")

                strategies_results[strategy_name] = {
                    'position': position,
                    'backtest': backtest
                }

        except Exception as e:
            print(f"✗ Error with {strategy_name}: {e}")
            import traceback
            traceback.print_exc()

    # Generate comparison and rankings
    if strategies_results:
        comparison = []

        for name, data in strategies_results.items():
            backtest = data['backtest']
            position = data['position']

            final_pnl = backtest[-1]['pnl']
            max_pnl = max(r['pnl'] for r in backtest)
            min_pnl = min(r['pnl'] for r in backtest)

            entry_cost = position.get('entry_credit', -position.get('entry_debit', 1))

            comparison.append({
                'strategy': name,
                'final_pnl': final_pnl,
                'max_pnl': max_pnl,
                'min_pnl': min_pnl,
                'max_drawdown': min_pnl,
                'return_pct': (final_pnl / abs(entry_cost) * 100) if entry_cost != 0 else 0
            })

        pd.DataFrame(comparison).to_csv(f"{ORACLE_DIR}/strategies_comparison.csv", index=False)
        print(f"✓ Saved strategies_comparison.csv")

        rankings = {
            'by_final_pnl': sorted(comparison, key=lambda x: x['final_pnl'], reverse=True),
            'by_return_pct': sorted(comparison, key=lambda x: x['return_pct'], reverse=True),
            'by_risk_adjusted': sorted(comparison, key=lambda x: x['final_pnl'] / abs(x['max_drawdown']) if x['max_drawdown'] != 0 else 0, reverse=True)
        }

        with open(f"{ORACLE_DIR}/strategy_rankings.json", 'w') as f:
            json.dump(rankings, f, indent=2)
        print(f"✓ Saved strategy_rankings.json")

    print("\n" + "="*70)
    print("✓ Oracle generation complete!")
    print(f"  Generated {len(strategies_results)} strategies")
    print("="*70)


if __name__ == "__main__":
    main()
