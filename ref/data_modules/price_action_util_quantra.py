# For data manipulation
import datetime
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

# For data visualisation
import matplotlib.pyplot as plt

plt.style.use('seaborn-v0_8-darkgrid')

def get_min_max(data, argrel_window):
    # Use the argrelextrema to compute the local minima and maxima points
    local_min = argrelextrema(
        data.iloc[:-argrel_window]['Low'].values, np.less, order=argrel_window)[0]
    local_max = argrelextrema(
        data.iloc[:-argrel_window]['High'].values, np.greater, order=argrel_window)[0]

    # Store the minima and maxima values in a dataframe
    minima = data.iloc[local_min].Low
    maxima = data.iloc[local_max].High

    # Return dataframes containing minima and maxima values
    return minima, maxima


def get_support(price_data, argrel_window=15):
    assert price_data.shape[0] > argrel_window, "Length of data is less then argel_window"

    support_list = argrelextrema(
        price_data.iloc[:-argrel_window]['Low'].values, np.less, order=argrel_window)[0]

    price_data['support'] = price_data.iloc[support_list, 2]

    ltp = price_data.Close.iloc[-1]
    price_data['support'] = np.where(price_data['support'] < ltp, price_data['support'], np.nan)

    try:
        return price_data.loc[price_data.support.dropna().index.max(), 'support']
    except:
        return np.nan


def get_resistance(price_data, argrel_window=15):
    resistance_list = argrelextrema(
        price_data.iloc[:-argrel_window]['High'].values, np.greater, order=argrel_window)[0]

    price_data['resistance'] = price_data.iloc[resistance_list, 1]

    ltp = price_data.Close.iloc[-1]
    price_data['resistance'] = np.where(price_data['resistance'] > ltp, price_data['resistance'], np.nan)

    try:
        return price_data.loc[price_data.resistance.dropna().index.max(), 'resistance']
    except:
        return np.nan


def backtester(data):
    # ------------------------------- Initial Settings -------------------------------------
    # Create dataframes for round trips, storing trades, and mtm
    round_trips_details = pd.DataFrame()
    trades = pd.DataFrame()

    # Initialise current position, number of trades, cumulative pnl, stop-loss to 0 and take-profit to 100000
    current_position = 0
    trade_num = 0
    cum_pnl = 0
    sl = 0
    tp = 100000

    # Set exit flag to False
    exit_flag = False
    entry_flag = False

    # ------------------------------- Backtest over historical data -------------------------------------
    for i in data.index:

        # ------------------- Positions Check ----------------------------
        # No positions
        if (current_position == 0) & ((data.loc[i, 'signal'] == 1) or (data.loc[i, 'signal'] == -1)):
            current_position = data.loc[i, 'signal']
            entry_flag = True

        # Short Position
        elif current_position == -1:

            if data.loc[i, 'Close'] > stop_loss:
                exit_type = 'SL'
                exit_flag = True
                data.loc[i, 'signal'] = 0

            elif data.loc[i, 'Close'] < take_profit:
                exit_type = 'TP'
                exit_flag = True
                data.loc[i, 'signal'] = 0

        # Long Position
        elif current_position == 1:

            if data.loc[i, 'Close'] < stop_loss:
                exit_type = 'SL'
                exit_flag = True
                data.loc[i, 'signal'] = 0

            elif data.loc[i, 'Close'] > take_profit:
                exit_type = 'TP'
                exit_flag = True
                data.loc[i, 'signal'] = 0

        # ------------------------------- Entry Position Update -------------------------------------
        if entry_flag:
            # Populate the trades dataframe
            trades = pd.DataFrame(index=[0])
            trades['entry_date'] = i
            trades['entry_price'] = round(data.loc[i, 'Close'], 2)
            trades['position'] = current_position

            stop_loss = data.loc[i, 'stoploss']
            take_profit = data.loc[i, 'target']

            # Increase number of trades by 1
            trade_num += 1

            # Print trade details
            print(f"\033[34mTrade No: {trade_num}\033[0m | Entry Date: {i} | Entry Price: {trades.entry_price[0]} | Position: {current_position}")

            # Set exit flag to false
            entry_flag = False
            continue

        # ------------------------------- Exit Position Update -------------------------------------
        if exit_flag:
            # Populate the trades dataframe
            trades['exit_date'] = i
            trades['exit_type'] = exit_type
            trades['exit_price'] = round(data.loc[i, 'Close'], 2)

            # Calculate pnl for the trade
            trade_pnl = current_position * (round(trades.exit_price[0] - trades.entry_price[0], 2))

            # Calculate cumulative pnl
            cum_pnl += trade_pnl
            cum_pnl = round(cum_pnl, 2)
            trades['PnL'] = trade_pnl

            # Add the trade logs to round trip details
            round_trips_details = pd.concat([round_trips_details, trades])

            # Print trade details
            print(f"Exit Type: {exit_type} | Exit Date: {i} | Exit Price: {trades.exit_price[0]} | PnL: {trade_pnl} | Cum PnL: {cum_pnl}")
            print("-" * 30)

            # Update current position to 0
            current_position = 0

            # Set exit flag to false
            exit_flag = False
            continue

    return round_trips_details


