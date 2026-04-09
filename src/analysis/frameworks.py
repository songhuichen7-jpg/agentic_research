"""Industry analysis frameworks — provides structured analytical templates.

Selects appropriate frameworks (PEST, Porter's Five Forces, value chain, etc.)
based on industry type and injects them into planner and writer prompts.
"""

from __future__ import annotations

# ── Framework definitions ───────────────────────────────────

FRAMEWORKS: dict[str, dict] = {
    "pest": {
        "name": "PEST 宏观环境分析",
        "dimensions": ["政策环境（P）", "经济环境（E）", "社会环境（S）", "技术环境（T）"],
        "prompt_hint": "从政策（P）、经济（E）、社会（S）、技术（T）四个维度分析宏观环境对行业的影响，每个维度给出具体政策文件名称或数据。",
    },
    "porter": {
        "name": "波特五力竞争分析",
        "dimensions": ["现有竞争者", "潜在进入者", "替代品威胁", "供应商议价能力", "买方议价能力"],
        "prompt_hint": "用波特五力模型分析行业竞争：现有竞争者（CR3/CR5 集中度）、潜在进入者（壁垒高低）、替代品威胁、供应商议价能力、买方议价能力。每项给出强/中/弱判断及理由。",
    },
    "value_chain": {
        "name": "产业链与价值链分析",
        "dimensions": ["上游供应", "中游制造/服务", "下游应用/消费", "价值分配"],
        "prompt_hint": "梳理完整产业链：上游原材料/核心零部件 → 中游制造/集成 → 下游应用场景/终端客户。分析各环节的利润分配、议价能力和关键瓶颈。",
    },
    "lifecycle": {
        "name": "行业生命周期分析",
        "dimensions": ["当前阶段判断", "增速特征", "竞争特征", "未来演进"],
        "prompt_hint": "判断行业处于导入期、成长期、成熟期还是衰退期，给出判断依据（增速、渗透率、竞争者数量），并预判未来 3-5 年的阶段演进。",
    },
    "competitive": {
        "name": "竞争格局与市场份额",
        "dimensions": ["市场集中度", "TOP5 企业对比", "差异化竞争策略", "护城河分析"],
        "prompt_hint": "量化分析竞争格局：CR3/CR5/HHI 集中度指标、TOP5 企业营收/市占率对比表、各家差异化策略（成本、技术、品牌、渠道）、护城河类型及强度。",
    },
    "tam_sam_som": {
        "name": "市场规模三层模型",
        "dimensions": ["TAM（潜在市场总量）", "SAM（可服务市场）", "SOM（可获取市场）"],
        "prompt_hint": "用 TAM/SAM/SOM 三层模型量化市场规模：TAM（全球/全国潜在总量）→ SAM（目标细分市场）→ SOM（实际可触达市场）。给出每层的具体金额和计算逻辑。",
    },
    "swot": {
        "name": "SWOT 分析",
        "dimensions": ["优势（S）", "劣势（W）", "机会（O）", "威胁（T）"],
        "prompt_hint": "从行业整体视角做 SWOT 分析：内部优势与劣势（资源/能力/效率），外部机会与威胁（政策/市场/技术变革），每项列出 2-3 个具体要点。",
    },
    "supply_demand": {
        "name": "供需分析",
        "dimensions": ["供给端产能与格局", "需求端驱动与结构", "供需平衡与价格趋势"],
        "prompt_hint": "分析供给端（产能、开工率、新增产能计划、主要供应商）和需求端（下游需求结构、增长驱动因素、替代需求），判断当前供需关系和价格走势。",
    },
}

# ── Industry → Framework mapping ────────────────────────────

