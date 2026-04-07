"""Document content audit engine.

Provides keyword-based sensitive word detection, violation identification,
and compliance checking with configurable rule categories.
"""

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Sensitive word / rule configuration
# ---------------------------------------------------------------------------

# Each category maps to a dict of { pattern: description }.
# Patterns support regex.  Plain strings are matched literally.
SENSITIVE_RULES: dict[str, dict[str, str]] = {
    "political": {
        "颠覆国家政权": "涉及颠覆国家政权相关表述",
        "分裂国家": "涉及分裂国家相关表述",
        "煽动暴乱": "涉及煽动暴乱相关表述",
        "反党反社会": "涉及反党反社会相关表述",
        "邪教": "涉及邪教相关表述",
        "法轮功": "涉及违禁组织相关表述",
        "推翻政府": "涉及推翻政府相关表述",
        "独立运动": "涉及独立运动相关表述",
        "政治迫害": "涉及政治迫害相关表述",
        "反动": "涉及反动相关表述",
        "叛国": "涉及叛国相关表述",
        "暴动": "涉及暴动相关表述",
        "游行示威": "涉及游行示威相关表述",
        "政变": "涉及政变相关表述",
    },
    "violence": {
        "暴力袭击": "涉及暴力袭击相关内容",
        "恐怖袭击": "涉及恐怖袭击相关内容",
        "制造炸弹": "涉及制造爆炸物相关内容",
        "枪支制造": "涉及非法武器制造相关内容",
        "杀人方法": "涉及危害人身安全相关内容",
        "暴力": "涉及暴力相关内容",
        "殴打": "涉及殴打相关内容",
        "杀害": "涉及杀害相关内容",
        "行凶": "涉及行凶相关内容",
        "凶杀": "涉及凶杀相关内容",
        "自杀方法": "涉及自杀方法相关内容",
        "爆炸": "涉及爆炸相关内容",
        "持刀": "涉及持刀相关内容",
        "血腥": "涉及血腥相关内容",
        "虐待": "涉及虐待相关内容",
        "施暴": "涉及施暴相关内容",
        "绑架": "涉及绑架相关内容",
    },
    "pornography": {
        "色情": "涉及色情相关内容",
        "淫秽": "涉及淫秽相关内容",
        "裸体": "涉及裸露相关内容",
        "性交易": "涉及性交易相关内容",
        "卖淫": "涉及卖淫相关内容",
        "嫖娼": "涉及嫖娼相关内容",
        "裸照": "涉及裸照相关内容",
        "黄色": "涉及黄色内容",
        "激情": "涉及激情相关内容",
        "情色": "涉及情色相关内容",
        "成人内容": "涉及成人内容",
        "性行为": "涉及性行为描述",
        "性爱": "涉及性爱相关内容",
        "做爱": "涉及性行为相关内容",
        "强奸": "涉及强奸相关内容",
        "猥亵": "涉及猥亵相关内容",
        "调情": "涉及调情相关内容",
        "勾引": "涉及勾引相关内容",
        "一夜情": "涉及一夜情相关内容",
        "约炮": "涉及约炮相关内容",
        "援交": "涉及援交相关内容",
        "性感": "涉及性感相关内容",
        "诱惑": "涉及诱惑相关内容",
        "脱衣": "涉及脱衣相关内容",
        "露骨": "涉及露骨相关内容",
        "下体": "涉及下体相关内容",
        "胸部": "涉及身体敏感部位描述",
        "臀部": "涉及身体敏感部位描述",
        "私处": "涉及身体私密部位描述",
        "风俗店": "涉及风俗店相关内容",
        "小姐": "涉及特殊服务相关内容",
        "包夜": "涉及特殊服务相关内容",
        "开房": "涉及开房相关内容",
        "上床": "涉及上床相关内容",
        "叫床": "涉及叫床相关内容",
        "自慰": "涉及自慰相关内容",
        "高潮": "涉及高潮相关内容",
        "AV": "涉及成人影片相关内容",
        "A片": "涉及成人影片相关内容",
        "黄片": "涉及黄色影片相关内容",
        "毛片": "涉及色情影片相关内容",
        "三级片": "涉及三级片相关内容",
        "porn": "涉及英文色情相关内容",
        "sex": "涉及英文性相关内容",
        "nude": "涉及英文裸露相关内容",
        "xxx": "涉及色情标记内容",
        "NSFW": "涉及不适宜工作场所内容",
    },
    "privacy": {
        r"(?<!\d)\d{17}[\dXx](?!\d)": "疑似身份证号码",
        r"(?<!\d)1[3-9]\d{9}(?!\d)": "疑似手机号码",
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}": "疑似电子邮箱地址",
        r"密码[:：]\s*\S+": "疑似明文密码泄露",
        r"身份证号?[:：]\s*\S+": "疑似身份证号泄露",
        r"手机号?[:：]\s*\S+": "疑似手机号泄露",
        r"银行卡号?[:：]\s*\S+": "疑似银行卡号泄露",
        r"家庭住址[:：]": "疑似家庭住址泄露",
        r"户籍地址[:：]": "疑似户籍地址泄露",
    },
    "compliance": {
        "内部机密": "涉及内部机密标记",
        "绝密": "涉及绝密等级标记",
        "机密": "涉及机密等级标记",
        "秘密": "涉及秘密等级标记",
        "商业秘密": "涉及商业秘密标记",
        "仅限内部": "涉及内部使用限制标记",
        "不得外传": "涉及传播限制标记",
        "禁止复制": "涉及复制限制标记",
        "内部资料": "涉及内部资料标记",
        "保密协议": "涉及保密协议相关内容",
        "未经授权": "涉及授权限制相关内容",
        "禁止传播": "涉及传播限制标记",
        "禁止转载": "涉及转载限制标记",
        "版权所有": "涉及版权声明",
        "内部使用": "涉及内部使用限制标记",
    },
}