def intraday_backtester(data, intraday_exit=False):
    # ------------------------------- Initial Settings -------------------------------------
    # Create dataframes for round trips, storing trades, and mtm
    round_trips_details = pd.DataFrame()
    trades = pd.DataFrame()

    # Initialise current position, number of trades,cumulative pnl, stop-loss to 0 and take-profit to 100000
    current_position = 0
    trade_num = 0
    cum_pnl = 0
    sl = 0
    tp = 100000

    # Set exit flag to False
    exit_flag = False
    entry_flag = False

    # ------------------------------- Backtest over historical data -------------------------------------
    for i in data.index:

        # ------------------------------- Entry Position Update -------------------------------------
        if entry_flag:
            # Populate the trades dataframe
            trades = pd.DataFrame(index=[0])
            trades['entry_date'] = i
            entry_date = i
            trades['entry_price'] = round(data.loc[i, 'Close'], 2)
            trades['position'] = current_position

            stop_loss = data.loc[i, 'stoploss']

            take_profit = data.loc[i, 'target']

            # Increase number of trades by 1
            trade_num += 1

            # Print trade details
            print(
                f"\033[34mTrade No: {trade_num}\033[0m | Entry Date: {i} | Entry Price: {trades.entry_price[0]} | Position: {current_position}")

            # Set exit flag to false
            entry_flag = False

            continue

        # ------------------------------- Exit Position Update -------------------------------------

        if exit_flag:
            # Populate the trades dataframe
            trades['exit_date'] = i
            trades['exit_type'] = exit_type
            trades['exit_price'] = round(data.loc[i, 'Close'], 2)

            # Calculate pnl for the trade
            trade_pnl = current_position * \
                        (round(trades.exit_price[0] - trades.entry_price[0], 2))

            # Calculate cumulative pnl
            cum_pnl += trade_pnl
            cum_pnl = round(cum_pnl, 2)
            trades['PnL'] = trade_pnl

            # Add the trade logs to round trip details
            round_trips_details = pd.concat([round_trips_details, trades])
            # Print trade details
            print(
                f"Exit Type: {exit_type} | Exit Date: {i} | Exit Price: {trades.exit_price[0]} | PnL: {trade_pnl} | Cum PnL: {cum_pnl}")
            print("-" * 30)

            # Update current position to 0
            current_position = 0

            # Set exit flag to false
            exit_flag = False

            continue

        # ------------------- Positions Check ----------------------------
        # No positions
        if (current_position == 0) & (data.loc[i, 'signal'] != 0):
            current_position = data.loc[i, 'signal']
            entry_flag = True

        # Short Position
        elif current_position == -1:

            if data.loc[i, 'Close'] > stop_loss:
                exit_type = 'SL'
                exit_flag = True

            elif data.loc[i, 'Close'] < take_profit:
                exit_type = 'TP'
                exit_flag = True

            elif (i.date() == entry_date.date()) & \
                    (i.time() == datetime.time(15, 50, 00)) & (intraday_exit == True):
                exit_type = 'Squareoff'
                exit_flag = True

        # Long Position
        elif current_position == 1:

            if data.loc[i, 'Close'] < stop_loss:
                exit_type = 'SL'
                exit_flag = True

            elif data.loc[i, 'Close'] > take_profit:
                exit_type = 'TP'
                exit_flag = True

            elif (i.date() == entry_date.date()) & \
                    (i.time() == datetime.time(15, 50, 00)) & (intraday_exit == True):
                exit_type = 'Squareoff'
                exit_flag = True

    return round_trips_details


