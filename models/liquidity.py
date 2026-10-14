"""
Net liquidity: Fed balance sheet minus the cash it isn't putting into markets.

    Net liquidity = WALCL − TGA (WTREGEN) − Overnight Reverse Repo (RRPONTSYD)

WALCL and WTREGEN are weekly (Wednesday) in millions of USD; RRPONTSYD is daily in billions.
Result is in millions of USD on WALCL's weekly dates.
"""
from __future__ import annotations

import pandas as pd


def compute_net_liquidity(liquidity_df: pd.DataFrame) -> pd.Series:
    """Weekly net liquidity (millions USD). Empty if WALCL or TGA is missing; RRP treated as 0 before it existed."""
    if liquidity_df.empty or not {"WALCL", "TGA"} <= set(liquidity_df.columns):
        return pd.Series(dtype=float)
    walcl = liquidity_df["WALCL"].dropna()
    tga = liquidity_df["TGA"].dropna()
    if walcl.empty or tga.empty:
        return pd.Series(dtype=float)
    idx = walcl.index
    tga_on = pd.Series(tga.asof(idx).to_numpy(dtype=float), index=idx)
    if "RRP" in liquidity_df.columns and not liquidity_df["RRP"].dropna().empty:
        rrp = liquidity_df["RRP"].dropna()
        rrp_on = pd.Series(rrp.asof(idx).to_numpy(dtype=float), index=idx).fillna(0.0) * 1000  # billions → millions
    else:
        rrp_on = 0.0
    return (walcl - tga_on - rrp_on).dropna().rename("NET_LIQUIDITY")
