from freqtrade.strategy import IStrategy
from pandas import DataFrame
import pandas_ta as pta



class Praktika(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '5m'
    minimal_roi = {'0':100}
    stoploss = -0.99

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:


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

