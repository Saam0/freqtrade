from abc import ABC

import numpy as np

import pandas as pd

import pandas_ta as pta

from datetime import datetime

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, CategoricalParameter

from freqtrade.strategy import merge_informative_pair, stoploss_from_absolute

from pandas import DataFrame



class MySupertrand_V4(IStrategy):

    INTERFACE_VERSION = 3

    timeframe = '15m'
    can_short = True
    startup_candle_count = 100


    minimal_roi = {"0": 100}
    stoploss = -0.99

    # HYPEROPT ՊԱՐԱՄԵՏՐԵՐ
    directional_mode = CategoricalParameter(['long_only', 'short_only', 'both'], default='both', space='buy')

        # --- Supertrend-ի կարգավորումներ ---
    st_period = IntParameter(5, 30, default=10, space='buy')
    st_multiplier = DecimalParameter(1.0, 5.0, default=1, decimals=2, space='buy')

    pullback_max_dist = DecimalParameter(0.001, 0.020, default=0.002, decimals=3, space="buy")






    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        st = pta.supertrend(dataframe['high'], dataframe['low'], dataframe['close'], self.st_period.value, self.st_multiplier.value)
        dir_col = f'SUPERd_{self.st_period.value}_{self.st_multiplier.value}'
        line_col = f'SUPERT_{self.st_period.value}_{self.st_multiplier.value}'

        dataframe["st_dir"] = st[dir_col]
        dataframe["st_line"] = st[line_col]

        # Pullback հեռավորություն
        dataframe["st_dist"] = abs(dataframe["close"] - dataframe["st_line"])

        # Գործարք բացելու համար թույլատրելի հեռավորության պայմանը
        dataframe["pullback_ok"] = dataframe["st_dist"] <= self.pullback_max_dist.value

        dataframe["pullback_long"] = (
                (dataframe["low"] < dataframe["st_line"]) &
                (dataframe["close"] > dataframe["st_line"]) &
                (dataframe["st_dir"] == 1)
        )

        dataframe["pullback_short"] = (
                (dataframe["high"] > dataframe["st_line"]) &
                (dataframe["close"] < dataframe["st_line"]) &
                (dataframe["st_dir"] == -1)
        )


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
