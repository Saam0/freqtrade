# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401

"""
Bollinger Bands Breakout Strategy for Freqtrade
Converted from TradeChartist's Pine Script strategy.

Original logic:
- Long signal: price closes ABOVE the upper Bollinger Band
- Short signal: price closes BELOW the lower Bollinger Band
- Default: 55 SMA, 1.0 Standard Deviation

Author: Converted for Freqtrade
"""

from datetime import datetime
from typing import Optional

import pandas as pd
import pandas_ta as pta
from pandas import DataFrame

from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    CategoricalParameter,
    merge_informative_pair,
)


class BBBreakoutStrategy(IStrategy):
    """
    Bollinger Bands Breakout Strategy

    - BUY  when price closes above the upper BB band
    - SELL when price closes below the lower BB band

    Based on TradeChartist's BB Filter (Pine Script v4).
    """

    # ── Strategy metadata ────────────────────────────────────────────────────
    INTERFACE_VERSION = 3

    # Timeframe
    timeframe = "1h"

    # Can this strategy go short?
    can_short: bool = True  # Set True + use_custom_stoploss if you enable shorts

    # ── ROI / Stoploss (let the signal handle exits) ─────────────────────────
    # Effectively disable ROI-based exits so the short-signal closes longs.
    minimal_roi = {
        "0": 100  # 10 000% → never hit by ROI alone
    }

    stoploss = -0.10  # 10 % hard stop – adjust to your risk tolerance

    trailing_stop = False

    # ── Startup candles ──────────────────────────────────────────────────────
    # We need at least `bb_length` candles before the first valid signal.
    startup_candle_count: int = 60

    # ── Hyperopt / optimisable parameters ────────────────────────────────────
    # SMA length (Pine default = 55)
    bb_length = IntParameter(20, 200, default=55, space="buy", optimize=True)

    # Standard deviation multiplier (Pine default = 1.0, max = 2.0)
    bb_std = DecimalParameter(0.5, 2.0, decimals=2, default=1.0, space="buy", optimize=True)

    # Trade direction – mirrors the Pine "Trade Type" input
    trade_type = CategoricalParameter(
        ["Longs Only", "Shorts Only", "Both"],
        default="Longs Only",
        space="buy",
        optimize=False,
    )

    # ── Indicator calculation ────────────────────────────────────────────────
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calculate Bollinger Bands for every combination that the optimiser
        might explore so we don't recompute inside populate_entry/exit.
        """
        for length in self.bb_length.range:
            for std in self.bb_std.range:
                bb = pta.bbands(dataframe["close"], length=length, std=std)
                if bb is not None:
                    upper_col = f"bb_upper_{length}_{std}"
                    lower_col = f"bb_lower_{length}_{std}"
                    basis_col = f"bb_basis_{length}_{std}"
                    # pandas_ta column names: BBL, BBM, BBU, BBB, BBP
                    dataframe[upper_col] = bb[f"BBU_{length}_{float(std)}"]
                    dataframe[lower_col] = bb[f"BBL_{length}_{float(std)}"]
                    dataframe[basis_col] = bb[f"BBM_{length}_{float(std)}"]

        return dataframe

    # ── Helper: active band columns ──────────────────────────────────────────
    def _band_cols(self):
        length = self.bb_length.value
        std = self.bb_std.value
        return (
            f"bb_upper_{length}_{std}",
            f"bb_lower_{length}_{std}",
            f"bb_basis_{length}_{std}",
        )

    # ── Entry signals ────────────────────────────────────────────────────────
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        upper_col, lower_col, _ = self._band_cols()

        # ── LONG entry: close crosses above upper band ────────────────────
        if self.trade_type.value in ("Longs Only", "Both"):
            dataframe.loc[
                (
                    (dataframe["close"] > dataframe[upper_col])   # above upper band
                    & (dataframe["volume"] > 0)                    # valid candle
                ),
                "enter_long",
            ] = 1

        # ── SHORT entry: close crosses below lower band ───────────────────
        if self.trade_type.value in ("Shorts Only", "Both") and self.can_short:
            dataframe.loc[
                (
                    (dataframe["close"] < dataframe[lower_col])   # below lower band
                    & (dataframe["volume"] > 0)
                ),
                "enter_short",
            ] = 1

        return dataframe

    # ── Exit signals ─────────────────────────────────────────────────────────
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        upper_col, lower_col, _ = self._band_cols()

        # ── Close LONG when a short signal fires ──────────────────────────
        if self.trade_type.value in ("Longs Only", "Both"):
            dataframe.loc[
                (
                    (dataframe["close"] < dataframe[lower_col])
                    & (dataframe["volume"] > 0)
                ),
                "exit_long",
            ] = 1

        # ── Close SHORT when a long signal fires ──────────────────────────
        if self.trade_type.value in ("Shorts Only", "Both") and self.can_short:
            dataframe.loc[
                (
                    (dataframe["close"] > dataframe[upper_col])
                    & (dataframe["volume"] > 0)
                ),
                "exit_short",
            ] = 1

        return dataframe