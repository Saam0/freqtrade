from abc import ABC

import numpy as np

import pandas as pd

import pandas_ta as pta

from datetime import datetime

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, CategoricalParameter

from freqtrade.strategy import merge_informative_pair, stoploss_from_absolute

from pandas import DataFrame

class MySupertrand_V6(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = '15m'
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