# Human-readable category labels
CATEGORY_LABELS: dict[str, str] = {
    "political": "涉政敏感",
    "violence": "暴力相关",
    "pornography": "涉黄内容",
    "privacy": "隐私泄露",
    "compliance": "合规标记",
}

# Category → base severity weight (higher = more severe)
CATEGORY_WEIGHT: dict[str, int] = {
    "political": 10,
    "violence": 8,
    "pornography": 7,
    "privacy": 5,
    "compliance": 3,
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AuditHit:
    """A single audit finding."""
    category: str           # rule category key
    category_label: str     # human-readable category
    keyword: str            # matched keyword / pattern
    description: str        # rule description
    location: str           # e.g. "第3页", "第2段"
    context: str            # surrounding text snippet
    severity: str           # low / medium / high
    suggestion: str         # recommended action


@dataclass
class AuditResult:
    """Aggregated audit result for one document."""
    filename: str
    total_hits: int = 0
    risk_level: str = "safe"              # safe / low / medium / high
    hits: list[AuditHit] = field(default_factory=list)
    category_summary: dict[str, int] = field(default_factory=dict)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_CONTEXT_RADIUS = 40  # chars of context around a match


def _severity_for(category: str, count: int) -> str:
    """Determine severity for a single hit based on category weight."""
    w = CATEGORY_WEIGHT.get(category, 3)
    if w >= 8:
        return "high"
    if w >= 5:
        return "medium"
    return "low"


def _suggestion_for(category: str) -> str:
    suggestions = {
        "political": "建议删除或修改相关内容，避免涉政敏感表述",
        "violence": "建议删除暴力相关描述，使用温和表述替代",
        "pornography": "建议删除涉黄内容，确保文档符合规范",
        "privacy": "建议脱敏处理，使用***替代敏感信息",
        "compliance": "建议确认文档密级，按规定流程处理",
    }
    return suggestions.get(category, "建议人工复核相关内容")


def _extract_context(text: str, start: int, end: int) -> str:
    """Extract a text snippet around [start, end) with surrounding context."""
    ctx_start = max(0, start - _CONTEXT_RADIUS)
    ctx_end = min(len(text), end + _CONTEXT_RADIUS)
    prefix = "..." if ctx_start > 0 else ""
    suffix = "..." if ctx_end < len(text) else ""
    snippet = text[ctx_start:ctx_end].replace("\n", " ")
    return f"{prefix}{snippet}{suffix}"


def audit_text(
    text: str,
    location: str,
    categories: list[str] | None = None,
) -> list[AuditHit]:
    """Scan a single text block against configured rules.

    Args:
        text: The text to audit.
        location: Human-readable location label (e.g. "第1页").
        categories: If given, only check these categories.

    Returns:
        List of AuditHit instances.
    """
    hits: list[AuditHit] = []
    check_categories = categories or list(SENSITIVE_RULES.keys())

    for cat in check_categories:
        rules = SENSITIVE_RULES.get(cat, {})
        for pattern, desc in rules.items():
            try:
                for m in re.finditer(pattern, text):
                    hits.append(AuditHit(
                        category=cat,
                        category_label=CATEGORY_LABELS.get(cat, cat),
                        keyword=m.group(),
                        description=desc,
                        location=location,
                        context=_extract_context(text, m.start(), m.end()),
                        severity=_severity_for(cat, 1),
                        suggestion=_suggestion_for(cat),
                    ))
            except re.error:
                # If the pattern is not valid regex, do literal search
                idx = 0
                while True:
                    idx = text.find(pattern, idx)
                    if idx == -1:
                        break
                    hits.append(AuditHit(
                        category=cat,
                        category_label=CATEGORY_LABELS.get(cat, cat),
                        keyword=pattern,
                        description=desc,
                        location=location,
                        context=_extract_context(text, idx, idx + len(pattern)),
                        severity=_severity_for(cat, 1),
                        suggestion=_suggestion_for(cat),
                    ))
                    idx += len(pattern)
    return hits


def audit_sections(
    sections: list,
    filename: str,
    categories: list[str] | None = None,
) -> AuditResult:
    """Audit a list of DocumentSection objects.

    Args:
        sections: List of DocumentSection (from document_processor).
        filename: Original filename.
        categories: Optional list of category keys to check.

    Returns:
        AuditResult with all findings.
    """
    all_hits: list[AuditHit] = []
    cat_summary: dict[str, int] = {}

    for section in sections:
        meta = section.metadata
        # Build location string
        if "page" in meta:
            loc = f"第{meta['page']}页"
        elif "slide" in meta:
            loc = f"第{meta['slide']}张幻灯片"
        elif "sheet" in meta:
            loc = f"工作表: {meta['sheet']}"
        else:
            loc = "正文"

        hits = audit_text(section.text, loc, categories)
        all_hits.extend(hits)
        for h in hits:
            cat_summary[h.category_label] = cat_summary.get(h.category_label, 0) + 1

    # Determine overall risk level
    risk = _compute_risk_level(all_hits)

    return AuditResult(
        filename=filename,
        total_hits=len(all_hits),
        risk_level=risk,
        hits=all_hits,
        category_summary=cat_summary,
    )


def _compute_risk_level(hits: list[AuditHit]) -> str:
    if not hits:
        return "safe"
    max_weight = 0
    for h in hits:
        w = CATEGORY_WEIGHT.get(h.category, 3)
        if w > max_weight:
            max_weight = w
    total = len(hits)
    if max_weight >= 8 or total >= 10:
        return "high"
    if max_weight >= 5 or total >= 5:
        return "medium"
    return "low"


def get_available_categories() -> list[dict[str, str]]:
    """Return list of available audit categories for frontend config."""
    return [
        {"key": k, "label": v}
        for k, v in CATEGORY_LABELS.items()
    ]
