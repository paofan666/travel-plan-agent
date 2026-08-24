from __future__ import annotations

import re


_RAG_CONTEXT_TITLE_PATTERN = re.compile(r"^\[来源:\s*.+?\s*\|\s*标题:\s*(?P<title>.+?)\]$")
_MARKDOWN_HEADING_NUMBER_PATTERN = re.compile(r"^\d+(?:\.\d+)*\s+")
_MEAL_NAME_PATTERN = re.compile(r"【(?P<name>[^】]+)】招牌菜")
_HOTEL_NAME_PATTERN = re.compile(r"【(?P<name>[^】]+)】[^\n]*酒店预算")


def _append_unique(candidates: list[str], value: str | None) -> None:
    """追加清洗后的候选名称，同时保持顺序并去重。

    Args:
        candidates: 原地维护的候选名称列表。
        value: 待追加的名称，允许为空。

    Returns:
        None: 候选列表直接在原对象上更新。
    """
    normalized = (value or "").strip()
    if normalized and normalized not in candidates:
        candidates.append(normalized)


def _extract_spot_names(rag_contexts: list[str]) -> list[str]:
    """从 RAG 上下文的景点条目中提取可追溯的地点名称。

    Args:
        rag_contexts: 带来源和标题头的攻略检索片段。

    Returns:
        list[str]: 按首次出现顺序排列的真实景点名称。
    """
    candidates: list[str] = []
    for context in rag_contexts:
        header, separator, body = context.partition("\n")
        if not separator or "**位置**" not in body:
            continue

        match = _RAG_CONTEXT_TITLE_PATTERN.match(header.strip())
        if match is None:
            continue
        _append_unique(
            candidates,
            _MARKDOWN_HEADING_NUMBER_PATTERN.sub("", match.group("title")).strip(),
        )
    return candidates


def _extract_entity_names(rag_contexts: list[str], pattern: re.Pattern[str]) -> list[str]:
    """使用指定规则从攻略上下文提取餐饮或住宿实体。

    Args:
        rag_contexts: 待扫描的攻略检索片段。
        pattern: 包含 ``name`` 命名分组的实体匹配规则。

    Returns:
        list[str]: 去重后且顺序稳定的实体名称。
    """
    candidates: list[str] = []
    for context in rag_contexts:
        for match in pattern.finditer(context):
            _append_unique(candidates, match.group("name"))
    return candidates


def extract_fallback_candidates(rag_contexts: list[str]) -> dict[str, list[str]]:
    """按行程 fallback 的正式规则提取真实景点、餐饮和住宿候选。"""
    return {
        "spots": _extract_spot_names(rag_contexts),
        "meals": _extract_entity_names(rag_contexts, _MEAL_NAME_PATTERN),
        "hotels": _extract_entity_names(rag_contexts, _HOTEL_NAME_PATTERN),
    }
