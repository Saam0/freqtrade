import pandas as pd
import pandas_ta as ta
from datetime import datetime
from freqtrade.strategy import IStrategy, Trade
from freqtrade.strategy import IntParameter, DecimalParameter


class AdvancedSupertrendPullback(IStrategy):
    """
    Պրոֆեսիոնալ Supertrend Pullback Ռազմավարություն
    - Ավելացված է use_custom_stoploss = True (Ստոպը հիմա ԱՇԽԱՏՈՒՄ Է)
    - Ռիսկը իդեալական ֆիքսված է դեպոզիտի 1%-ի չափով
    - Չափազանց արագացված կատարողականություն
    """
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True

    use_custom_stoploss = True  # <--- ԱՄԵՆԱԿԱՐԵՎՈՐ ՏՈՂԸ (Ակտիվացնում է մեր Ստոպ-Լոսը)
    startup_candle_count = 100  # <--- Ապահովում է ինդիկատորի ճշգրտությունը սկզբից

    # ==========================================
    # HYPEROPT ՊԱՐԱՄԵՏՐԵՐ
    # ==========================================
    st_length = IntParameter(5, 20, default=10, space="indicator")
    st_multiplier = DecimalParameter(1.5, 5.0, default=3.0, decimals=1, space="indicator")

    trend_maturity_candles = IntParameter(2, 20, default=10, space="buy")
    pullback_max_dist = DecimalParameter(0.001, 0.020, default=0.004, decimals=3, space="buy")

    rr_target = DecimalParameter(1.0, 5.0, default=3.0, decimals=1, space="sell")

    # Ռիսկի Կառավարում
    fee_buffer = 0.003
    use_volume_filter = True
    min_volume = 100
    max_entries_per_trend = 1
    portfolio_risk_pct = 0.01  # 1% ՌԻՍԿ
    max_allowed_leverage = 20.0

    # ==========================================
    # ԲԱԶԱՅԻՆ ԿԱՐԳԱՎՈՐՈՒՄՆԵՐ
    # ==========================================
    process_only_new_candles = True
    use_exit_signal = True
    stoploss = -0.99
    minimal_roi = {"0": 100}
    trend_trade_counts = {}

    def _get_candle_at_or_before(self, dataframe: pd.DataFrame, target_time: datetime):
        if dataframe.empty: return None
        subset = dataframe.loc[dataframe['date'] <= target_time]
        if subset.empty: return None
        return subset.iloc[-1]

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        st = ta.supertrend(dataframe['high'], dataframe['low'], dataframe['close'],
                           length=self.st_length.value, multiplier=self.st_multiplier.value)

        dir_col = f'SUPERTd_{self.st_length.value}_{self.st_multiplier.value}'
        line_col = f'SUPERT_{self.st_length.value}_{self.st_multiplier.value}'

        dataframe['st_dir'] = st[dir_col]
        dataframe['st_line'] = st[line_col]
        dataframe['st_dist'] = abs(dataframe['close'] - dataframe['st_line']) / dataframe['st_line']

        dataframe['trend_change'] = (dataframe['st_dir'] != dataframe['st_dir'].shift(1))
        dataframe['trend_id'] = dataframe['trend_change'].cumsum()
        dataframe['bars_in_trend'] = dataframe.groupby('trend_id').cumcount()

        if self.use_volume_filter:
            dataframe['vol_ok'] = dataframe['volume'] > self.min_volume
        else:
            dataframe['vol_ok'] = True

        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[
            (
                    (dataframe['st_dir'] == 1) &
                    (dataframe['bars_in_trend'] >= self.trend_maturity_candles.value) &
                    (dataframe['st_dist'] <= self.pullback_max_dist.value) &
                    (dataframe['close'].shift(1) > dataframe['st_line'].shift(1)) &
                    (dataframe['vol_ok'])
            ),
            'enter_long'] = 1

        dataframe.loc[
            (
                    (dataframe['st_dir'] == -1) &
                    (dataframe['bars_in_trend'] >= self.trend_maturity_candles.value) &
                    (dataframe['st_dist'] <= self.pullback_max_dist.value) &
                    (dataframe['close'].shift(1) < dataframe['st_line'].shift(1)) &
                    (dataframe['vol_ok'])
            ),
            'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[(dataframe['st_dir'] == -1) & (dataframe['st_dir'].shift(1) == 1), 'exit_long'] = 1
        dataframe.loc[(dataframe['st_dir'] == 1) & (dataframe['st_dir'].shift(1) == -1), 'exit_short'] = 1
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str,
                            side: str, **kwargs) -> bool:
        current_candle = kwargs.get('current_candle')
        if current_candle is None:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            current_candle = self._get_candle_at_or_before(dataframe, current_time)
        if current_candle is None: return True

        trend_id = current_candle['trend_id']
        pair_store = self.trend_trade_counts.setdefault(pair, {})
        trades_in_this_trend = pair_store.get(trend_id, 0)

        if trades_in_this_trend >= self.max_entries_per_trend: return False
        pair_store[trend_id] = trades_in_this_trend + 1

        if len(pair_store) > 1000:
            for old_id in sorted(pair_store.keys())[:-500]: pair_store.pop(old_id, None)

        return True

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        current_candle = kwargs.get('current_candle')
        if current_candle is None:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            current_candle = self._get_candle_at_or_before(dataframe, current_time)
        if current_candle is None: return -0.99

        st_line = current_candle['st_line']
        if trade.is_short:
            stop_distance = (st_line - current_rate) / current_rate
        else:
            stop_distance = (current_rate - st_line) / current_rate

        return -max(stop_distance, self.fee_buffer)

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        risk_pct = trade.get_custom_data(key='initial_risk_pct', default=None)
        if risk_pct is None:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            entry_candle = self._get_candle_at_or_before(dataframe, trade.open_date_utc)
            if entry_candle is not None:
                risk_pct = abs(trade.open_rate - entry_candle['st_line']) / trade.open_rate
                if risk_pct < self.fee_buffer: risk_pct = self.fee_buffer
                trade.set_custom_data('initial_risk_pct', risk_pct)
            else:
                return None

        if trade.is_short:
            tp_price = trade.open_rate * (1 - (risk_pct * self.rr_target.value))
            if current_rate <= tp_price: return 'take_profit_rr_reached'
        else:
            tp_price = trade.open_rate * (1 + (risk_pct * self.rr_target.value))
            if current_rate >= tp_price: return 'take_profit_rr_reached'

        return None

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float, max_stake: float,
                            leverage: float, entry_tag: str, side: str, **kwargs) -> float:
        current_candle = kwargs.get('current_candle')
        if current_candle is None:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            current_candle = self._get_candle_at_or_before(dataframe, current_time)
        if current_candle is None: return min_stake

        st_line = current_candle['st_line']
        sl_distance_pct = abs(current_rate - st_line) / current_rate
        if sl_distance_pct < self.fee_buffer: sl_distance_pct = self.fee_buffer

        total_capital = self.wallets.get_total_stake_amount()
        if total_capital <= 0: return min_stake

        risk_amount = total_capital * self.portfolio_risk_pct
        position_size_needed = risk_amount / sl_distance_pct
        margin_needed = position_size_needed / leverage

        margin_needed = max(margin_needed, min_stake)
        margin_needed = min(margin_needed, max_stake)

        return margin_needed

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str, side: str,
                 **kwargs) -> float:
        current_candle = kwargs.get('current_candle')
        if current_candle is None:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            current_candle = self._get_candle_at_or_before(dataframe, current_time)
        if current_candle is None: return 1.0

        st_line = current_candle['st_line']
        sl_distance_pct = abs(current_rate - st_line) / current_rate
        if sl_distance_pct < self.fee_buffer: sl_distance_pct = self.fee_buffer

        total_capital = self.wallets.get_total_stake_amount()
        if total_capital <= 0: return 1.0

        max_open_trades = self.config.get('max_open_trades', 1)
        if max_open_trades == float('inf') or max_open_trades <= 0: max_open_trades = 1
        max_margin_per_trade = total_capital / max_open_trades

        risk_amount = total_capital * self.portfolio_risk_pct
        position_size_needed = risk_amount / sl_distance_pct
        calculated_leverage = position_size_needed / max_margin_per_trade

        calculated_leverage = min(calculated_leverage, self.max_allowed_leverage)
        calculated_leverage = max(calculated_leverage, 1.0)

        return round(calculated_leverage)