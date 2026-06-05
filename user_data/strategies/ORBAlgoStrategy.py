# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
ORB Algo Strategy for Freqtrade
Converted from fluxchart's "ORB Algo | Flux Charts" Pine Script v6.

Logic:
  1. Every session, track the Opening Range (first N minutes = orb_timeframe).
  2. After the ORB closes, wait for a breakout above high or below low.
  3. Count retests of the broken level (sensitivity setting).
  4. Enter Long/Short after enough retests.
  5. Exit at TP1 / TP2 / TP3 (ATR-based) or SL (center of ORB / fixed %).
  6. Force-close any open trade at session end.

⚠️  IMPORTANT CONSTRAINTS
  • Only works on timeframes ≤ 5 m  (Pine required < 15 m).
  • Designed for instruments with a regular daily session (stocks, futures, forex).
  • Short side requires  can_short = True  and a margin-enabled exchange.
  • custom_sell / custom_stoploss hooks handle the 3-TP ladder.
  • Session times default to US market (09:30 – 16:00 ET).  Adjust SESSION_START_HOUR/MIN.
"""

from datetime import time as dtime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import pandas_ta as pta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter, CategoricalParameter
from freqtrade.persistence import Trade


# ── tuneable session constants (UTC hours for US market) ──────────────────────
SESSION_START_HOUR = 13   # 09:30 ET = 13:30 UTC  (change for your market/TZ)
SESSION_START_MIN  = 30
SESSION_END_HOUR   = 20   # 16:00 ET = 20:00 UTC
SESSION_END_MIN    = 0


class ORBAlgoStrategy(IStrategy):
    """
    Opening Range Breakout – full port of fluxchart's Pine v6 indicator.
    """

    INTERFACE_VERSION = 3
    timeframe         = "5m"          # must be ≤ 15 m
    can_short: bool   = True         # set True for short signals on margin

    # ── ROI / stoploss (managed manually via custom_sell) ────────────────────
    minimal_roi   = {"0": 10}         # effectively disabled
    stoploss      = -0.05             # hard emergency stop (5 %)
    trailing_stop = False

    startup_candle_count: int = 50    # need ATR(12) + EMA warmup

    # ── Hyperopt parameters ──────────────────────────────────────────────────
    # ORB window in minutes (Pine default = 30 m)
    orb_minutes = IntParameter(15, 60, default=30, space="buy", optimize=True)

    # Sensitivity → retests needed before entry
    sensitivity = CategoricalParameter(
        ["High", "Medium", "Low", "Lowest"],
        default="Medium", space="buy", optimize=False
    )

    # Breakout condition
    breakout_cond = CategoricalParameter(
        ["Close", "EMA"], default="EMA", space="buy", optimize=False
    )

    # EMA length
    ema_length = CategoricalParameter(
        [4, 9, 13, 20, 34], default=9, space="buy", optimize=False
    )

    # TP method (fixed to ATR — Dynamic requires EMA crossover logic not suited for backtesting)
    tp_method: str = "ATR"

    # SL method
    sl_method = CategoricalParameter(
        ["Safer", "Balanced", "Risky"], default="Balanced", space="buy", optimize=False
    )

    # ATR multipliers (matching Pine constants)
    atr_tp1_mult  = 0.75
    atr_tp2_mult  = 1.50
    atr_tp3_mult  = 2.25
    atr_total_mult = 1.0

    # Adaptive SL (move SL to entry after TP1 hit)
    adaptive_sl = True

    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _retests_needed(sensitivity: str) -> int:
        return {"High": 0, "Medium": 1, "Low": 2, "Lowest": 3}[sensitivity]

    @staticmethod
    def _session_start(dt: pd.Timestamp) -> pd.Timestamp:
        return dt.normalize().replace(
            hour=SESSION_START_HOUR, minute=SESSION_START_MIN, second=0
        )

    @staticmethod
    def _session_end(dt: pd.Timestamp) -> pd.Timestamp:
        return dt.normalize().replace(
            hour=SESSION_END_HOUR, minute=SESSION_END_MIN, second=0
        )

    def _orb_end(self, session_start: pd.Timestamp) -> pd.Timestamp:
        return session_start + pd.Timedelta(minutes=self.orb_minutes.value)

    # ── Indicators ───────────────────────────────────────────────────────────
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        for el in self.ema_length.range:
            dataframe[f"ema_{el}"] = pta.ema((dataframe["high"] + dataframe["low"]) / 2.0, length=el)

        dataframe["atr"] = pta.atr(dataframe["high"], dataframe["low"], dataframe["close"], length=12)

        # ── ORB state machine ────────────────────────────────────────────────
        # We iterate row-by-row to replicate Pine's bar-by-bar logic.
        el   = self.ema_length.value
        ema  = dataframe[f"ema_{el}"].values
        atr  = dataframe["atr"].values
        op   = dataframe["open"].values
        hi   = dataframe["high"].values
        lo   = dataframe["low"].values
        cl   = dataframe["close"].values
        ts   = pd.to_datetime(dataframe["date"])

        n = len(dataframe)

        # Output columns
        sig_long       = np.zeros(n, dtype=int)
        sig_short      = np.zeros(n, dtype=int)
        sig_tp1        = np.zeros(n, dtype=int)
        sig_tp2        = np.zeros(n, dtype=int)
        sig_tp3        = np.zeros(n, dtype=int)
        sig_sl         = np.zeros(n, dtype=int)
        col_entry_px   = np.full(n, np.nan)
        col_sl_px      = np.full(n, np.nan)
        col_tp1_px     = np.full(n, np.nan)
        col_tp2_px     = np.full(n, np.nan)
        col_tp3_px     = np.full(n, np.nan)

        # ORB per-session state
        orb_h = orb_l = orb_start = orb_end = None
        state          = "inactive"   # inactive | opening | waiting | breakout | entered
        is_bullish     = None
        retests        = 0
        entry_px       = sl_px = tp1_px = tp2_px = tp3_px = np.nan
        entry_atr      = np.nan
        tp1_hit = tp2_hit = tp3_hit = sl_hit = False
        adaptive_sl_moved = False
        retests_needed = self._retests_needed(self.sensitivity.value)

        for i in range(n):
            t = ts.iloc[i]
            sess_start = self._session_start(t)
            orb_end_t  = self._orb_end(sess_start)
            sess_end   = self._session_end(t)

            cond_price = ema[i] if self.breakout_cond.value == "EMA" else cl[i]

            # ── New session ──────────────────────────────────────────────────
            if t >= sess_start and (orb_start is None or t.date() > orb_start.date()):
                # Force-close previous session trade at previous bar close
                if state == "entered" and not sl_hit and not tp3_hit:
                    sig_sl[i - 1] = 1           # exit signal on last bar of prev session
                # Reset
                orb_h = orb_l = None
                orb_start = sess_start
                state = "opening"
                is_bullish = None
                retests = 0
                entry_px = sl_px = tp1_px = tp2_px = tp3_px = np.nan
                entry_atr = np.nan
                tp1_hit = tp2_hit = tp3_hit = sl_hit = False
                adaptive_sl_moved = False

            # ── Opening range accumulation ───────────────────────────────────
            if state == "opening":
                if t < orb_end_t:
                    orb_h = hi[i] if orb_h is None else max(orb_h, hi[i])
                    orb_l = lo[i] if orb_l is None else min(orb_l, lo[i])
                else:
                    state = "waiting"

            # ── Waiting for breakout ─────────────────────────────────────────
            if state == "waiting" and orb_h is not None:
                if cond_price > orb_h:
                    is_bullish = True
                    retests    = 0
                    state      = "breakout"
                elif cond_price < orb_l:
                    is_bullish = False
                    retests    = 0
                    state      = "breakout"

            # ── In breakout – count retests ──────────────────────────────────
            if state == "breakout" and orb_h is not None:
                # Failed breakout
                if is_bullish and cl[i] < orb_h:
                    state = "waiting"
                    is_bullish = None
                elif not is_bullish and cl[i] > orb_l:
                    state = "waiting"
                    is_bullish = None
                else:
                    # Retest: price dips back to the level but closes on breakout side
                    if is_bullish and cl[i] > orb_h and lo[i] < orb_h:
                        retests += 1
                    elif not is_bullish and cl[i] < orb_l and hi[i] > orb_l:
                        retests += 1

                    if retests >= retests_needed:
                        # ── Entry ────────────────────────────────────────────
                        state     = "entered"
                        entry_px  = cl[i]
                        entry_atr = atr[i] if not np.isnan(atr[i]) else 0.0

                        # SL calculation
                        center = (orb_h + orb_l) / 2.0
                        if self.sl_method.value == "Safer":
                            sl_px = (center + orb_h) / 2.0 if is_bullish else (center + orb_l) / 2.0
                        elif self.sl_method.value == "Balanced":
                            sl_px = center
                        else:  # Risky
                            sl_px = (center + orb_l) / 2.0 if is_bullish else (center + orb_h) / 2.0

                        # TP levels (ATR method)
                        d = entry_atr * self.atr_total_mult
                        dir_ = 1 if is_bullish else -1
                        tp1_px = entry_px + d * self.atr_tp1_mult * dir_
                        tp2_px = entry_px + d * self.atr_tp2_mult * dir_
                        tp3_px = entry_px + d * self.atr_tp3_mult * dir_

                        if is_bullish:
                            sig_long[i] = 1
                        else:
                            sig_short[i] = 1

                        col_entry_px[i] = entry_px
                        col_sl_px[i]    = sl_px
                        col_tp1_px[i]   = tp1_px
                        col_tp2_px[i]   = tp2_px
                        col_tp3_px[i]   = tp3_px

            # ── In trade – check TP / SL ─────────────────────────────────────
            if state == "entered" and not np.isnan(entry_px):
                # propagate levels
                col_sl_px[i]  = sl_px
                col_tp1_px[i] = tp1_px
                col_tp2_px[i] = tp2_px
                col_tp3_px[i] = tp3_px

                # TP1
                if not tp1_hit:
                    hit = hi[i] >= tp1_px if is_bullish else lo[i] <= tp1_px
                    if hit:
                        tp1_hit = True
                        sig_tp1[i] = 1
                        if self.adaptive_sl:
                            sl_px = entry_px   # move SL to breakeven
                            adaptive_sl_moved = True

                # TP2
                elif not tp2_hit:
                    hit = hi[i] >= tp2_px if is_bullish else lo[i] <= tp2_px
                    if hit:
                        tp2_hit = True
                        sig_tp2[i] = 1

                # TP3
                elif not tp3_hit:
                    hit = hi[i] >= tp3_px if is_bullish else lo[i] <= tp3_px
                    if hit:
                        tp3_hit = True
                        sig_tp3[i] = 1
                        sl_hit = True          # fully out
                        state  = "inactive"

                # SL (only if not already hitting a TP this bar)
                if not sl_hit and sig_tp1[i] == 0 and sig_tp2[i] == 0 and sig_tp3[i] == 0:
                    sl_triggered = (lo[i] < sl_px) if is_bullish else (hi[i] > sl_px)
                    if sl_triggered:
                        sl_hit    = True
                        sig_sl[i] = 1
                        state     = "inactive"

                # Session end – force exit
                if t >= sess_end and not sl_hit and not tp3_hit:
                    sig_sl[i] = 1
                    state     = "inactive"

        dataframe["orb_sig_long"]    = sig_long
        dataframe["orb_sig_short"]   = sig_short
        dataframe["orb_sig_tp1"]     = sig_tp1
        dataframe["orb_sig_tp2"]     = sig_tp2
        dataframe["orb_sig_tp3"]     = sig_tp3
        dataframe["orb_sig_sl"]      = sig_sl
        dataframe["orb_entry_px"]    = col_entry_px
        dataframe["orb_sl_px"]       = col_sl_px
        dataframe["orb_tp1_px"]      = col_tp1_px
        dataframe["orb_tp2_px"]      = col_tp2_px
        dataframe["orb_tp3_px"]      = col_tp3_px

        return dataframe

    # ── Entry signals ────────────────────────────────────────────────────────
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["orb_sig_long"] == 1) & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1

        if self.can_short:
            dataframe.loc[
                (dataframe["orb_sig_short"] == 1) & (dataframe["volume"] > 0),
                "enter_short",
            ] = 1

        return dataframe

    # ── Exit signals ─────────────────────────────────────────────────────────
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # TP3 or SL hit → full exit
        dataframe.loc[
            ((dataframe["orb_sig_tp3"] == 1) | (dataframe["orb_sig_sl"] == 1))
            & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1

        if self.can_short:
            dataframe.loc[
                ((dataframe["orb_sig_tp3"] == 1) | (dataframe["orb_sig_sl"] == 1))
                & (dataframe["volume"] > 0),
                "exit_short",
            ] = 1

        return dataframe

    # ── Custom stoploss (dynamic SL + partial exits via ROI ladder) ──────────
    def custom_stoploss(
        self,
        current_time,
        current_rate: float,
        current_profit: float,
        trade: Trade,
        **kwargs,
    ) -> float:
        """
        Move SL to breakeven after TP1 is reached.
        We approximate this by checking current_profit > atr_tp1_mult %.
        For production, store the SL level in trade.custom_info.
        """
        # After TP1 (~0.75 ATR gain), protect entry
        if current_profit >= 0.005:   # 0.5 % as a rough proxy
            return -0.001             # near-zero trailing (effectively breakeven)
        return self.stoploss

    # ── Custom sell (partial exits at TP1 / TP2) ────────────────────────────
    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        """
        Partial exits are not natively supported in Freqtrade without
        the partial-close patch.  This hook returns a reason string for
        full exits only; use the ROI table or a fork with partial support
        for true ladder exits.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None

        last = dataframe.iloc[-1]

        # Full TP3 or SL exit
        if last["orb_sig_tp3"] == 1:
            return "orb_tp3"
        if last["orb_sig_sl"] == 1:
            return "orb_sl"

        # Session-end forced exit
        ct = pd.Timestamp(current_time, tz="UTC")
        sess_end = self._session_end(ct)
        if ct >= sess_end:
            return "orb_session_end"

        return None