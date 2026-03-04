"""
FRED-only "Macro Regime" curves — alternative to Yahoo rotation when Yahoo is unavailable.
Uses S&P 500, Fed liquidity (WALCL), NFCI, and HY spread from existing FRED data; all rebased to 100.
"""
from __future__ import annotations

import pandas as pd


def prepare_regime_curves(
    val_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    base_date: str | None = None,
) -> pd.DataFrame:
    """
    Build rebased (100 = start) curves from FRED series only. No Yahoo Finance.
    Columns: S&P 500, Liquidity, NFCI, HY spread — aligned to risk_df index.
    Returns empty DataFrame if insufficient data.
    """
    if risk_df.empty or len(risk_df) < 10:
        return pd.DataFrame()
    idx = risk_df.index.sort_values()
    out = pd.DataFrame(index=idx)

    # S&P 500 from valuation data (reindex to risk index)
    if not val_df.empty and "SP500" in val_df.columns:
        s = val_df["SP500"].reindex(idx).ffill().dropna()
        if len(s) >= 10:
            base = s.loc[base_date] if base_date and base_date in s.index else s.iloc[0]
            if base and base != 0:
                out["S&P 500"] = (s / base) * 100

    # Liquidity (WALCL) from risk_df
    if "LIQUIDITY" in risk_df.columns:
        s = risk_df["LIQUIDITY"].reindex(idx).ffill().dropna()
        if len(s) >= 10:
            base = s.loc[base_date] if base_date and base_date in s.index else s.iloc[0]
            if base and base != 0:
                out["Liquidity (WALCL)"] = (s / base) * 100

    # NFCI (higher = tighter) — raw rebased so trend is visible
    if "CREDIT_TIGHTENING" in risk_df.columns:
        s = risk_df["CREDIT_TIGHTENING"].reindex(idx).ffill().dropna()
        if len(s) >= 10:
            base = s.loc[base_date] if base_date and base_date in s.index else s.iloc[0]
            if base is not None and (base != 0 or s.min() != s.max()):
                # Avoid div by zero; if constant use 100
                scale = base if base != 0 else 1.0
                out["NFCI"] = (s / scale) * 100

    # Credit stress (HY OAS) — raw rebased
    if "CREDIT_STRESS" in risk_df.columns:
        s = risk_df["CREDIT_STRESS"].reindex(idx).ffill().dropna()
        if len(s) >= 10:
            base = s.loc[base_date] if base_date and base_date in s.index else s.iloc[0]
            if base is not None and (base != 0 or s.min() != s.max()):
                scale = base if base != 0 else 1.0
                out["HY spread"] = (s / scale) * 100

    out = out.dropna(how="all").ffill().dropna(how="all")
    return out if len(out.columns) >= 1 and len(out) >= 10 else pd.DataFrame()
