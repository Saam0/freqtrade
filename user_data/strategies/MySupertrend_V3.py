# =====================================================================================
# ԲԼՈԿ 1. ՆԵՐՄՈՒԾՈՒՄՆԵՐ ԵՎ ՀԻՄՆԱԿԱՆ ԿԱՐԳԱՎՈՐՈՒՄՆԵՐ
# =====================================================================================

# 1. ԳՐԱԴԱՐԱՆՆԵՐԻ ՆԵՐՄՈՒԾՈՒՄ (Imports)
# -------------------------------------------------------------------------------------
# Մեզ պետք է numpy-ը բարդ մաթեմատիկական հաշվարկների համար (օրինակ՝ զանգվածների մինիմում/մաքսիմում գտնելու)
import numpy as np

# Pandas-ը Python-ում աղյուսակների (Dataframe) հետ աշխատելու «Աստվածն» է:
# Բորսայից եկող բոլոր մոմերը պահվում են Pandas-ի աղյուսակներում:
import pandas as pd

# Pandas_TA-ն հատուկ գրադարան է, որի մեջ պատրաստի կան առևտրային ինդիկատորները, այդ թվում՝ Supertrend-ը:
import pandas_ta as pta

# Ժամանակի հետ աշխատելու համար, որպեսզի բոտը հասկանա, թե որ ժամին է բացվում մոմը:
from datetime import datetime

# Սրանք Freqtrade-ի «ուղեղի» մասերն են:
# IStrategy-ն բազային դասն է, իսկ Parameter-ները պետք են, որ ապագայում բոտը ինքը գտնի ճիշտ թվերը (Hyperopt):
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, CategoricalParameter

# Մեզ պետք են այս երկու հատուկ գործիքները Freqtrade-ից:
# Առաջինը միացնում է տարբեր թայմֆրեյմներ (օր՝ 15m և 1h), իսկ երկրորդը կառավարում է Դինամիկ Stop Loss-ը:
from freqtrade.strategy import merge_informative_pair, stoploss_from_absolute

# Որպեսզի կոդում հստակ նշենք, որ աշխատում ենք DataFrame տիպի տվյալների հետ:
from pandas import DataFrame


