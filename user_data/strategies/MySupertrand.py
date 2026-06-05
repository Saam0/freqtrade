# =========================================================================================
# ԳՐԱԴԱՐԱՆՆԵՐԻ ՆԵՐՄՈՒԾՈՒՄ (Imports - ինչպես Java-ի import-ները)
# =========================================================================================
import pandas as pd  
# pandas-ը տվյալների վերլուծության գլխավոր գործիքն է: Այն ստեղծում է DataFrame (վիրտուալ Excel աղյուսակ):

import pandas_ta as ta 
# pandas_ta-ն ինդիկատորների գրադարան է (Technical Analysis): Պարունակում է Supertrend, RSI, MACD և այլն:

from datetime import datetime 
# datetime-ը ժամանակի հետ աշխատելու համար է (պետք է գալիս դինամիկ ելքի ֆունկցիայում):

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter 
# Freqtrade-ի հիմնական գործիքներն են. IStrategy-ն բազային կլասն է (Interface), իսկ Parameter-ները՝ Hyperopt-ի համար:

from freqtrade.persistence import Trade 
# Trade-ը պարունակում է արդեն բացված գործարքի տվյալները (գին, ժամանակ, շահույթ): Ինչպես Entity-ն Java Spring-ում:


# =========================================================================================
# ՌԱԶՄԱՎԱՐՈՒԹՅԱՆ ԿԼԱՍԸ (Ժառանգում ենք Freqtrade-ի IStrategy-ից)
# =========================================================================================
class MySupertrend(IStrategy):
    """
    Այս ռազմավարությունը գտնում է տրենդը (Supertrend), սպասում է որ այն հասունանա (օրինակ՝ 10 մոմ),
    ապա սպասում է գնի հետքաշման (Pullback) դեպի տրենդի գիծը և նոր միայն գնում է:
    """
    
    # -------------------------------------------------------------------------------------
    # 1. ԲԱԶԱՅԻՆ ԿԱՆՈՆՆԵՐ (Գլխավոր կարգավորումներ)
    # -------------------------------------------------------------------------------------
    INTERFACE_VERSION = 3         # Օգտագործում ենք Freqtrade-ի շարժիչի նորագույն տարբերակը
    timeframe = '5m'              # Աշխատում ենք 5 րոպեանոց մոմերի (candles) գրաֆիկի վրա
    can_short = True              # Թույլատրում ենք և՛ գնել (Long), և՛ վաճառել գնանկման վրա (Short)
    use_custom_stoploss = True    # Բոտին ասում ենք. «Լսիր իմ գրած custom_exit ֆունկցիային»
    startup_candle_count = 100    # Բոտին խնդրում ենք բեռնել անցյալի 100 մոմ, որ ինդիկատորը ճիշտ հաշվարկվի


    # -------------------------------------------------------------------------------------
    # 2. ՍՏԱՆԴԱՐՏ ԵԼՔԵՐԻ ԱՆՋԱՏՈՒՄ (Որպեսզի չխանգարեն մեր 1% ռիսկի կանոնին)
    # -------------------------------------------------------------------------------------
    minimal_roi = {"0": 100}  # Ստանդարտ շահույթը դնում ենք 100%, որպեսզի բոտը երբեք ավտոմատ չփակի պլյուսը
    stoploss = -0.99          # Ստանդարտ վնասը դնում ենք -99%, որպեսզի բոտը երբեք ավտոմատ չփակի մինուսը


    # -------------------------------------------------------------------------------------
    # 3. HYPEROPT ՊԱՐԱՄԵՏՐԵՐ (Փոփոխականներ, որոնք ապագայում բոտը ինքը կօպտիմիզացնի)
    # -------------------------------------------------------------------------------------
    # Supertrend ինդիկատորի կարգավորումներ.
    # IntParameter (Ամբողջ թիվ). փնտրել 5-ից 20 միջակայքում, լռելյայնը՝ 10:
    st_length = IntParameter(5, 20, default=10, space="indicator")
    # DecimalParameter (Կոտորակային թիվ). փնտրել 1.5-ից 5.0 միջակայքում, լռելյայնը՝ 3.0:
    st_multiplier = DecimalParameter(1.5, 5.0, default=3.0, decimals=1, space="indicator")

    # Մուտքի որոշման կարգավորումներ.
    # Քանի՞ մոմ սպասենք, որ տրենդը հաստատվի (հասունանա):
    trend_maturity_candles = IntParameter(2, 20, default=25, space="buy")
    # Մաքսիմում քանի՞ տոկոսով կարող է գինը հեռու լինել գծից (Pullback-ի թույլատրելի չափը):
    pullback_max_dist = DecimalParameter(0.001, 0.020, default=0.002, decimals=3, space="buy")

    # Ելքի (Շահույթի) կարգավորում.
    # Քանի՞ անգամ շահույթը պետք է մեծ լինի վնասից (Ռիսկ/Շահույթ կամ R:R):
    rr_target = DecimalParameter(1.0, 15.0, default=3.0, decimals=1, space="sell")


    # Քանի՞ անգամ կարող ենք մտնել նույն տրենդի մեջ (փնտրել 1-ից 3 միջակայքում, լռելյայն՝ 1)
    max_trades_per_trend = IntParameter(1, 3, default=1, space="buy")
    
    # ՊԱՏՈՒՀԱՆԻ ՏԵՎՈՂՈՒԹՅՈՒՆ (Duration). 
    # Քանի՞ մոմ բաց մնա հնարավորության պատուհանը հասունանալուց հետո:
    # Փնտրել 5-ից 30 մոմ տևողության միջակայքում, լռելյայն՝ 15:
    trend_window_candles = IntParameter(5, 300, default=10, space="buy")


    # -------------------------------------------------------------------------------------
    # 4. ԻՆԴԻԿԱՏՈՐՆԵՐ (Բոտի "Աչքերը" - Այստեղ ստեղծում ենք նոր սյունակներ աղյուսակում)
    # -------------------------------------------------------------------------------------
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        
        # 1. Հաշվում ենք Supertrend-ը (Սա մնում է նույնը)
        st = ta.supertrend(dataframe['high'], dataframe['low'], dataframe['close'], 
                           length=self.st_length.value, multiplier=self.st_multiplier.value)
        dir_col = f'SUPERTd_{self.st_length.value}_{self.st_multiplier.value}'
        line_col = f'SUPERT_{self.st_length.value}_{self.st_multiplier.value}'
        
        dataframe['st_dir'] = st[dir_col]
        dataframe['st_line'] = st[line_col]
        
        # 2. Pullback հեռավորություն (Սա ևս ունեինք)
        dataframe['st_dist'] = abs(dataframe['close'] - dataframe['st_line']) / dataframe['st_line']

        # -------------------------------------------------------------------------
        # ՆՈՐ ԲԼՈԿ. ՌԻՍԿԻ ՀԱՇՎԱՐԿԻ ՆԱԽԱՊԱՏՐԱՍՏՈՒՄ
        # -------------------------------------------------------------------------
        # Ենթադրյալ միջնորդավճար (Fee). 0.1% մուտքի համար + 0.1% ելքի համար = 0.2% (0.002)
        estimated_fee = 0.002 
        
        # Հաշվում ենք իրական Stop Loss տոկոսը գումարած բորսայի միջնորդավճարը:
        # st_dist-ը հենց մեր մաքուր հեռավորությունն է գծից դրական թվով:
        # Սա վեկտորիզացված գործողություն է՝ գումարումը արվում է միանգամից ամբողջ սյունակի համար:
        dataframe['sl_percent'] = dataframe['st_dist'] + estimated_fee

        # Ապահովագրություն. Որպեսզի զրոյի բաժանում (Divide by Zero) կամ անվերջ լծակ չստանանք, 
        # եթե գինը և գիծը 100% համընկնեն, մենք դնում ենք մինիմալ սահմանափակում (օրինակ՝ 0.3%):
        # dataframe['sl_percent'].clip(lower=0.003) նշանակում է՝ "եթե թիվը 0.003-ից փոքր է, սարքիր այն 0.003":
        dataframe['sl_percent'] = dataframe['sl_percent'].clip(lower=0.003)
        # -------------------------------------------------------------------------

        # 3. Տրենդի տարիքի հաշվարկ (Մնում է նույնը)
        dataframe['trend_change'] = (dataframe['st_dir'] != dataframe['st_dir'].shift(1))
        dataframe['trend_id'] = dataframe['trend_change'].cumsum()
        dataframe['bars_in_trend'] = dataframe.groupby('trend_id').cumcount()

        return dataframe



    # -------------------------------------------------------------------------------------
    # 5. ՄՈՒՏՔԻ ՊԱՅՄԱՆՆԵՐ (Որոշումներ կայացնող "Ուղեղը")
    # -------------------------------------------------------------------------------------
    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        
        # [ՆՈՐ ՍԻՆՏԱՔՍԻ ԲԱՑԱՏՐՈՒԹՅՈՒՆ]
        # Այստեղ մենք դինամիկ հաշվում ենք "endTime"-ը:
        # Սկիզբ (օրինակ՝ 10) + Տևողություն (օրինակ՝ 15) = Մաքսիմում թույլատրելի տարիք (25)
        max_trend_age = self.trend_maturity_candles.value + self.trend_window_candles.value

        # ==========================================
        # LONG ԼՈԳԻԿԱ (ԳՆԱՃ)
        # ==========================================
        is_valid_long = (
            (dataframe['st_dir'] == 1) & 
            # Պատուհանի ՍԿԻԶԲ
            (dataframe['bars_in_trend'] >= self.trend_maturity_candles.value) & 
            # Պատուհանի ԱՎԱՐՏ (օգտագործում ենք վերևում հաշված դինամիկ թիվը)
            (dataframe['bars_in_trend'] <= max_trend_age) & 
            (dataframe['st_dist'] <= self.pullback_max_dist.value)
        )
        
        dataframe['temp_long_signal'] = is_valid_long.astype(int)
        dataframe['long_signal_count'] = dataframe.groupby('trend_id')['temp_long_signal'].cumsum()
        
        dataframe.loc[
            (dataframe['temp_long_signal'] == 1) & 
            (dataframe['long_signal_count'] <= self.max_trades_per_trend.value),
            'enter_long'
        ] = 1


        # ==========================================
        # SHORT ԼՈԳԻԿԱ (ԳՆԱՆԿՈՒՄ)
        # ==========================================
        is_valid_short = (
            (dataframe['st_dir'] == -1) & 
            # Պատուհանի ՍԿԻԶԲ
            (dataframe['bars_in_trend'] >= self.trend_maturity_candles.value) & 
            # Պատուհանի ԱՎԱՐՏ
            (dataframe['bars_in_trend'] <= max_trend_age) & 
            (dataframe['st_dist'] <= self.pullback_max_dist.value)
        )
        
        dataframe['temp_short_signal'] = is_valid_short.astype(int)
        dataframe['short_signal_count'] = dataframe.groupby('trend_id')['temp_short_signal'].cumsum()
        
        dataframe.loc[
            (dataframe['temp_short_signal'] == 1) & 
            (dataframe['short_signal_count'] <= self.max_trades_per_trend.value),
            'enter_short'
        ] = 1

        return dataframe

    # -------------------------------------------------------------------------------------
    # 6. ԵԼՔԻ ՍՏԱՆԴԱՐՏ ՊԱՅՄԱՆՆԵՐ (Տրենդի շրջադարձ)
    # -------------------------------------------------------------------------------------
    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        
        # Եթե մենք LONG ենք բացել (գնել ենք), բայց գույնը հանկարծ դարձավ կարմիր (-1)
        dataframe.loc[
            (dataframe['st_dir'] == -1),
            'exit_long'] = 1   # Շտապ վաճառում ենք

        # Եթե մենք SHORT ենք բացել, բայց գույնը դարձավ կանաչ (1)
        dataframe.loc[
            (dataframe['st_dir'] == 1),
            'exit_short'] = 1  # Շտապ փակում ենք

        return dataframe


    # -------------------------------------------------------------------------------------
    # 7. ԴԻՆԱՄԻԿ ԵԼՔ (Անընդհատ աշխատող Risk Management / Event Listener)
    # -------------------------------------------------------------------------------------
    def custom_exit(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs):
        """
        Այս ֆունկցիան չի օգտագործում DataFrame: Այն աշխատում է անհատապես ամեն մի գործարքի վրա՝ 
        իրական ժամանակում ստուգելով տոկոսները ամեն անգամ, երբ գինը փոխվում է:
        """
        
        # Հաշվում ենք մեր Շահույթի թիրախը (Take Profit).
        # Բազային վնասը 1% է (0.01): Բազմապատկում ենք մեր դրած R:R պարամետրով (օրինակ՝ 3.0)
        take_profit_target = 0.01 * self.rr_target.value
        
        # Եթե ընթացիկ շահույթը (մուտքի գնից հաշված) հասավ մեր թիրախին (օրինակ՝ +3%)
        if current_profit >= take_profit_target:
            return "take_profit_hit"  # Բոտը փակում է գործարքը և լոգերում գրում է այս բառը
            
        # Եթե գինը գնաց մեր դեմ, և մենք ունենք խիստ 1% վնաս (-0.01)
        if current_profit <= -0.01:
            return "stop_loss_hit"    # Բոտը կանխում է մեծ վնասը և փակում գործարքը

        # Եթե գինը մեջտեղում է, վերադարձնում ենք None (նույնն է ինչ Java-ում null)
        # Դա բոտին հուշում է, որ դեռ պետք է սպասել:
        return None
    
    # ------------------------------------
    # 8. ԼԾԱԿԻ ԴԻՆԱՄԻԿ ՀԱՇՎԱՐԿ (Leverage)
    # ------------------------------------
    def leverage(self, pair: str, current_time: 'datetime', current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str, side: str,
                 **kwargs) -> float:
        """
        Այս ֆունկցիան հաշվարկում է, թե քանի անգամ է պետք մեծացնել մեր գումարը,
        որպեսզի փոքր Stop Loss-ի դեպքում կարողանանք վաստակել (կամ կորցնել) մեր ուզած 1%-ը:
        """
        
        # 1. Դիմում ենք Data Provider-ին (մեր "Repository"-ին) և խնդրում ենք այս կոպեկի աղյուսակը
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        # 2. Վերցնում ենք աղյուսակի ամենավերջին տողը (այս պահին ընթացող մոմը):
        # Python-ում (Pandas-ում) .iloc-ը (Index Location) ցույց է տալիս տողի համարը: 
        # -1 նշանակում է "վերջից առաջինը" կամ ամենավերջինը:
        last_candle = dataframe.iloc[-1].squeeze()
        
        # 3. Վերջին մոմից վերցնում ենք մեր հաշվարկած Stop Loss-ի տոկոսը (Օրինակ՝ 0.002 կամ 0.2%)
        sl_percent = last_candle['sl_percent']
        
        # 4. ՄԱԹԵՄԱՏԻԿԱ. 
        # Եթե մենք ուզում ենք ռիսկի ենթարկել 1% (0.01), ապա պահանջվող լծակը հավասար է՝
        # Լծակ = Ռիսկի Տոկոս / Stop Loss-ի Տոկոս
        # Օրինակ՝ 0.01 / 0.002 = 5.0 (Այսինքն՝ 5x լծակ)
        desired_leverage = 0.01 / sl_percent
        
        # 5. Ապահովություն. Բորսաները ունեն մաքսիմալ լծակի սահմանափակում (max_leverage, օրինակ 20x):
        # Ինչպես նաև, լծակը երբեք չի կարող լինել 1.0-ից փոքր:
        # min() և max() ֆունկցիաները ապահովում են, որ մեր թիվը մնա այս սահմաններում:
        actual_leverage = max(1.0, min(desired_leverage, max_leverage))
        
        return actual_leverage # Վերադարձնում ենք բորսային հասկանալի թիվը (օրինակ՝ 5.0)
    
    # ------------------------------------
    # 9. ԳՈՐԾԱՐՔԻ ԳՈՒՄԱՐ (Custom Stake Amount)
    # ------------------------------------
    def custom_stake_amount(self, pair: str, current_time: 'datetime', current_rate: float,
                            proposed_stake: float, min_stake: float, max_stake: float,
                            leverage: float, entry_tag: str, side: str,
                            **kwargs) -> float:
        """
        Որոշում է, թե քանի դոլար մեր անձնական գումարից դնենք այս գործարքի մեջ, 
        որպեսզի Stop Loss-ի հարվածի դեպքում կորցնենք դեպոզիտի ճիշտ 1%-ը:
        """
        
        # 1. Նորից վերցնում ենք աղյուսակը և վերջին մոմի Stop Loss-ի տոկոսը
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        sl_percent = last_candle['sl_percent']
        
        # 2. Որոշում ենք, թե ընդհանուր քանի՞ դոլար ունենք մեր հաշվին (Wallet Balance)
        # self.wallets-ը Freqtrade-ի գործիքն է՝ դրամապանակի տվյալները ստանալու համար:
        total_capital = self.wallets.get_total_stake_amount()
        
        # 3. Հաշվում ենք ռիսկի գումարը դոլարով (օրինակ՝ $1000-ի 1%-ը = $10 վնաս)
        risk_amount = total_capital * 0.01
        
        # 4. Հաշվում ենք ԸՆԴՀԱՆՈՒՐ գործարքի ծավալը (Total Position Size),
        # որն անհրաժեշտ է, որպեսզի sl_percent շարժման դեպքում կորցնենք risk_amount-ը:
        # Օրինակ՝ $10 / 0.002 = $5000: Մեզ պետք է բացել $5000-անոց գործարք:
        total_position = risk_amount / sl_percent
        
        # 5. Վերջնական հաշվարկ մեր գրպանի համար. 
        # Քանի որ մենք օգտագործում ենք լծակ (leverage), մենք չենք վճարում ամբողջ $5000-ը:
        # Մենք վճարում ենք = Ընդհանուր Ծավալ / Լծակ
        # Օրինակ՝ $5000 / 5x = $1000 մեր անձնական գումարից (Margin):
        stake_amount = total_position / leverage
        
        # Վերադարձնում ենք այն գումարը, որը բոտը պետք է վերցնի դրամապանակից:
        return stake_amount