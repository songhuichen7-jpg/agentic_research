"""
Step 1 verification script.

Validates the entire data pipeline:
  1. Input an industry topic
  2. Use LLM (OpenRouter) to match industry code
  3. Fetch research reports from EastMoney
  4. Fetch structured data from AkShare
  5. Print results
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.llm import get_utility_llm
from src.config.settings import OPENROUTER_API_KEY
from src.connectors.eastmoney import EastMoneyConnector, find_industry_code, get_industry_map
from src.connectors.akshare_connector import AkShareConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("verify")


def match_industry_code_with_llm(topic: str) -> str | None:
    """Use the utility LLM to find the best EastMoney industry code for a topic."""
    industry_map = get_industry_map()
    industry_list = "\n".join(f"  {code}: {name}" for code, name in sorted(industry_map.items(), key=lambda x: x[1]))

    llm = get_utility_llm(temperature=0)
    prompt = (
        f"用户想研究的行业主题是：「{topic}」\n\n"
        f"以下是东方财富行业分类代码列表：\n{industry_list}\n\n"
        "请从上面的列表中选择最匹配的 1-3 个行业代码。\n"
        "只返回 JSON 数组，例如 [\"910\", \"545\"]，不要有任何其他文字。"
    )
    resp = llm.invoke(prompt)
    content = resp.content.strip()

    # Parse JSON array from response
    try:
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        codes = json.loads(content)
        if isinstance(codes, list) and codes:
            return codes[0]
    except (json.JSONDecodeError, IndexError):
        logger.warning("LLM returned unparseable response: %s", content)

    return None


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "人形机器人"

    print(f"\n{'='*60}")
    print(f"  多模态研报 Agent — Step 1 验证")
    print(f"  行业主题: {topic}")
    print(f"{'='*60}\n")

    # -- 1. Verify OpenRouter API key --
    assert OPENROUTER_API_KEY, "OPENROUTER_API_KEY is not set in .env"
    print("[✓] OpenRouter API key loaded\n")

    # -- 2. Test LLM connectivity --
    print("[*] Testing LLM connectivity (OpenRouter utility model)...")
    llm = get_utility_llm()
    resp = llm.invoke("请用一句话回答：1+1等于几？")
    print(f"    LLM response: {resp.content.strip()}")
    print("[✓] LLM connection OK\n")

    # -- 3. Match industry code --
    print("[*] Matching industry code...")
    code = find_industry_code(topic)
    if not code:
        print(f"    Exact match not found, trying LLM matching...")
        code = match_industry_code_with_llm(topic)
    if code:
        industry_map = get_industry_map()
        print(f"    Matched: {code} → {industry_map.get(code, '?')}")
    else:
        print("    [!] Could not match industry code. Using '910' (专用设备) as fallback.")
        code = "910"
    print(f"[✓] Industry code: {code}\n")

    # -- 4. Fetch EastMoney reports --
    print("[*] Fetching EastMoney industry reports...")
    em = EastMoneyConnector(delay=2.0, max_pages=1, years_ago=2)
    items = em.search(topic, industry_code=code)
    print(f"    Found {len(items)} report listings\n")

    if items:
        print("    Top 5 reports:")
        for i, item in enumerate(items[:5]):
            print(f"      {i+1}. [{item['published_at'][:10]}] {item['title']}")
            print(f"         {item['url']}")
        print()

    # Fetch full content for top 3
    docs = []
    fetch_count = min(3, len(items))
    if fetch_count > 0:
        print(f"[*] Fetching full content for top {fetch_count} reports...")
        for i in range(fetch_count):
            item = items[i]
            logger.info("Fetching [%d/%d]: %s", i + 1, fetch_count, item["title"])
            detail = em.fetch(url=item["url"])
            merged = {**item, **detail}
            doc = em.normalize(merged)
            docs.append(doc)
            content_preview = doc.content_text[:100] + "..." if len(doc.content_text) > 100 else doc.content_text
            print(f"    {i+1}. {doc.title}")
            print(f"       Content length: {len(doc.content_text)} chars")
            print(f"       Preview: {content_preview}")
            print()

    print(f"[✓] EastMoney connector: {len(docs)} documents fetched\n")

    # -- 5. Fetch AkShare data --
    print("[*] Testing AkShare connector...")
    ak_conn = AkShareConnector()

    # Try getting industry PE data
    pe_df = ak_conn.get_industry_pe()
    if pe_df is not None and not pe_df.empty:
        print(f"    Industry PE data: {len(pe_df)} rows")
        print(f"    Columns: {list(pe_df.columns)}")
        pe_doc = ak_conn.dataframe_to_document(pe_df, "行业市盈率数据")
        print(f"    Converted to Document: {len(pe_doc.content_text)} chars")
    else:
        print("    [!] Industry PE data not available (non-blocking)")
    print("[✓] AkShare connector OK\n")

    # -- 6. Summary --
    print(f"{'='*60}")
    print("  Step 1 验证结果总结")
    print(f"{'='*60}")
    print(f"  行业主题:      {topic}")
    print(f"  行业代码:      {code}")
    print(f"  研报数量:      {len(items)} listings, {len(docs)} fetched")
    print(f"  LLM 模型:      OpenRouter (utility + writer)")
    print(f"  数据通路:      {'✓ 已打通' if docs else '✗ 需排查'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
