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

    timeframe = '5m'
    can_short = True
    startup_candle_count = 100

    minimal_roi = {"0": 100}
    stoploss = -0.99

    # HYPEROPT ՊԱՐԱՄԵՏՐԵՐ
    directional_mode = CategoricalParameter(['long_only', 'short_only', 'both'], default='both', space='buy')

    # --- Supertrend-ի կարգավորումներ ---
    st_period = IntParameter(5, 30, default=10, space='buy')
    st_multiplier = DecimalParameter(1.0, 5.0, default=2.0, decimals=1, space='buy')

    pullback_max_dist = DecimalParameter(0.001, 0.020, default=0.0003, decimals=4, space="buy")

    # --- ՆՈՐ: Հիշողության բառարան՝ նամակների սպամից խուսափելու համար ---
    custom_alerts_sent = {}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        st = pta.supertrend(dataframe['high'], dataframe['low'], dataframe['close'], self.st_period.value,
                            self.st_multiplier.value)
        # dir_col = f'SUPERd_{self.st_period.value}_{self.st_multiplier.value}'
        # line_col = f'SUPERT_{self.st_period.value}_{self.st_multiplier.value}'
        #
        # dataframe["st_dir"] = st[dir_col]
        # dataframe["st_line"] = st[line_col]

        # ԱՄԵՆԱԱՆՎՏԱՆԳ ՏԱՐԲԵՐԱԿԸ (առանց անուններ գուշակելու)
        dataframe["st_line"] = st[st.columns[0]]
        dataframe["st_dir"] = st[st.columns[1]]

        # Pullback հեռավորություն
        dataframe["st_dist"] = abs(dataframe["close"] - dataframe["st_line"]) / dataframe["st_line"]

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

        # ======================================================================
        # ԻՐԱԿԱՆ ԺԱՄԱՆԱԿԻ TELEGRAM ԾԱՆՈՒՑՈՒՄՆԵՐ (send_msg մեթոդով)
        # ======================================================================
        # 1. Համոզվում ենք, որ բոտը գտնվում է իրական կամ դեմո ռեժիմում (որ backtest-ի ժամանակ չաշխատի)
        if self.dp and self.dp.runmode.value in ('dry_run', 'live'):
            last_candle = dataframe.iloc[-1]
            pair = metadata['pair']
            current_candle_time = last_candle['date']

            # 2. Ստուգում ենք, թե արդյոք այս նույն ժամի մոմի համար արդեն ուղարկե՞լ ենք նամակ
            if self.custom_alerts_sent.get(pair) != current_candle_time:

                # 3. Եթե մտել է գոտի (կամ ծակել է գիծը)
                if last_candle['pullback_ok'] or last_candle['pullback_long'] or last_candle['pullback_short']:
                    clean_pair = pair.split(':')[0]
                    st_line = round(last_candle['st_line'], 2)
                    close_price = round(last_candle['close'], 2)
                    # Բազմապատկում ենք 100-ով և կլորացնում տոկոսը գեղեցիկ ցուցադրելու համար
                    dist_pct = round(last_candle['st_dist'] * 100, 2)

                    if last_candle['st_dir'] == 1:
                        msg = (
                            f"👀 *[ZONE APPROACH - LONG]*\n"
                            f"🔸 *Ակտիվ:* #{clean_pair}\n"
                            f"📈 *Տրենդ:* ԱՃՈՂ (Bullish)\n"
                            f"🎯 *Գինը մտել է մոտեցման գոտի!*\n"
                            f"📊 *Հեռավորությունը:* {dist_pct}%\n"
                            f"💵 *Ընթացիկ գին:* {close_price}\n"
                            f"🟢 *Supertrend:* {st_line}"
                        )
                        self.dp.send_msg(msg)
                        self.custom_alerts_sent[pair] = current_candle_time

                    elif last_candle['st_dir'] == -1:
                        msg = (
                            f"👀 *[ZONE APPROACH - SHORT]*\n"
                            f"🔸 *Ակտիվ:* #{clean_pair}\n"
                            f"📉 *Տրենդ:* ԱՆԿՈՒՄԱՅԻՆ (Bearish)\n"
                            f"🎯 *Գինը մտել է մոտեցման գոտի!*\n"
                            f"📊 *Հեռավորությունը:* {dist_pct}%\n"
                            f"💵 *Ընթացիկ գին:* {close_price}\n"
                            f"🔴 *Supertrend:* {st_line}"
                        )
                        self.dp.send_msg(msg)
                        self.custom_alerts_sent[pair] = current_candle_time

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

