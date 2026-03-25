"""
AkShare connector for structured market/company data.

Migrated from AIDM_AFAC_Agent get_stock_info.py / get_financial_data_annual.py / get_company_intro.py.
Provides a unified SourceConnector interface over AkShare's diverse APIs.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import akshare as ak
import pandas as pd

from src.config.settings import AKSHARE_REQUEST_DELAY
from src.models import Document, SourceType

logger = logging.getLogger(__name__)


def _safe_call(fn, *args, **kwargs) -> pd.DataFrame | None:
    """Call an AkShare function with basic error handling."""
    try:
        time.sleep(AKSHARE_REQUEST_DELAY)
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning("AkShare call %s failed: %s", fn.__name__, e)
        return None


class AkShareConnector:
    """SourceConnector for AkShare structured financial data."""

    # -- SourceConnector interface --

    def search(self, topic: str, **kwargs: Any) -> list[dict]:
        """Not directly applicable — use helper methods below."""
        return []

    def fetch(self, item_id: str | None = None, url: str | None = None) -> dict:
        return {}

    def normalize(self, raw: dict) -> Document:
        return Document(
            source_type=SourceType.STRUCTURED_DATA,
            source_name="akshare",
            title=raw.get("title", ""),
            content_text=raw.get("content", ""),
            content_markdown=raw.get("content", ""),
            meta=raw.get("meta", {}),
        )

    # -- Stock price data --

    def get_cn_stock_hist(
        self,
        symbol: str,
        period: str = "monthly",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """Get A-share historical price data."""
        symbol = "".join(filter(str.isdigit, symbol.upper()))
        if not start_date:
            start_date = f"{datetime.now().year - 1}0101"
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        return _safe_call(ak.stock_zh_a_hist, symbol=symbol, period=period, start_date=start_date, end_date=end_date)

    def get_hk_stock_hist(
        self,
        symbol: str,
        period: str = "monthly",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """Get HK stock historical price data."""
        symbol = "".join(filter(str.isdigit, symbol.upper()))
        if len(symbol) > 4:
            symbol = symbol[-4:]
        symbol = "0" + symbol
        if not start_date:
            start_date = f"{datetime.now().year - 1}0101"
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        return _safe_call(ak.stock_hk_hist, symbol=symbol, period=period, start_date=start_date, end_date=end_date)

    # -- Industry sector data --

    def get_sector_stocks(self, sector_name: str) -> pd.DataFrame | None:
        """Get constituent stocks of an industry sector (概念板块)."""
        return _safe_call(ak.stock_board_concept_name_em)

    def get_industry_pe(self) -> pd.DataFrame | None:
        """Get industry-level PE ratios (申万行业)."""
        return _safe_call(ak.stock_board_industry_summary_ths)

    # -- Convert DataFrame to Document --

    def dataframe_to_document(self, df: pd.DataFrame, title: str, meta: dict | None = None) -> Document:
        """Convert a pandas DataFrame into a Document with markdown table."""
        md_table = df.head(30).to_markdown(index=False)
        return Document(
            source_type=SourceType.STRUCTURED_DATA,
            source_name="akshare",
            title=title,
            content_markdown=md_table,
            content_text=df.head(30).to_string(index=False),
            meta=meta or {},
        )