def trade_level_analytics(trades):
    # Create dataframe to store trade analytics
    analytics = pd.DataFrame(index=['Strategy'])

    # Calculate total PnL
    analytics['Total PnL'] = trades.PnL.sum()

    # Number of total trades
    analytics['total_trades'] = len(trades)

    # Profitable trades
    analytics['Number of Winners'] = len(trades.loc[trades.PnL > 0])

    # Loss-making trades
    analytics['Number of Losers'] = len(trades.loc[trades.PnL <= 0])

    # Win percentage
    analytics['Win (%)'] = 100 * analytics['Number of Winners'] / analytics.total_trades

    # Loss percentage
    analytics['Loss (%)'] = 100 * analytics['Number of Losers'] / analytics.total_trades

    # Per trade profit/loss of winning trades
    analytics['per_trade_PnL_winners'] = trades.loc[trades.PnL > 0].PnL.mean()

    # Per trade profit/loss of losing trades
    analytics['per_trade_PnL_losers'] = np.abs(trades.loc[trades.PnL <= 0].PnL.mean())

    # Convert entry time and exit time to datetime format
    trades['entry_date'] = pd.to_datetime(trades['entry_date'])
    trades['exit_date'] = pd.to_datetime(trades['exit_date'])

    # Calculate holding period for each trade
    holding_period = trades['exit_date'] - trades['entry_date']

    # Calculate their mean
    analytics['Average holding time'] = holding_period.mean()

    # Calculate profit factor
    analytics['Profit Factor'] = (analytics['Win (%)'] / 100 * analytics['per_trade_PnL_winners']) / (
            analytics['Loss (%)'] / 100 * analytics['per_trade_PnL_losers'])

    return analytics.T


def get_performance_metrics(data, col_names=['Close', 'signal']):
    Close = col_names[0]
    signal = col_names[1]

    # Create a data to store performance metrics
    performance_metrics = pd.DataFrame(index=['Strategy'])

    # -------------------Plot equity curve---------------------

    # Calculate strategy returns
    data['strategy_returns'] = data.signal.shift(1) * data.Close.pct_change()

    # Calculate cumulative strategy returns
    data['cumulative_returns'] = (data['strategy_returns'] + 1.0).cumprod()

    # Plot cumulative returns
    data['cumulative_returns'].plot(figsize=(15, 7), color='black')
    plt.title('Equity Curve', fontsize=14)
    plt.ylabel('Returns (in times)', fontsize=12)
    plt.xlabel('Year', fontsize=12)
    plt.show()

    # -------------------Compute CAGR---------------------

    # Total number of trading candles per day
    candle_difference = data.index.to_series().diff().mean().days
    if candle_difference >= 1:
        n = np.floor(candle_difference)
    else:
        n = data.loc[datetime.datetime.strftime(
            data.index[-1].date(), '%Y-%m-%d')].shape[0]

    # Total number of trading candles over time
    trading_candles = len(data['cumulative_returns'])

    # Calculate compound annual growth rate
    performance_metrics['CAGR'] = "{0:.2f}%".format(
        (data.cumulative_returns.iloc[-1] ** (252 * n / trading_candles) - 1) * 100)

    # -------------------Compute Sharpe ratio---------------------

    # Set a risk-free rate
    risk_free_rate = 0.02 / (252 * n)

    # Calculate Sharpe ratio
    performance_metrics['Sharpe Ratio'] = round(np.sqrt(252 * n) * (np.mean(data['strategy_returns']) -
                                                                    (risk_free_rate)) / np.std(
        data['strategy_returns']), 2)

    # -------------------Compute maximum drawdown---------------------

    # Compute the cumulative maximum
    data['Peak'] = (data['strategy_returns'] + 1).cumprod().cummax()

    # Compute the Drawdown
    data['Drawdown'] = (
                               ((data['strategy_returns'] + 1).cumprod() - data['Peak']) / data['Peak']) * 100

    # Compute the maximum drawdown
    performance_metrics['Maximum Drawdown'] = "{0:.2f}%".format(
        (data['Drawdown'].min()))

    # -------------------Plot maximum drawdown---------------------

    # Plot maximum drawdown
    data['Drawdown'].plot(figsize=(15, 7), color='red')

    # Set the title and axis labels
    plt.title('Drawdowns', fontsize=14)
    plt.ylabel('Drawdown(%)', fontsize=12)
    plt.xlabel('Year', fontsize=12)
    plt.fill_between(data['Drawdown'].index,
                     data['Drawdown'].values, color='red')
    plt.show()

    # Display performance metrics
    print(performance_metrics.T)
