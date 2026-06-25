from abc import ABC

import numpy as np

import pandas as pd

import pandas_ta as pta

from datetime import datetime

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, CategoricalParameter

from freqtrade.strategy import merge_informative_pair, stoploss_from_absolute

from pandas import DataFrame

class MySupertrand_V5(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = '5m'
    can_short = True
    startup_candle_count = 100

    minimal_roi = {"0": 100}
    stoploss = -0.99

    st_period = 10
    st_multiplier = 3





    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        st = pta.supertrend(dataframe['high'], dataframe['low'], dataframe['close'], self.st_period, self.st_multiplier)
        dataframe["st_line"] = st[st.columns[0]]
        dataframe["st_dir"] = st[st.columns[1]]

        # --- ATR և Նախորդ Մոմերի Պատմություն ---
        dataframe['atr'] = pta.atr(dataframe['high'], dataframe['low'], dataframe['close'], length=14)
        dataframe['prev_high'] = dataframe['high'].shift(1)
        dataframe['prev_low'] = dataframe['low'].shift(1)

        # --- Դինամիկ Stop Loss-ի Գծեր ---
        dataframe['dynamic_sl_long'] = dataframe['prev_low'] - dataframe['atr']
        dataframe['dynamic_sl_short'] = dataframe['prev_high'] + dataframe['atr']

        # --- LONG Տրամաբանություն ---
        dataframe['trend_changed_to_long'] = np.where((dataframe['st_dir'] == 1) & (dataframe['st_dir'].shift(1) == -1),
                                                      True, False)
        dataframe['entry_price_anchor'] = np.nan
        dataframe.loc[dataframe['trend_changed_to_long'] == True, 'entry_price_anchor'] = dataframe['close']
        dataframe['entry_price_anchor'] = dataframe['entry_price_anchor'].ffill()

        dataframe['enter_long'] = 0
        dataframe.loc[
            (dataframe['st_dir'] == 1) & (dataframe['close'] <= dataframe['entry_price_anchor']), 'enter_long'] = 1

        # --- SHORT Տրամաբանություն ---
        dataframe['trend_changed_to_short'] = np.where(
            (dataframe['st_dir'] == -1) & (dataframe['st_dir'].shift(1) == 1), True, False)
        dataframe['short_entry_anchor'] = np.nan
        dataframe.loc[dataframe['trend_changed_to_short'] == True, 'short_entry_anchor'] = dataframe['close']
        dataframe['short_entry_anchor'] = dataframe['short_entry_anchor'].ffill()

        dataframe['enter_short'] = 0
        dataframe.loc[
            (dataframe['st_dir'] == -1) & (dataframe['close'] >= dataframe['short_entry_anchor']), 'enter_short'] = 1


        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Այստեղ գրում ենք գործարք բացելու (գնելու) պայմանները:
        """
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Այստեղ գրում ենք գործարքը փակելու (վաճառելու) պայմանները:
        """
        return dataframe