# 2. ՍՏՐԱՏԵԳԻԱՅԻ ԴԱՍԻ ՍՏԵՂԾՈՒՄ (Class Definition)
# -------------------------------------------------------------------------------------
# Անունը պարտադիր պետք է լինի նույնը, ինչ ֆայլի անունը (օրինակ՝ MySupertrend_V2.py):
class MySupertrend_V3(IStrategy):
    # Բոտին ասում ենք, որ օգտագործի Freqtrade-ի ամենավերջին և խելացի շարժիչը (տարբերակ 3)
    INTERFACE_VERSION = 3

    # 3. ԲԱԶԱՅԻՆ ԵՎ ՏԵԽՆԻԿԱԿԱՆ ԿԱՐԳԱՎՈՐՈՒՄՆԵՐ
    # -------------------------------------------------------------------------------------
    # Աշխատում ենք 15 րոպեանոց գրաֆիկի վրա (տակտիկական մուտքեր գտնելու համար)
    timeframe = '15m'

    # Բարձր թայմֆրեյմը, որով հասկանալու ենք մեծ տրենդի ուղղությունը (մակրո վերլուծություն)
    informative_tf = '15m'

    # ՊԱՇՏՈՆԱԿԱՆ ԳՐԱՆՑՈՒՄ. Ստեղծում ենք սյունակի դինամիկ անունը գլխավոր բլոկում
    htf_dir_col = f"htf_st_dir_{informative_tf}"

    # Քանի որ ստրատեգիան և' գնում է (Long), և' վաճառում (Short), այս ֆունկցիան պարտադիր միացնում ենք
    can_short = True

    # Բոտին խնդրում ենք բեռնել անցյալի 100 մոմ հենց սկզբից, որպեսզի Supertrend-ը հասցնի հաշվարկվել
    startup_candle_count = 100

    # Բոտին ասում ենք. «Դինամիկ Stop Loss-ը կկառավարեմ ես՝ իմ գրած custom_stoploss ֆունկցիայով»
    use_custom_stoploss = True

    # 4. ՍՏԱՆԴԱՐՏ ԵԼՔԵՐԻ ԱՆՋԱՏՈՒՄ (Որպեսզի բոտը չխառնվի մեր պլաններին)
    # -------------------------------------------------------------------------------------
    # Ստանդարտ շահույթը դնում ենք 100%, որպեսզի բոտը երբեք ավտոմատ չփակի պլյուսը առանց մեր հրամանի
    minimal_roi = {"0": 100}

    # Ստանդարտ վնասը դնում ենք -99%: Մենք ունենք մեր խելացի Stop Loss-ը, սա ուղղակի անվտանգության համար է:
    stoploss = -0.99

    # 5. HYPEROPT ՊԱՐԱՄԵՏՐԵՐ (Փոփոխականներ, որոնք բոտը կօպտիմիզացնի AI-ի միջոցով)
    # -------------------------------------------------------------------------------------

    # --- Ուղղության կարգավորում ---
    # Արդյոք թույլատրե՞լ միայն Long, միայն Short, թե երկուսն էլ: (Բոտը կգտնի ամենաշահավետը)
    directional_mode = CategoricalParameter(['long_only', 'short_only', 'both'], default='both', space='buy')

    # --- Supertrend-ի կարգավորումներ ---
    # Ինդիկատորի ժամանակահատվածը (փնտրել 5-ից 30-ի միջև, լռելյայնը՝ 10)
    st_period = IntParameter(5, 30, default=10, space='buy')
    # Ինդիկատորի բազմապատկիչը կամ հեռավորությունը գնից (փնտրել 1.0-ից 5.0-ի միջև, լռելյայն՝ 3.0)
    st_multiplier = DecimalParameter(1.0, 5.0, default=1, decimals=2, space='buy')
    # Վիրտուալ Supertrend-ի բուֆերը՝ կեղծ ճեղքումներից (Fakeouts) պաշտպանվելու համար (10% = 0.10)
    st_virtual_offset = DecimalParameter(0.05, 0.30, default=0.00, decimals=2, space='buy')

    # --- Մուտքի և Շրջադարձի կարգավորումներ (Pullback & Reversal) ---
    # Որքա՞ն մոտ պետք է լինի գինը տրենդին, որ համարենք հպում (0.002 = 0.2% հեռավորություն)
    proximity_threshold = DecimalParameter(0.0005, 0.0100, default=0.0020, decimals=4, space='buy')
    # Քանի՞ մոմ հետ նայենք հպումը գտնելու համար:
    reversal_window = IntParameter(1, 5, default=3, space='buy')
    # Քանի՞ ATR կարող է լինել մոմի մարմինը առավելագույնը:
    # 2.5 նշանակում է՝ մոմը չպետք է լինի ակտիվի միջին մոմից 2.5 անգամ ավելի մեծ (պաշտպանում է վերջնական ուժասպառված գներից):
    max_candle_atr_mult = DecimalParameter(1.5, 5.0, default=2.0, decimals=1, space='buy')

    # --- Տրենդի թեքության և ուժի կարգավորում (Slope) ---
    # Քանի՞ մոմ հետ նայենք թեքությունը հաշվելու համար
    slope_candles = IntParameter(1, 100, default=1, space='buy')
    # Որքա՞ն պետք է լինի նվազագույն թեքությունը (որ չմտնենք հորիզոնական ֆլեթ շուկա)
    slope_min_pct = DecimalParameter(0.0001, 0.0050, default=0.0050, decimals=4, space='buy')

    # --- Ռիսկի և Շահույթի կառավարում (Risk Management) ---
    # Stop Loss-ի պաշտպանիչ հեռավորությունը տեղական մինիմումից (0.05% անվտանգության մարժա)
    sl_offset_pct = DecimalParameter(0.0001, 0.0020, default=0.0005, decimals=4, space='sell')
    # Որքա՞ն կարող է լինել առավելագույն թույլատրելի ռիսկը (Stop Loss-ի հեռավորությունը):
    # Եթե պոչը խելագար երկար է և ռիսկը մեծ է 2%-ից (0.02), մենք մերժում ենք գործարքը:
    max_risk_pct = DecimalParameter(0.010, 0.050, default=0.020, decimals=3, space='buy')
    # Նպատակային շահույթի գործակիցը (2.0 նշանակում է շահույթը երկու անգամ մեծ է ռիսկից՝ 1:2 R/R)
    rr_target = DecimalParameter(1.5, 5.0, default=3.0, decimals=1, space='sell')
    # Որքա՞ն է մեր նպատակային ռիսկը յուրաքանչյուր գործարքի համար (0.01 = 1%)
    target_risk_pct = DecimalParameter(0.005, 0.050, default=0.01, decimals=3, space='buy')

    # --- Առևտրային ժամերի ֆիլտր (Session Limits) ---
    # Մենք ինքներս ենք որոշում թույլատրված ժամերը (UTC-ով), Hyperopt-ը սրան չի կպնի:
    # 0-ն գիշերվա 00:00-ն է
    allowed_hours = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]

    # Բացառիկ զույգեր և նրանց անհատական սեսիաները (գրված մարդկային ժամերով)
    custom_sessions = {
        # "BTC/USDT": {"start": "17:45", "end": "19:10"},
        # Կարող ես ավելացնել անսահմանափակ քանակի այլ զույգեր, օրինակ՝
        # "ETH/USDT": {"start": "08:30", "end": "10:15"}
    }

    # --- Գրաֆիկական Վիզուալիզացիայի Կարգավորումներ (Plot Config) ---
    plot_config = {
        'main_plot': {
            # Ջնջել ենք միագույն 'st'-ն և փոխարինել մեր երկու նոր գունավոր գծերով
            'st_green': {'color': 'green'},
            'st_red': {'color': 'red'},

            'st_virt': {'color': 'lightblue'},

            # Stop Loss գծերը դարձնում ենք նարնջագույն, որ տարբերվեն Տրենդի կարմիրից
            'dynamic_sl_long': {'color': 'orange'},
            'dynamic_sl_short': {'color': 'orange'},
        },
        'subplots': {
            "ATR (Volatility)": {
                'atr': {'color': 'teal'},
            }
        }
    }

    # =====================================================================================
    # ԲԼՈԿ 2. ՏՎՅԱԼՆԵՐԻ ՆԵՐԲԵՌՆՈՒՄ, ԻՆԴԻԿԱՏՈՐՆԵՐ ԵՎ ԺԱՄԱՆԱԿԻ ՖԻԼՏՐԱՑԻԱ
    # =====================================================================================

    # 6. ԲԱՐՁՐ ԹԱՅՄՖՐԵՅՄԻ (HTF) ՏՎՅԱԼՆԵՐԻ ՊԱՏՎԻՐՈՒՄ
    # -------------------------------------------------------------------------------------
    def informative_pairs(self):
        """
        Բոտին ասում ենք, որ մեզ միայն 15 րոպեանոց գրաֆիկը բավարար չէ:
        Մենք ուզում ենք տեսնել նաև մակրո տրենդը (1h):
        """
        if self.dp:
            # 1. Ստեղծում ենք դատարկ ցուցակ (զամբյուղ), որտեղ հավաքելու ենք մեր պատվերները
            informative_list = []

            # 2. Սկսում ենք դասական ցիկլ (for loop) բոլոր ակտիվ մետաղադրամների վրայով
            # ՈՒՂՂՈՒՄ. Օգտագործում ենք current_whitelist(), որը Freqtrade-ի ճիշտ մեթոդն է
            for pair in self.dp.current_whitelist():
                # 3. Ստեղծում ենք փոքրիկ փաթեթ (մետաղադրամի անունը և 1h թայմֆրեյմը)
                pair_info = (pair, self.informative_tf)

                # 4. Ավելացնում ենք այդ փաթեթը մեր գլխավոր ցուցակի մեջ
                informative_list.append(pair_info)

            # 5. Վերադարձնում ենք արդեն լցված ցուցակը Freqtrade շարժիչին
            return informative_list

        # Եթե բազան անջատված է, վերադարձնում ենք դատարկ ցուցակ՝ սխալներից խուսափելու համար
        return []

    # 7. ԻՆԴԻԿԱՏՈՐՆԵՐԻ ԵՎ ՄԱԹԵՄԱՏԻԿԱՅԻ ՀԱՇՎԱՐԿ
    # -------------------------------------------------------------------------------------
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # --- Ա. Մակրո Տրենդի Հաշվարկ (1h) ---
        # Վերցնում ենք արդեն բեռնված 1h աղյուսակը
        informative = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.informative_tf)

        # Հաշվում ենք 1h Supertrend-ը
        htf_st = pta.supertrend(
            informative['high'], informative['low'], informative['close'],
            length=self.st_period.value, multiplier=self.st_multiplier.value
        )
        # Պահում ենք միայն ուղղությունը (1 = աճ, -1 = անկում)
        informative['htf_st_dir'] = htf_st[htf_st.columns[1]]

        # Խելացի սոսնձում. 1h աղյուսակը միացնում ենք հիմնական 15m աղյուսակին:
        # ffill=True-ն լրացնում է դատարկ տեղերը, որպեսզի look-ahead (ապագայի) սխալ չլինի:
        dataframe = merge_informative_pair(dataframe, informative, self.timeframe, self.informative_tf, ffill=True)
        # self.htf_dir_col = f"htf_st_dir_{self.informative_tf}"

        # --- Բ. Տեղական Տրենդ (15m) ---
        # Հաշվում ենք հիմնական գիծը, որի վրա որսալու ենք հետքաշումները
        st = pta.supertrend(
            dataframe['high'], dataframe['low'], dataframe['close'],
            length=self.st_period.value, multiplier=self.st_multiplier.value
        )
        dataframe['st'] = st[st.columns[0]]
        dataframe['st_dir'] = st[st.columns[1]]

        # --- ՆՈՐ: Առանձնացնում ենք գույները գրաֆիկի համար ---
        # Եթե ուղղությունը վերև է (1), պահում ենք գինը կանաչի մեջ, հակառակ դեպքում՝ դատարկ (NaN)
        dataframe['st_green'] = np.where(dataframe['st_dir'] == 1, dataframe['st'], np.nan)
        # Եթե ուղղությունը ներքև է (-1), պահում ենք գինը կարմիրի մեջ
        dataframe['st_red'] = np.where(dataframe['st_dir'] == -1, dataframe['st'], np.nan)


        # Հաշվում ենք Վիրտուալ Supertrend (Ավելի լայն գիծ՝ կեղծ ճեղքումներից / Fakeouts-ից պաշտպանվելու համար)
        virt_mult = self.st_multiplier.value * (1 + self.st_virtual_offset.value)
        st_virt = pta.supertrend(
            dataframe['high'], dataframe['low'], dataframe['close'],
            length=self.st_period.value, multiplier=virt_mult
        )
        dataframe['st_virt'] = st_virt[st_virt.columns[0]]

        # --- Գ. Տրենդի Տարիքը (The Clock) ---
        # Քայլ 1. Ստուգում ենք փոփոխության պահը (Վերադարձնում է True կամ False)
        dataframe['trend_changed'] = dataframe['st_dir'] != dataframe['st_dir'].shift(1)

        # Քայլ 2. Յուրաքանչյուր նոր տրենդի տալիս ենք իր անձնական համարը (ID)
        # cumsum()-ը ամեն True տեսնելիս թիվը մեծացնում է 1-ով (օր՝ Տրենդ 1, Տրենդ 2...)
        dataframe['trend_id'] = dataframe['trend_changed'].cumsum()

        # Քայլ 3. Խմբավորում ենք ըստ այդ ID-ների և պարզապես զրոյից հաշվում մոմերը
        dataframe['trend_age'] = dataframe.groupby('trend_id').cumcount()

        # --- Դ. Թեքության (Slope) Հաշվարկ՝ Դինամիկ Խարիսխի մեթոդով ---

        # 1. ԶՐՈՅԱՑՈՒՄ (RESET). Ամեն անգամ, երբ տրենդը փոխվում է (trend_age == 0),
        # մենք դատարկում ենք խարիսխը (դնում ենք np.nan), որ հին տրենդի գինը չխանգարի նորին:
        dataframe.loc[dataframe['trend_age'] == 0, 'st_anchor'] = np.nan

        # 2. ԽԱՐԻՍԽԻ ՖԻՔՍՈՒՄ. Երբ տրենդը հասնում է մեր նշած տարիքին (օր՝ 4 մոմ),
        # ֆիքսում ենք Supertrend-ի այդ պահի գինը որպես կայուն խարիսխ:
        dataframe.loc[dataframe['trend_age'] == self.slope_candles.value, 'st_anchor'] = dataframe['st']

        # 3. Այդ կայունացած գինը տանում ենք առաջ (ffill) հաջորդող մոմերի վրա:
        # Եթե տրենդը շուտ մեռնի, ffill-ը պարզապես կտանի np.nan (դատարկություն), և սխալ չի լինի:
        dataframe['st_anchor'] = dataframe['st_anchor'].ffill()

        # 4. Հաշվում ենք թեքությունը ընթացիկ գնի և մեր ստեղծած խարիսխի միջև:
        dataframe['slope_long_pct'] = (dataframe['st'] - dataframe['st_anchor']) / dataframe['st_anchor']
        dataframe['slope_short_pct'] = (dataframe['st_anchor'] - dataframe['st']) / dataframe['st_anchor']

        # 5. ԱՊԱՀՈՎԱԳՐՈՒԹՅՈՒՆ. Քանի դեռ տրենդը չի հասել մեր slope_candles տարիքին,
        # թեքությունը արհեստականորեն պահում ենք 0.0, որպեսզի բոտը սպասի և մուտք չանի:
        dataframe.loc[dataframe['trend_age'] < self.slope_candles.value, 'slope_long_pct'] = 0.0
        dataframe.loc[dataframe['trend_age'] < self.slope_candles.value, 'slope_short_pct'] = 0.0



        # --- Ե. Ժամային և Րոպեական Ֆիլտր (Դինամիկ Կոնվերտացիայով) ---
        dataframe['minute_of_day'] = dataframe['date'].dt.hour * 60 + dataframe['date'].dt.minute
        dataframe['active_session'] = False

        current_pair = metadata['pair']
        # ԽԵԼԱՑԻ ՄԱՔՐՈՒՄ. Եթե ակտիվը ֆյուչերս է (BTC/USDT:USDT), կտրում ենք պոչը և պահում միայն հիմքը (BTC/USDT)
        clean_pair = current_pair.split(':')[0]

        # Ստուգում ենք մաքրված անունով
        if clean_pair in self.custom_sessions:
            start_str = self.custom_sessions[clean_pair]["start"]
            end_str = self.custom_sessions[clean_pair]["end"]

            start_min = int(start_str.split(':')[0]) * 60 + int(start_str.split(':')[1])
            end_min = int(end_str.split(':')[0]) * 60 + int(end_str.split(':')[1])

            # ԼՈՒԾՈՒՄ. Ստուգում ենք՝ արդյոք սեսիան անցնո՞ւմ է կեսգիշերը
            if start_min < end_min:
                # Նորմալ ցերեկային սեսիա (օր՝ 17:45 - 19:10)
                dataframe.loc[
                    (dataframe['minute_of_day'] >= start_min) &
                    (dataframe['minute_of_day'] <= end_min),
                    'active_session'
                ] = True
            else:
                # Գիշերային սեսիա (օր՝ 23:00 - 02:00). Օգտագործում ենք ԿԱՄ (|) օպերատորը
                dataframe.loc[
                    (dataframe['minute_of_day'] >= start_min) |
                    (dataframe['minute_of_day'] <= end_min),
                    'active_session'
                ] = True

        else:
            # Բազային ժամեր
            dataframe.loc[
                dataframe['date'].dt.hour.isin(self.allowed_hours),
                'active_session'
            ] = True


        # --- Զ. Մոմերի նախնական տվյալներ ԵՎ Դինամիկ Չափի Ֆիլտր ---
        dataframe['prev_open'] = dataframe['open'].shift(1)
        dataframe['prev_close'] = dataframe['close'].shift(1)
        dataframe['prev_high'] = dataframe['high'].shift(1)
        dataframe['prev_low'] = dataframe['low'].shift(1)
        # 1. Հաշվում ենք ակտիվի վոլատիլությունը՝ հիմնվելով Supertrend-ի ժամանակահատվածի վրա
        dataframe['atr'] = pta.atr(dataframe['high'], dataframe['low'], dataframe['close'], length=self.st_period.value)
        # 1. Հաշվում ենք մոմի մարմնի ՖԻԶԻԿԱԿԱՆ չափը (բացարձակ գնով, ոչ թե տոկոսով)
        dataframe['body_size_abs'] = abs(dataframe['close'] - dataframe['open'])
        # 2. Դինամիկ ստուգում. Արդյո՞ք այս մոմը փոքր է տվյալ պահի ATR-ի թույլատրելի առավելագույն բազմապատկիկից
        dataframe['is_valid_size'] = dataframe['body_size_abs'] <= (
                        dataframe['atr'] * self.max_candle_atr_mult.value)


        # --- Է. Proximity (Գոտուն մոտենալու հաշվարկ՝ close-ով) ---
        # LONG: Ստուգում ենք, թե արդյոք վերջին N մոմերի ընթացքում փակման գինը մտել է մոտեցման գոտի
        dist_long = (dataframe['close'] - dataframe['st']) / dataframe['st']
        dataframe['in_zone_long'] = (dataframe['st_dir'] == 1) & (dist_long > 0) & (
                dist_long <= self.proximity_threshold.value)
        dataframe['setup_long_valid'] = dataframe['in_zone_long'].rolling(
            window=self.reversal_window.value).max() > 0
        # SHORT: Նույնը Short-ի համար
        dist_short = (dataframe['st'] - dataframe['close']) / dataframe['st']
        dataframe['in_zone_short'] = (dataframe['st_dir'] == -1) & (dist_short > 0) & (
                dist_short <= self.proximity_threshold.value)
        dataframe['setup_short_valid'] = dataframe['in_zone_short'].rolling(
            window=self.reversal_window.value).max() > 0


        # --- Ը. Դինամիկ Stop Loss-ի հաշվարկ (Գիծ vs Պոչ + ATR) ---

        # # 1. Հաշվում ենք ակտիվի վոլատիլությունը՝ հիմնվելով Supertrend-ի ժամանակահատվածի վրա
        # dataframe['atr'] = pta.atr(dataframe['high'], dataframe['low'], dataframe['close'], length=self.st_period.value)

        # 2. Գտնում ենք վերջին 2 մոմերի մինիմումներն ու մաքսիմումները
        local_min = dataframe[['low', 'prev_low']].min(axis=1)
        local_max = dataframe[['high', 'prev_high']].max(axis=1)

        # 3. LONG: Ընտրում ենք ապահովագույն կետը և հաշվում ռիսկը ՖԻԶԻԿԱԿԱՆ ԳՆՈՎ
        proposed_sl_long = np.minimum(dataframe['st'], local_min)
        dataframe['dynamic_sl_long'] = proposed_sl_long * (1 - self.sl_offset_pct.value)
        dataframe['risk_amount_long'] = dataframe['close'] - dataframe['dynamic_sl_long']

        # 4. SHORT: Ընտրում ենք ապահովագույն կետը և հաշվում ռիսկը ՖԻԶԻԿԱԿԱՆ ԳՆՈՎ
        proposed_sl_short = np.maximum(dataframe['st'], local_max)
        dataframe['dynamic_sl_short'] = proposed_sl_short * (1 + self.sl_offset_pct.value)
        dataframe['risk_amount_short'] = dataframe['dynamic_sl_short'] - dataframe['close']

        return dataframe

    # =====================================================================================
    # ԲԼՈԿ 3. ՄՈՒՏՔԻ ԱԶԴԱՆՇԱՆՆԵՐ (ENTRY SIGNALS)
    # =====================================================================================
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # --- Ա. Իմպուլսային Կլանման Հաշվարկ ---
        prev_is_red = dataframe['prev_close'] < dataframe['prev_open']
        curr_is_green = dataframe['close'] > dataframe['open']
        bullish_engulfing = prev_is_red & curr_is_green & (dataframe['close'] > dataframe['prev_open'])

        prev_is_green = dataframe['prev_close'] > dataframe['prev_open']
        curr_is_red = dataframe['close'] < dataframe['open']
        bearish_engulfing = prev_is_green & curr_is_red & (dataframe['close'] < dataframe['prev_open'])

        # --- Բ. LONG ՊԱՅՄԱՆՆԵՐ ---
        if self.directional_mode.value in ['long_only', 'both']:
            dataframe.loc[
                (
                        (dataframe['active_session'] == True) &  # 1. Ժամային ֆիլտր
                        (dataframe['is_valid_size'] == True) &  # 2. Մոմը չափազանց մեծ չէ
                        (dataframe[self.htf_dir_col] == 1) &  # 3. Մակրո (1h) տրենդը աճող է
                        (dataframe['st_dir'] == 1) &  # 4. Տեղական (15m) տրենդը աճող է
                        (dataframe['slope_long_pct'] >= self.slope_min_pct.value) &  # 5. Թեքությունը բավարար է
                        (dataframe['setup_long_valid'].shift(
                            1)) &  # 6. ՆԱԽՔԱՆ այս մոմը գինը հպվել էր գծին (Pullback)
                        bullish_engulfing &  # 7. Ունենք Ցուլային Կլանում
                        (dataframe['risk_amount_long'] <= (dataframe['atr'] * self.st_multiplier.value))
                # 8. ATR Ռիսկի ֆիլտր
                ),
                'enter_long'
            ] = 1
        # --- Գ. SHORT ՊԱՅՄԱՆՆԵՐ ---
        if self.directional_mode.value in ['short_only', 'both']:
            dataframe.loc[
                (
                        (dataframe['active_session'] == True) &
                        (dataframe['is_valid_size'] == True) &
                        (dataframe[self.htf_dir_col] == -1) &
                        (dataframe['st_dir'] == -1) &
                        (dataframe['slope_short_pct'] >= self.slope_min_pct.value) &
                        (dataframe['setup_short_valid'].shift(1)) &  # Նախքան այս մոմը գինը հպվել էր գծին
                        bearish_engulfing &
                        (dataframe['risk_amount_short'] <= (dataframe['atr'] * self.st_multiplier.value))
                ),
                'enter_short'
            ] = 1
        return dataframe

    # =====================================================================================
    # ԲԼՈԿ 4. ԵԼՔԵՐ (EXITS), ԼԾԱԿ (LEVERAGE) ԵՎ STOP LOSS/TAKE PROFIT
    # =====================================================================================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        ՏՐԵՆԴԱՅԻՆ TRAILING ՍՏՈՊ (Ճշգրիտ հատման պահով)
        """
        # LONG-ի փակում. Ընթացիկ գինը փոքր է գծից, ԻՍԿ ՆԱԽՈՐԴ մոմի գինը դեռ մեծ կամ հավասար էր գծին
        dataframe.loc[
            (dataframe['close'] < dataframe['st_virt']) &
            (dataframe['close'].shift(1) >= dataframe['st_virt'].shift(1)),
            'exit_long'
        ] = 1

        # SHORT-ի փակում. Ընթացիկ գինը մեծ է գծից, ԻՍԿ ՆԱԽՈՐԴ մոմի գինը դեռ փոքր կամ հավասար էր
        dataframe.loc[
            (dataframe['close'] > dataframe['st_virt']) &
            (dataframe['close'].shift(1) <= dataframe['st_virt'].shift(1)),
            'exit_short'
        ] = 1

        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str,
                 side: str, **kwargs) -> float:
        """
        ԴԻՆԱՄԻԿ ԼԾԱԿԻ ՀԱՇՎԱՐԿ (Fixed Fractional Risk)
        Ապահովում է, որ Stop Loss-ի հարվածի դեպքում կորուստը կազմի ճշգրտորեն մեր ուզած տոկոսը:
        """
        # Քաշում ենք տվյալ մետաղադրամի վերջին հաշվարկված աղյուսակը
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return 1.0

        # Վերցնում ենք ամենավերջին փակված մոմի տվյալները
        # last_candle = dataframe.iloc[-1].squeeze()

        # Գտնում ենք մեր Դինամիկ Stop Loss-ի բացարձակ գինը
        if side == 'long':
            sl_price = float(dataframe['dynamic_sl_long'].iloc[-1])
        else:
            sl_price = float(dataframe['dynamic_sl_short'].iloc[-1])


        # 1. Հաշվում ենք ֆիզիկական հեռավորությունը մինչև ստոպ՝ տոկոսով
        sl_distance_pct = abs(current_rate - sl_price) / current_rate

        # Պաշտպանություն զրոյի բաժանումից (եթե գինը և ստոպը հավասար են)
        if sl_distance_pct == 0:
            return 1.0

        # 2. Կիրառում ենք բանաձևը (Նպատակային Ռիսկ / Իրական SL հեռավորություն)
        # Օրինակ՝ 1% ռիսկ / 0.5% հեռավորություն = 2x Լծակ
        calculated_leverage = self.target_risk_pct.value / sl_distance_pct

        # 3. Ապահովագրություն. Լծակը չի կարող լինել 1-ից փոքր և չի կարող գերազանցել բորսայի մաքսիմումը
        final_leverage = max(1.0, min(calculated_leverage, max_leverage))

        # Կլորացնում ենք 1 տասնորդականով (օր՝ 2.1x), քանի որ բորսաների մեծ մասը ամբողջ թվեր է պահանջում
        return round(final_leverage, 1)

    def custom_stoploss(self, pair: str, trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Պահպանում է մեր Դինամիկ Լոկալ Մին/Մաքս սկզբնական Stop Loss-ը:
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        # Կիրառում ենք ուղիղ ֆիլտր (առանց .loc-ի), որպեսզի PyCharm-ը հստակ տեսնի DataFrame-ը
        trade_candle = dataframe[dataframe['date'] == trade.open_date_utc]

        if len(trade_candle) == 0:
            return self.stoploss

        if trade.is_short:
            sl_absolute_price = float(trade_candle['dynamic_sl_short'].iloc[0])
        else:
            sl_absolute_price = float(trade_candle['dynamic_sl_long'].iloc[0])

        return stoploss_from_absolute(sl_absolute_price, current_rate, is_short=trade.is_short, leverage=trade.leverage)

    def custom_exit(self, pair: str, trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        """
        ԼՐԻՎ ՓԱԿՈՒՄ (FULL TAKE PROFIT) ըստ Risk/Reward (R/R) հարաբերակցության:
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        # Կիրառում ենք ուղիղ ֆիլտր
        trade_candle = dataframe[dataframe['date'] == trade.open_date_utc]

        if len(trade_candle) == 0:
            return None

        if trade.is_short:
            sl_absolute_price = float(trade_candle['dynamic_sl_short'].iloc[0])
        else:
            sl_absolute_price = float(trade_candle['dynamic_sl_long'].iloc[0])

        # Հաշվում ենք սկզբնական 1R ռիսկը տոկոսով (Առանց լծակի ազդեցության)
        base_risk_pct = abs(trade.open_rate - sl_absolute_price) / trade.open_rate

        # Բազմապատկում ենք R/R նպատակակետով
        target_profit_pct = base_risk_pct * self.rr_target.value * trade.leverage

        if current_profit >= target_profit_pct:
            return f"Full_TP_Hit_{self.rr_target.value}RR"

        return None