# Keywords in topic → recommended framework set
_INDUSTRY_FRAMEWORK_MAP: list[tuple[list[str], list[str]]] = [
    # 制造业 / 工业
    (["制造", "工业", "材料", "钢铁", "化工", "有色", "建材", "机械", "设备"],
     ["pest", "value_chain", "supply_demand", "competitive", "lifecycle"]),
    # 科技 / 互联网
    (["科技", "互联网", "软件", "AI", "人工智能", "芯片", "半导体", "云计算", "大数据", "SaaS"],
     ["pest", "tam_sam_som", "competitive", "value_chain", "lifecycle"]),
    # 消费
    (["消费", "零售", "食品", "饮料", "服装", "家电", "美妆", "电商"],
     ["pest", "competitive", "value_chain", "swot", "lifecycle"]),
    # 医药 / 医疗
    (["医药", "医疗", "生物", "制药", "器械", "健康"],
     ["pest", "tam_sam_som", "competitive", "value_chain", "lifecycle"]),
    # 金融
    (["金融", "银行", "保险", "证券", "基金", "信托"],
     ["pest", "competitive", "swot", "lifecycle"]),
    # 能源 / 新能源
    (["能源", "新能源", "光伏", "风电", "储能", "电池", "氢能", "碳中和"],
     ["pest", "value_chain", "supply_demand", "tam_sam_som", "competitive"]),
    # 汽车 / 出行
    (["汽车", "新能源汽车", "智能驾驶", "出行", "低空经济", "无人机"],
     ["pest", "value_chain", "competitive", "tam_sam_som", "lifecycle"]),
    # 地产 / 基建
    (["地产", "房地产", "基建", "建筑"],
     ["pest", "supply_demand", "lifecycle", "swot"]),
]

# Default frameworks for unknown industries
_DEFAULT_FRAMEWORKS = ["pest", "competitive", "value_chain", "tam_sam_som", "lifecycle"]


def select_frameworks(topic: str) -> list[str]:
    """Select appropriate analysis frameworks based on topic keywords."""
    topic_lower = topic.lower()
    for keywords, framework_ids in _INDUSTRY_FRAMEWORK_MAP:
        if any(kw in topic_lower for kw in keywords):
            return framework_ids
    return _DEFAULT_FRAMEWORKS


def get_framework(framework_id: str) -> dict | None:
    """Get a framework definition by ID."""
    return FRAMEWORKS.get(framework_id)


def format_frameworks_for_planner(topic: str) -> str:
    """Generate framework guidance text for the planner prompt."""
    ids = select_frameworks(topic)
    lines = ["以下是适用于该行业的分析框架，请在章节设计中覆盖这些维度：\n"]
    for fid in ids:
        fw = FRAMEWORKS.get(fid)
        if fw:
            dims = "、".join(fw["dimensions"])
            lines.append(f"- **{fw['name']}**：{dims}")
    return "\n".join(lines)


def format_framework_for_writer(topic: str, section_title: str) -> str:
    """Select the most relevant framework for a specific section and return prompt guidance."""
    ids = select_frameworks(topic)
    title_lower = section_title.lower()

    # Match section title to framework
    matches: list[str] = []
    _SECTION_FRAMEWORK_HINTS = {
        "pest": ["宏观", "政策", "环境", "驱动", "PEST"],
        "porter": ["竞争", "五力", "格局"],
        "value_chain": ["产业链", "价值链", "上下游", "供应链"],
        "lifecycle": ["生命周期", "阶段", "演进", "成熟度"],
        "competitive": ["竞争", "格局", "市场份额", "集中度", "龙头", "头部"],
        "tam_sam_som": ["市场规模", "规模", "容量", "TAM", "SAM"],
        "swot": ["SWOT", "优势", "劣势", "机会", "威胁"],
        "supply_demand": ["供需", "供给", "需求", "产能", "价格"],
    }

    for fid in ids:
        keywords = _SECTION_FRAMEWORK_HINTS.get(fid, [])
        if any(kw in title_lower for kw in keywords):
            matches.append(fid)

    if not matches:
        return ""

    lines = ["\n## 分析框架指引\n请在本章节中运用以下分析框架：\n"]
    for fid in matches[:2]:  # Max 2 frameworks per section
        fw = FRAMEWORKS.get(fid)
        if fw:
            lines.append(f"**{fw['name']}**：{fw['prompt_hint']}\n")
    return "\n".join(lines)
