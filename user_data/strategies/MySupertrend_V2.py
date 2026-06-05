import numpy as np
import pandas as pd
import pandas_ta as pta
from datetime import datetime
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, CategoricalParameter
from freqtrade.strategy import merge_informative_pair, stoploss_from_absolute
from pandas import DataFrame

class MySupertrend_V2(IStrategy):
    """
    Supertrend Pullback Strategy (Long & Short)
    - Full Take Profit based on Dynamic Risk/Reward (1R)
    - Trend-change exit (Virtual Supertrend Cross)
    - Dynamic Stoploss based on local minimum/maximum
    """
    INTERFACE_VERSION = 3

    # =========================================================
    # 1. Գլոբալ Կարգավորումներ և Փոփոխականներ (Hyperopt Parameters)
    # =========================================================
    
    directional_mode = CategoricalParameter(['long_only', 'short_only', 'both'], default='both', space='buy')
    
    # Supertrend Պարամետրեր
    st_period = IntParameter(5, 30, default=10, space='buy')
    st_multiplier = DecimalParameter(1.0, 5.0, default=3.0, decimals=1, space='buy')
    st_virtual_offset = DecimalParameter(0.05, 0.30, default=0.01, decimals=2, space='buy') # Fakeout buffer
    
    # Proximity (Մոտիկության) & Engulfing
    proximity_threshold = DecimalParameter(0.0005, 0.0100, default=0.0050, decimals=4, space='buy') # 0.2%
    reversal_window = IntParameter(1, 5, default=5, space='buy')
    max_candle_size_pct = DecimalParameter(0.005, 0.030, default=0.010, decimals=3, space='buy') # 1.0%
    
    # Տրենդի Թեքություն (Slope)
    slope_candles = IntParameter(1, 10, default=10, space='buy')
    slope_min_pct = DecimalParameter(0.0001, 0.0050, default=0.0005, decimals=4, space='buy') # 0.05%
    
    # Ռիսկերի Կառավարում & Session
    sl_offset_pct = DecimalParameter(0.0001, 0.0020, default=0.01, decimals=4, space='sell') # 0.05% margin
    rr_target = DecimalParameter(1.5, 5.0, default=3.0, decimals=1, space='sell') # Risk/Reward (օր՝ 2.0 նշ. է 1:2 R/R)
    
    session_start_hour = IntParameter(0, 23, default=1, space='buy')
    session_end_hour = IntParameter(0, 23, default=23, space='buy')

    # Timeframes
    timeframe = '15m'
    informative_tf = '1h'

    # Freqtrade հիմնական կարգավորումներ
    minimal_roi = {"0": 100}  # ROI-ն անջատում ենք, կառավարումը թողնում ենք custom_exit-ին
    stoploss = -0.99          # Ստատիկ SL-ն անջատում ենք
    use_custom_stoploss = True

    def informative_pairs(self):
        """
        Սա ճիշտ և անվտանգ տարբերակն է Freqtrade-ի համար։
        Այն վերցնում է ընթացիկ ակտիվ զույգերը և ստեղծում HTF կապը։
        """
        # Եթե DataProvider-ը պատրաստ է, վերցնում ենք market_pairs-ը
        if self.dp:
            return [(pair, self.informative_tf) for pair in self.dp.market_pairs()]
        # Որպես ապահովագրություն, եթե դեռ չի բացվել
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # -----------------------------------------------------
        # 1. Բարձր TF Supertrend (Informative)
        # -----------------------------------------------------
        # Ուղղակի վերցնում ենք մեր սահմանած փոփոխականը՝ խուսափելով ավելորդ կանչերից
        inf_tf = self.informative_tf
        informative = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=inf_tf)
        
        htf_st = pta.supertrend(
            informative['high'], informative['low'], informative['close'], 
            length=self.st_period.value, multiplier=self.st_multiplier.value
        )
        informative['htf_st_dir'] = htf_st[htf_st.columns[1]]
        
        dataframe = merge_informative_pair(dataframe, informative, self.timeframe, inf_tf, ffill=True)
        self.htf_dir_col = f"htf_st_dir_{inf_tf}"
        
        # -----------------------------------------------------
        # 2. Հիմնական և Վիրտուալ Supertrend (Ընթացիկ TF)
        # -----------------------------------------------------
        st = pta.supertrend(
            dataframe['high'], dataframe['low'], dataframe['close'], 
            length=self.st_period.value, multiplier=self.st_multiplier.value
        )
        dataframe['st'] = st[st.columns[0]]
        dataframe['st_dir'] = st[st.columns[1]]

        # Վիրտուալ ST՝ fakeout-ներից և վաղաժամ տրենդի փոփոխությունից պաշտպանվելու համար
        virt_mult = self.st_multiplier.value * (1 + self.st_virtual_offset.value)
        st_virt = pta.supertrend(
            dataframe['high'], dataframe['low'], dataframe['close'], 
            length=self.st_period.value, multiplier=virt_mult
        )
        dataframe['st_virt'] = st_virt[st_virt.columns[0]]
        
        # -----------------------------------------------------
        # 3. Մոմերի Մաթեմատիկա և Կլանում (Engulfing)
        # -----------------------------------------------------
        dataframe['body_size_pct'] = abs(dataframe['close'] - dataframe['open']) / dataframe['open']
        dataframe['is_valid_size'] = dataframe['body_size_pct'] <= self.max_candle_size_pct.value

        dataframe['prev_open'] = dataframe['open'].shift(1)
        dataframe['prev_close'] = dataframe['close'].shift(1)
        dataframe['prev_high'] = dataframe['high'].shift(1)
        dataframe['prev_low'] = dataframe['low'].shift(1)

        # Bullish Engulfing
        dataframe['bullish_engulfing'] = (
            (dataframe['prev_close'] < dataframe['prev_open']) & 
            (dataframe['close'] > dataframe['open']) & 
            (dataframe['close'] > dataframe['prev_open']) & 
            (dataframe['open'] < dataframe['prev_close'])
        )

        # Bearish Engulfing
        dataframe['bearish_engulfing'] = (
            (dataframe['prev_close'] > dataframe['prev_open']) & 
            (dataframe['close'] < dataframe['open']) & 
            (dataframe['close'] < dataframe['prev_open']) & 
            (dataframe['open'] > dataframe['prev_close'])
        )

        # -----------------------------------------------------
        # 4. Proximity (Գոտուն մոտենալու հաշվարկ)
        # -----------------------------------------------------
        dist_long = (dataframe['low'] - dataframe['st']) / dataframe['st']
        dataframe['in_zone_long'] = (dataframe['st_dir'] == 1) & (dist_long > 0) & (dist_long <= self.proximity_threshold.value)
        dataframe['setup_long_valid'] = dataframe['in_zone_long'].rolling(window=self.reversal_window.value).max() > 0

        dist_short = (dataframe['st'] - dataframe['high']) / dataframe['st']
        dataframe['in_zone_short'] = (dataframe['st_dir'] == -1) & (dist_short > 0) & (dist_short <= self.proximity_threshold.value)
        dataframe['setup_short_valid'] = dataframe['in_zone_short'].rolling(window=self.reversal_window.value).max() > 0

        # -----------------------------------------------------
        # 5. Slope (Թեքության Հաշվարկ)
        # -----------------------------------------------------
        dataframe['st_shifted'] = dataframe['st'].shift(self.slope_candles.value)
        dataframe['slope_long_pct'] = (dataframe['st'] - dataframe['st_shifted']) / dataframe['st_shifted']
        dataframe['slope_short_pct'] = (dataframe['st_shifted'] - dataframe['st']) / dataframe['st_shifted']

        # -----------------------------------------------------
        # 6. Առևտրային Սեսիա (Ժամային Ֆիլտր)
        # -----------------------------------------------------
        hour = dataframe['date'].dt.hour
        start = self.session_start_hour.value
        end = self.session_end_hour.value
        if start < end:
            dataframe['active_session'] = (hour >= start) & (hour < end)
        else:
            dataframe['active_session'] = (hour >= start) | (hour < end)

        # -----------------------------------------------------
        # 7. Դինամիկ Stop Loss-ի նախապատրաստում
        # -----------------------------------------------------
        local_min = dataframe[['low', 'prev_low']].min(axis=1)
        dataframe['dynamic_sl_long'] = local_min * (1 - self.sl_offset_pct.value)
        
        local_max = dataframe[['high', 'prev_high']].max(axis=1)
        dataframe['dynamic_sl_short'] = local_max * (1 + self.sl_offset_pct.value)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # LONG ՊԱՅՄԱՆՆԵՐ
        if self.directional_mode.value in ['long_only', 'both']:
            dataframe.loc[
                (
                    dataframe['active_session'] &
                    dataframe['is_valid_size'] &
                    dataframe['bullish_engulfing'] &
                    dataframe['setup_long_valid'].shift(1) & 
                    (dataframe[self.htf_dir_col] == 1) &    
                    (dataframe['st_dir'] == 1) &            
                    (dataframe['slope_long_pct'] >= self.slope_min_pct.value)
                ),
                'enter_long'
            ] = 1

        # SHORT ՊԱՅՄԱՆՆԵՐ
        if self.directional_mode.value in ['short_only', 'both']:
            dataframe.loc[
                (
                    dataframe['active_session'] &
                    dataframe['is_valid_size'] &
                    dataframe['bearish_engulfing'] &
                    dataframe['setup_short_valid'].shift(1) & 
                    (dataframe[self.htf_dir_col] == -1) &    
                    (dataframe['st_dir'] == -1) &            
                    (dataframe['slope_short_pct'] >= self.slope_min_pct.value)
                ),
                'enter_short'
            ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # =========================================================
        # ՏՐԵՆԴԱՅԻՆ TRAILING ՍՏՈՊ (Exit on Trend Change)
        # =========================================================
        # Եթե գինը հակառակ ուղղությամբ հատում է Վիրտուալ Supertrend-ը, 
        # նշանակում է տրենդը կոտրվել է, և մենք շտապ փակում ենք դիրքը.
        
        dataframe.loc[
            (dataframe['close'] < dataframe['st_virt']), 'exit_long'
        ] = 1

        dataframe.loc[
            (dataframe['close'] > dataframe['st_virt']), 'exit_short'
        ] = 1

        return dataframe

    def custom_stoploss(self, pair: str, trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Պահպանում է մեր սկզբնական (անվտանգության) Stop Loss-ը, 
        եթե գինը կտրուկ ընկնի նախքան տրենդի կոտրվելը հաստատվի:
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        trade_candle = dataframe.loc[dataframe['date'] == trade.open_date_utc]

        if trade_candle.empty:
            return -0.99 

        if trade.is_short:
            sl_absolute_price = trade_candle['dynamic_sl_short'].values[0]
        else:
            sl_absolute_price = trade_candle['dynamic_sl_long'].values[0]

        return stoploss_from_absolute(sl_absolute_price, current_rate, is_short=trade.is_short)

    def custom_exit(self, pair: str, trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        """
        ԼՐԻՎ ՓԱԿՈՒՄ (FULL TAKE PROFIT) Դինամիկ R/R-ով:
        Գործարքը փակվում է, եթե հասնում է մեր նպատակային Risk/Reward հարաբերակցությանը:
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        trade_candle = dataframe.loc[dataframe['date'] == trade.open_date_utc]

        if trade_candle.empty:
            return None

        # 1. Ստանում ենք նախնական 1R-ի բացարձակ գինը
        if trade.is_short:
            sl_absolute_price = trade_candle['dynamic_sl_short'].values[0]
        else:
            sl_absolute_price = trade_candle['dynamic_sl_long'].values[0]

        # 2. Հաշվում ենք նախնական Ռիսկը (1R) արտահայտված տոկոսով
        risk_pct = abs(trade.open_rate - sl_absolute_price) / trade.open_rate

        # 3. Հաշվում ենք թիրախային շահույթը՝ բազմապատկելով rr_target-ով (օր՝ 2.0 = 1:2 R/R)
        target_profit_pct = risk_pct * self.rr_target.value

        # 4. Եթե ընթացիկ շահույթը (current_profit) հավասար կամ մեծ է թիրախից, փակում ենք այն
        if current_profit >= target_profit_pct:
            return f"Full_TP_Hit_{self.rr_target.value}RR"

        return None