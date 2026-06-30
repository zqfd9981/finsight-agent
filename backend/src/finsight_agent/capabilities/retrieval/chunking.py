from __future__ import annotations

from dataclasses import dataclass

from .parsing_models import ChunkRecord, ParsedElement


@dataclass(slots=True)
class ChunkingResult:
    """单份文档的父子块生成结果。"""

    parents: list[ChunkRecord]
    children: list[ChunkRecord]


def build_chunks(
    document_id: str,
    elements: list[ParsedElement],
    parser_version: str,
    parent_target_chars: int,
    child_target_chars: int,
) -> ChunkingResult:
    """按结构优先、长度约束辅助的原则生成首版 parent / child。"""

    meaningful_elements = [
        element
        for element in elements
        if element.element_type not in {"page_header", "page_footer"}
    ]
    grouped_sections: list[tuple[list[str], list[ParsedElement]]] = []
    for element in meaningful_elements:
        current_path = list(element.section_path)
        if not grouped_sections or grouped_sections[-1][0] != current_path:
            grouped_sections.append((current_path, [element]))
            continue
        grouped_sections[-1][1].append(element)

    parents: list[ChunkRecord] = []
    children: list[ChunkRecord] = []
    parent_index = 0

    for section_path, section_elements in grouped_sections:
        if not _should_index_section(section_path, section_elements):
            continue

        # 同一 section 过长时，先按元素边界做一次轻量 parent 软拆分。
        parent_groups = _split_parent_elements(section_elements, parent_target_chars)
        for parent_group in parent_groups:
            parent_index += 1
            parent_id = f"{document_id}_parent_{parent_index:06d}"
            parents.append(
                ChunkRecord(
                    chunk_id=parent_id,
                    document_id=document_id,
                    chunk_level="parent",
                    parent_id=None,
                    chunk_text=_join_chunk_text(parent_group),
                    page_start=parent_group[0].page_start,
                    page_end=parent_group[-1].page_end,
                    page_anchor=parent_group[0].page_start,
                    section_path=section_path,
                    element_ids=[element.element_id for element in parent_group],
                    order_in_document=parent_group[0].order_in_document,
                    source_parser=parent_group[0].parser_source,
                    created_from_parser_version=parser_version,
                )
            )

            # 首版普通 child 只消费正文、列表和图表说明，不直接塞入表格本体。
            child_elements = [
                element
                for element in parent_group
                if element.element_type in {"paragraph", "list_item", "table_caption", "figure_caption"}
            ]
            if not child_elements:
                continue

            child_groups = _split_child_elements(child_elements, child_target_chars)
            for child_index, child_group in enumerate(child_groups, start=1):
                child_id = f"{document_id}_child_{parent_index:06d}_{child_index:02d}"
                children.append(
                    ChunkRecord(
                        chunk_id=child_id,
                        document_id=document_id,
                        chunk_level="child",
                        parent_id=parent_id,
                        chunk_text=_join_chunk_text(child_group),
                        page_start=child_group[0].page_start,
                        page_end=child_group[-1].page_end,
                        page_anchor=child_group[0].page_start,
                        section_path=section_path,
                        element_ids=[element.element_id for element in child_group],
                        order_in_document=child_group[0].order_in_document,
                        source_parser=child_group[0].parser_source,
                        created_from_parser_version=parser_version,
                    )
                )

    return ChunkingResult(parents=parents, children=children)


def _should_index_section(section_path: list[str], section_elements: list[ParsedElement]) -> bool:
    """决定一个 section 是否进入默认检索 chunk 链路。"""

    if not section_elements:
        return False

    # 没有章节归属的内容通常是封面、前言或董事长致辞，首版先不进入检索主链路。
    if not section_path:
        return False

    section_label = section_path[-1]

    # “备查文件目录”里的附件清单不属于用户主要检索正文。
    if section_label.startswith(("（一）载有", "（二）载有", "（三）载有", "(一)载有", "(二)载有", "(三)载有")):
        return False

    # 释义表主要用于辅助阅读，不作为首版主检索正文。
    if _looks_like_glossary_section(section_elements):
        return False

    return True


def _looks_like_glossary_section(section_elements: list[ParsedElement]) -> bool:
    """根据术语表的典型行文样式识别释义型 section。"""

    glossary_like_count = 0
    for element in section_elements:
        text = element.text.strip()
        if not text:
            continue
        if " 指 " in text:
            glossary_like_count += 1
            continue
        if text in {"释义", "释义项 指 释义内容"}:
            glossary_like_count += 1
            continue

    return glossary_like_count >= 2


def _join_chunk_text(elements: list[ParsedElement]) -> str:
    """按元素顺序拼接文本，避免把空文本带进 chunk。"""

    return "\n".join(element.text for element in elements if element.text.strip())


def _split_parent_elements(
    elements: list[ParsedElement],
    parent_target_chars: int,
) -> list[list[ParsedElement]]:
    """按元素边界对超长 section 做轻量 parent 软拆分。"""

    return _split_elements_by_target(elements, parent_target_chars)


def _split_child_elements(
    elements: list[ParsedElement],
    child_target_chars: int,
) -> list[list[ParsedElement]]:
    """按目标长度把语义元素切成多个 child。"""

    return _split_elements_by_target(elements, child_target_chars)


def _split_elements_by_target(
    elements: list[ParsedElement],
    target_chars: int,
) -> list[list[ParsedElement]]:
    """按元素累计字符数切分，保证切分发生在元素边界而不是字符中间。"""

    groups: list[list[ParsedElement]] = []
    current_group: list[ParsedElement] = []
    current_length = 0

    for element in elements:
        element_length = len(element.text.strip())
        if current_group and current_length + element_length > target_chars:
            groups.append(current_group)
            current_group = []
            current_length = 0

        current_group.append(element)
        current_length += element_length

    if current_group:
        groups.append(current_group)
    return groups
