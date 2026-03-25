"""
EastMoney (东方财富) industry research report connector.

EastMoney industry research report connector.
Key improvements:
  - Unified SourceConnector interface
  - Configurable rate limiting instead of hard-coded sleep
  - Local caching to avoid redundant fetches
  - Returns typed Document objects
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.config.settings import EASTMONEY_REQUEST_DELAY, RAW_DIR
from src.models import Document, SourceType

logger = logging.getLogger(__name__)

# ── Industry code mapping (parsed from EastMoney page) ───────

_INDUSTRY_MAP: dict[str, str] = {
    "546": "玻璃玻纤",
    "474": "保险",
    "1036": "半导体",
    "733": "包装材料",
    "1017": "采掘行业",
    "729": "船舶制造",
    "459": "电子元件",
    "457": "电网设备",
    "428": "电力行业",
    "1039": "电子化学品",
    "1034": "电源设备",
    "1033": "电池",
    "1030": "电机",
    "738": "多元金融",
    "451": "房地产开发",
    "436": "纺织服装",
    "1045": "房地产服务",
    "1032": "风电设备",
    "1020": "非金属材料",
    "479": "钢铁行业",
    "427": "公用事业",
    "425": "工程建设",
    "1038": "光学光电子",
    "1031": "光伏设备",
    "739": "工程机械",
    "732": "贵金属",
    "726": "工程咨询服务",
    "538": "化学制品",
    "480": "航天航空",
    "471": "化纤行业",
    "465": "化学制药",
    "450": "航运港口",
    "447": "互联网服务",
    "420": "航空机场",
    "1019": "化学原料",
    "731": "化肥行业",
    "728": "环保行业",
    "456": "家电行业",
    "440": "家用轻工",
    "429": "交运设备",
    "740": "教育",
    "735": "计算机设备",
    "485": "旅游酒店",
    "484": "贸易行业",
    "437": "煤炭行业",
    "1035": "美容护理",
    "477": "酿酒行业",
    "433": "农牧饲渔",
    "1015": "能源金属",
    "730": "农药兽药",
    "481": "汽车零部件",
    "1029": "汽车整车",
    "1016": "汽车服务",
    "1028": "燃气",
    "737": "软件开发",
    "482": "商业百货",
    "464": "石油行业",
    "454": "塑料制品",
    "438": "食品饮料",
    "424": "水泥建材",
    "1044": "生物制品",
    "545": "通用设备",
    "448": "通信设备",
    "421": "铁路公路",
    "736": "通信服务",
    "486": "文化传媒",
    "422": "物流行业",
    "1037": "消费电子",
    "1027": "小金属",
    "1018": "橡胶制品",
    "478": "有色金属",
    "475": "银行",
    "458": "仪器仪表",
    "1046": "游戏",
    "1042": "医药商业",
    "1041": "医疗器械",
    "727": "医疗服务",
    "539": "综合行业",
    "476": "装修建材",
    "473": "证券",
    "470": "造纸印刷",
    "1043": "专业服务",
    "1040": "中药",
    "910": "专用设备",
    "734": "珠宝首饰",
    "725": "装修装饰",
}

_NAME_TO_CODE = {v: k for k, v in _INDUSTRY_MAP.items()}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36"
    ),
}


def get_industry_map() -> dict[str, str]:
    """Return {code: name} mapping of all known EastMoney industry codes."""
    return dict(_INDUSTRY_MAP)


def find_industry_code(keyword: str, use_llm: bool = True) -> str | None:
    """Fuzzy-match an industry name to its EastMoney code.

    Falls back to LLM matching when *use_llm* is True and no exact/substring
    match is found.
    """
    if keyword in _NAME_TO_CODE:
        return _NAME_TO_CODE[keyword]
    for name, code in _NAME_TO_CODE.items():
        if keyword in name or name in keyword:
            return code

    if not use_llm:
        return None

    # LLM fallback
    try:
        import json as _json
        from src.config.llm import get_utility_llm

        industry_list = "\n".join(f"  {c}: {n}" for c, n in sorted(_INDUSTRY_MAP.items(), key=lambda x: x[1]))
        prompt = (
            f"用户想研究的行业主题是：「{keyword}」\n\n"
            f"以下是东方财富行业分类代码列表：\n{industry_list}\n\n"
            "请从上面的列表中选择最匹配的 1-3 个行业代码。\n"
            '只返回 JSON 数组，例如 ["910", "545"]，不要有任何其他文字。'
        )
        resp = get_utility_llm(temperature=0).invoke(prompt)
        content = resp.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        codes = _json.loads(content)
        if isinstance(codes, list) and codes:
            code = str(codes[0])
            logger.info("LLM matched '%s' → code %s (%s)", keyword, code, _INDUSTRY_MAP.get(code, "?"))
            return code
    except Exception as e:
        logger.warning("LLM industry code matching failed: %s", e)

    return None


# ── Cache helpers ────────────────────────────────────────────


def _cache_path(prefix: str, key: str) -> Path:
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    p = RAW_DIR / "eastmoney" / prefix
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{h}.json"


def _read_cache(prefix: str, key: str) -> dict | None:
    path = _cache_path(prefix, key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _write_cache(prefix: str, key: str, data: dict) -> None:
    path = _cache_path(prefix, key)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Low-level API wrappers ───────────────────────────────────


def _fetch_report_list(industry_code: str, page: int = 1, years_ago: int = 2) -> dict:
    """Fetch the industry report list from EastMoney API."""
    cache_key = f"{industry_code}_{page}_{years_ago}"
    cached = _read_cache("list", cache_key)
    if cached:
        logger.info("Cache hit for report list: %s", cache_key)
        return cached

    now = datetime.now()
    end_date = now.strftime("%Y-%m-%d")
    start_date = now.replace(year=now.year - years_ago).strftime("%Y-%m-%d")

    params = {
        "industryCode": str(industry_code),
        "pageSize": 50,
        "industry": "*",
        "rating": "*",
        "ratingChange": "*",
        "beginTime": start_date,
        "endTime": end_date,
        "pageNo": page,
        "fields": "",
        "qType": 1,
        "orgCode": "",
        "rcode": "",
        "p": page,
        "pageNum": page,
        "pageNumber": page,
        "_": int(time.time() * 1000),
    }

    resp = requests.get(
        "https://reportapi.eastmoney.com/report/list",
        params=params,
        headers=_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()

    text = resp.text
    for prefix in ("datatable", "jQuery"):
        idx = text.find("(")
        if idx != -1 and text.endswith(")"):
            text = text[idx + 1 : -1]
            break

    data = json.loads(text)
    _write_cache("list", cache_key, data)
    return data


def _fetch_report_page(url: str) -> str | None:
    """Fetch the HTML of a single report page."""
    cache_key = url
    cached = _read_cache("page", cache_key)
    if cached:
        return cached.get("html", "")

    resp = requests.get(url, headers=_HEADERS, timeout=15)
    if resp.status_code != 200:
        logger.warning("Failed to fetch %s: HTTP %d", url, resp.status_code)
        return None

    _write_cache("page", cache_key, {"html": resp.text, "url": url})
    return resp.text


def _parse_report_html(html: str) -> tuple[str, str | None]:
    """Extract body text and optional PDF link from a report page."""
    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.find("div", class_="ctx-content")
    pdf_link = soup.find("a", class_="pdf-link")
    content = content_div.get_text(strip=True) if content_div else ""
    pdf_url = pdf_link["href"] if pdf_link else None
    return content, pdf_url


# ── Public connector class ───────────────────────────────────


class EastMoneyConnector:
    """SourceConnector implementation for EastMoney industry reports."""

    def __init__(self, delay: float = EASTMONEY_REQUEST_DELAY, years_ago: int = 2, max_pages: int = 1):
        self.delay = delay
        self.years_ago = years_ago
        self.max_pages = max_pages

    # -- SourceConnector interface --

    def search(self, topic: str, **kwargs: Any) -> list[dict]:
        """Search for industry reports matching *topic*.

        Accepts optional ``industry_code`` kwarg to skip fuzzy matching.
        """
        industry_code = kwargs.get("industry_code") or find_industry_code(topic)
        if not industry_code:
            logger.warning("Cannot map topic '%s' to an industry code", topic)
            return []

        results: list[dict] = []
        for page in range(1, self.max_pages + 1):
            if page > 1:
                time.sleep(self.delay)
            data = _fetch_report_list(industry_code, page=page, years_ago=self.years_ago)
            for item in data.get("data", []):
                info_code = item.get("infoCode", "")
                results.append(
                    {
                        "title": item.get("title", ""),
                        "info_code": info_code,
                        "org_name": item.get("orgName", ""),
                        "published_at": item.get("publishDate", ""),
                        "url": f"https://data.eastmoney.com/report/zw_industry.jshtml?infocode={info_code}",
                        "industry_code": industry_code,
                        "raw": item,
                    }
                )
        logger.info("EastMoney search for '%s' (code=%s) returned %d items", topic, industry_code, len(results))
        return results

    def fetch(self, item_id: str | None = None, url: str | None = None) -> dict:
        """Fetch full content of a single report."""
        if not url and item_id:
            url = f"https://data.eastmoney.com/report/zw_industry.jshtml?infocode={item_id}"
        if not url:
            return {"content": "", "pdf_url": None}

        time.sleep(self.delay)
        html = _fetch_report_page(url)
        if not html:
            return {"content": "", "pdf_url": None, "url": url}

        content, pdf_url = _parse_report_html(html)
        return {"content": content, "pdf_url": pdf_url, "url": url}

    def normalize(self, raw: dict) -> Document:
        """Convert a raw search result + fetched content into a Document."""
        pub_date = raw.get("published_at", "")
        if pub_date:
            try:
                pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        return Document(
            source_type=SourceType.INDUSTRY_REPORT,
            source_name="eastmoney",
            title=raw.get("title", ""),
            published_at=pub_date,
            url=raw.get("url", ""),
            content_text=raw.get("content", ""),
            content_markdown=raw.get("content", ""),
            meta={
                "org_name": raw.get("org_name", ""),
                "info_code": raw.get("info_code", ""),
                "industry_code": raw.get("industry_code", ""),
                "pdf_url": raw.get("pdf_url"),
            },
        )

    # -- Convenience --

    def search_and_fetch(self, topic: str, max_reports: int = 10, **kwargs: Any) -> list[Document]:
        """Search, fetch content for top results, and return Documents.

        Accepts optional ``emit_fn`` kwarg — a callable(detail: str) used to
        broadcast granular progress events (e.g. telemetry).
        """
        emit_fn = kwargs.pop("emit_fn", None)
        items = self.search(topic, **kwargs)[:max_reports]
        docs: list[Document] = []
        for i, item in enumerate(items):
            title_short = item["title"][:40]
            logger.info("[%d/%d] Fetching: %s", i + 1, len(items), item["title"])
            if emit_fn:
                emit_fn(f"获取研报 [{i + 1}/{len(items)}] {title_short}")
            detail = self.fetch(url=item["url"])
            merged = {**item, **detail}
            docs.append(self.normalize(merged))
        if emit_fn:
            emit_fn(f"共获取 {len(docs)} 篇研报")
        return docs
