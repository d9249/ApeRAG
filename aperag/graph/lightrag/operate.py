# Copyright 2025 ApeCloud, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
LightRAG Module for ApeRAG

This module is based on the original LightRAG project with extensive modifications.

Original Project:
- Repository: https://github.com/HKUDS/LightRAG
- Paper: "LightRAG: Simple and Fast Retrieval-Augmented Generation" (arXiv:2410.05779)
- Authors: Zirui Guo, Lianghao Xia, Yanhua Yu, Tu Ao, Chao Huang
- License: MIT License

Modifications by ApeRAG Team:
- Removed global state management for true concurrent processing
- Added stateless interfaces for Celery/Prefect integration
- Implemented instance-level locking mechanism
- Enhanced error handling and stability
- See changelog.md for detailed modifications
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import Counter, defaultdict
from typing import Any, AsyncIterator

from aperag.concurrent_control import get_or_create_lock

from .base import (
    BaseGraphStorage,
    BaseKVStorage,
    BaseVectorStorage,
    QueryParam,
    TextChunkSchema,
)
from .prompt import GRAPH_FIELD_SEP, PROMPTS
from .types import GraphNodeData, GraphNodeDataDict, MergeSuggestion
from .utils import (
    LightRAGLogger,
    Tokenizer,
    clean_str,
    compute_mdhash_id,
    get_conversation_turns,
    is_float_regex,
    logger,
    normalize_extracted_info,
    pack_user_ass_to_openai_messages,
    process_combine_contexts,
    split_string_by_multi_markers,
    timing_wrapper,
    truncate_list_by_token_size,
)


def chunking_by_token_size(
    tokenizer: Tokenizer,
    content: str,
    split_by_character: str | None = None,
    split_by_character_only: bool = False,
    overlap_token_size: int = 128,
    max_token_size: int = 1024,
) -> list[dict[str, Any]]:
    tokens = tokenizer.encode(content)
    results: list[dict[str, Any]] = []
    if split_by_character:
        raw_chunks = content.split(split_by_character)
        new_chunks = []
        if split_by_character_only:
            for chunk in raw_chunks:
                _tokens = tokenizer.encode(chunk)
                new_chunks.append((len(_tokens), chunk))
        else:
            for chunk in raw_chunks:
                _tokens = tokenizer.encode(chunk)
                if len(_tokens) > max_token_size:
                    for start in range(0, len(_tokens), max_token_size - overlap_token_size):
                        chunk_content = tokenizer.decode(_tokens[start : start + max_token_size])
                        new_chunks.append((min(max_token_size, len(_tokens) - start), chunk_content))
                else:
                    new_chunks.append((len(_tokens), chunk))
        for index, (_len, chunk) in enumerate(new_chunks):
            results.append(
                {
                    "tokens": _len,
                    "content": chunk.strip(),
                    "chunk_order_index": index,
                }
            )
    else:
        for index, start in enumerate(range(0, len(tokens), max_token_size - overlap_token_size)):
            chunk_content = tokenizer.decode(tokens[start : start + max_token_size])
            results.append(
                {
                    "tokens": min(max_token_size, len(tokens) - start),
                    "content": chunk_content.strip(),
                    "chunk_order_index": index,
                }
            )
    return results


@timing_wrapper("_handle_entity_relation_summary")
async def _handle_entity_relation_summary(
    entity_or_relation_name: str,
    description: str,
    llm_model_func: callable,
    tokenizer: Tokenizer,
    llm_model_max_token_size: int,
    summary_to_max_tokens: int,
    language: str,
    lightrag_logger: LightRAGLogger,
) -> str:
    """Handle entity relation summary
    For each entity or relation, input is the combined description of already existing description and new description.
    If too long, use LLM to summarize.
    """
    use_llm_func: callable = llm_model_func

    tokens = tokenizer.encode(description)

    prompt_template = PROMPTS["summarize_entity_descriptions"]
    use_description = tokenizer.decode(tokens[:llm_model_max_token_size])
    context_base = dict(
        entity_name=entity_or_relation_name,
        description_list=use_description.split(GRAPH_FIELD_SEP),
        language=language,
    )
    use_prompt = prompt_template.format(**context_base)

    lightrag_logger.debug(f"Trigger summary: {entity_or_relation_name}")

    summary = await use_llm_func(use_prompt, max_tokens=summary_to_max_tokens)
    return summary


async def _handle_single_entity_extraction(
    record_attributes: list[str],
    chunk_key: str,
    file_path: str = "unknown_source",
):
    if len(record_attributes) < 4 or '"entity"' not in record_attributes[0]:
        return None

    # Clean and validate entity name
    entity_name = clean_str(record_attributes[1]).strip()
    if not entity_name:
        logger.warning(f"Entity extraction error: empty entity name in: {record_attributes}")
        return None

    # Normalize entity name
    entity_name = normalize_extracted_info(entity_name, is_entity=True)

    # Clean and validate entity type
    entity_type = clean_str(record_attributes[2]).strip('"')
    if not entity_type.strip() or entity_type.startswith('("'):
        logger.warning(f"Entity extraction error: invalid entity type in: {record_attributes}")
        return None

    # Clean and validate description
    entity_description = clean_str(record_attributes[3])
    entity_description = normalize_extracted_info(entity_description)

    if not entity_description.strip():
        logger.warning(f"Entity extraction error: empty description for entity '{entity_name}' of type '{entity_type}'")
        return None

    return dict(
        entity_name=entity_name,
        entity_type=entity_type,
        description=entity_description,
        source_id=chunk_key,
        file_path=file_path,
    )


async def _handle_single_relationship_extraction(
    record_attributes: list[str],
    chunk_key: str,
    file_path: str = "unknown_source",
):
    if len(record_attributes) < 5 or '"relationship"' not in record_attributes[0]:
        return None
    # add this record as edge
    source = clean_str(record_attributes[1])
    target = clean_str(record_attributes[2])

    # Normalize source and target entity names
    source = normalize_extracted_info(source, is_entity=True)
    target = normalize_extracted_info(target, is_entity=True)
    if source == target:
        logger.debug(f"Relationship source and target are the same in: {record_attributes}")
        return None

    edge_description = clean_str(record_attributes[3])
    edge_description = normalize_extracted_info(edge_description)

    edge_keywords = normalize_extracted_info(clean_str(record_attributes[4]), is_entity=True)
    edge_keywords = edge_keywords.replace("，", ",")

    edge_source_id = chunk_key
    weight = (
        float(record_attributes[-1].strip('"').strip("'"))
        if is_float_regex(record_attributes[-1].strip('"').strip("'"))
        else 1.0
    )
    return dict(
        src_id=source,
        tgt_id=target,
        weight=weight,
        description=edge_description,
        keywords=edge_keywords,
        source_id=edge_source_id,
        file_path=file_path,
    )


async def _merge_nodes_then_upsert(
    entity_name: str,
    nodes_data: list[dict],
    knowledge_graph_inst: BaseGraphStorage,
    llm_model_func: callable,
    tokenizer: Tokenizer,
    llm_model_max_token_size: int,
    summary_to_max_tokens: int,
    language: str,
    force_llm_summary_on_merge: int,
    lightrag_logger: LightRAGLogger | None = None,
    workspace: str = "",
):
    """
    Merge multiple entity nodes with the same name and upsert the result to knowledge graph.

    This function handles entity deduplication by:
    1. Retrieving existing entity data from knowledge graph
    2. Merging existing data with new entity data
    3. Determining the final entity properties through aggregation
    4. Optionally using LLM to summarize lengthy descriptions
    5. Upserting the merged entity back to knowledge graph

    Args:
        entity_name: The name of the entity to merge
        nodes_data: List of new entity data dictionaries to merge
        knowledge_graph_inst: Knowledge graph storage instance
        llm_model_func: LLM function for description summarization
        tokenizer: Tokenizer for text processing
        llm_model_max_token_size: Maximum token size for LLM input
        summary_to_max_tokens: Maximum tokens for summary output
        language: Language for LLM summarization
        force_llm_summary_on_merge: Threshold for triggering LLM summarization
        lightrag_logger: Optional logger instance
        workspace: Workspace identifier for lock creation

    Returns:
        dict: The merged node data that was upserted
    """

    # 1. Initialize containers for collecting existing entity data
    already_entity_types = []
    already_source_ids = []
    already_description = []
    already_file_paths = []

    # 2. Retrieve existing entity from knowledge graph if it exists
    already_node = await knowledge_graph_inst.get_node(entity_name)
    if already_node:
        # 2.1. Collect existing entity type
        already_entity_types.append(already_node["entity_type"])

        # 2.2. Split and collect existing source IDs (multiple IDs separated by GRAPH_FIELD_SEP)
        already_source_ids.extend(split_string_by_multi_markers(already_node["source_id"], [GRAPH_FIELD_SEP]))

        # 2.3. Split and collect existing file paths (multiple paths separated by GRAPH_FIELD_SEP)
        already_file_paths.extend(split_string_by_multi_markers(already_node["file_path"], [GRAPH_FIELD_SEP]))

        # 2.4. Collect existing description
        already_description.append(already_node["description"])

    # 3. Merge and determine final entity properties

    # 3.1. Determine entity type by frequency count (most common type wins)
    entity_type = sorted(
        Counter([dp["entity_type"] for dp in nodes_data] + already_entity_types).items(),
        key=lambda x: x[1],
        reverse=True,
    )[0][0]

    # 3.2. Merge descriptions with field separator, sorted and deduplicated
    description = GRAPH_FIELD_SEP.join(sorted(set([dp["description"] for dp in nodes_data] + already_description)))

    # 3.3. Merge source IDs, deduplicated
    source_id = GRAPH_FIELD_SEP.join(set([dp["source_id"] for dp in nodes_data] + already_source_ids))

    # 3.4. Merge file paths, deduplicated
    file_path = GRAPH_FIELD_SEP.join(set([dp["file_path"] for dp in nodes_data] + already_file_paths))

    # 4. Calculate description fragment counts for summarization decision
    num_fragment = description.count(GRAPH_FIELD_SEP) + 1  # Total description fragments
    num_new_fragment = len(set([dp["description"] for dp in nodes_data]))  # New unique descriptions

    # 5. Handle description summarization if there are multiple fragments
    if num_fragment > 1:
        # 5.1. Check if LLM summarization threshold is met
        if num_fragment >= force_llm_summary_on_merge:
            # 5.1.1. Log LLM summarization decision
            lightrag_logger.log_entity_merge(entity_name, num_fragment, num_new_fragment, is_llm_summary=True)

            # 5.1.2. Use LLM to summarize lengthy descriptions
            description = await _handle_entity_relation_summary(
                entity_name,
                description,
                llm_model_func,
                tokenizer,
                llm_model_max_token_size,
                summary_to_max_tokens,
                language,
                lightrag_logger,
            )
        else:
            # 5.2. Simple merge without LLM summarization (fragment count below threshold)
            lightrag_logger.log_entity_merge(entity_name, num_fragment, num_new_fragment, is_llm_summary=False)

    # 6. Create final node data structure
    node_data = dict(
        entity_id=entity_name,
        entity_type=entity_type,
        description=description,
        source_id=source_id,
        file_path=file_path,
        created_at=int(time.time()),
    )

    # 7. Upsert the merged entity to knowledge graph
    await knowledge_graph_inst.upsert_node(
        entity_name,
        node_data=node_data,
    )

    # 8. Add entity_name to returned data and return the final merged entity
    node_data["entity_name"] = entity_name
    return node_data


async def _merge_edges_then_upsert(
    src_id: str,
    tgt_id: str,
    edges_data: list[dict],
    knowledge_graph_inst: BaseGraphStorage,
    llm_model_func: callable,
    tokenizer: Tokenizer,
    llm_model_max_token_size: int,
    summary_to_max_tokens: int,
    language: str,
    force_llm_summary_on_merge: int,
    lightrag_logger: LightRAGLogger,
    workspace: str = "",
):
    if src_id == tgt_id:
        return None

    already_weights = []
    already_source_ids = []
    already_description = []
    already_keywords = []
    already_file_paths = []

    if await knowledge_graph_inst.has_edge(src_id, tgt_id):
        already_edge = await knowledge_graph_inst.get_edge(src_id, tgt_id)
        # Handle the case where get_edge returns None or missing fields
        if already_edge:
            # Get weight with default 0.0 if missing
            already_weights.append(already_edge.get("weight", 0.0))

            # Get source_id with empty string default if missing or None
            if already_edge.get("source_id") is not None:
                already_source_ids.extend(split_string_by_multi_markers(already_edge["source_id"], [GRAPH_FIELD_SEP]))

            # Get file_path with empty string default if missing or None
            if already_edge.get("file_path") is not None:
                already_file_paths.extend(split_string_by_multi_markers(already_edge["file_path"], [GRAPH_FIELD_SEP]))

            # Get description with empty string default if missing or None
            if already_edge.get("description") is not None:
                already_description.append(already_edge["description"])

            # Get keywords with empty string default if missing or None
            if already_edge.get("keywords") is not None:
                already_keywords.extend(split_string_by_multi_markers(already_edge["keywords"], [GRAPH_FIELD_SEP]))

    # Process edges_data with None checks
    weight = sum([dp["weight"] for dp in edges_data] + already_weights)
    description = GRAPH_FIELD_SEP.join(
        sorted(set([dp["description"] for dp in edges_data if dp.get("description")] + already_description))
    )

    # Split all existing and new keywords into individual terms, then combine and deduplicate
    all_keywords = set()
    # Process already_keywords (which are comma-separated)
    for keyword_str in already_keywords:
        if keyword_str:  # Skip empty strings
            all_keywords.update(k.strip() for k in keyword_str.split(",") if k.strip())
    # Process new keywords from edges_data
    for edge in edges_data:
        if edge.get("keywords"):
            all_keywords.update(k.strip() for k in edge["keywords"].split(",") if k.strip())
    # Join all unique keywords with commas
    keywords = ",".join(sorted(all_keywords))

    source_id = GRAPH_FIELD_SEP.join(
        set([dp["source_id"] for dp in edges_data if dp.get("source_id")] + already_source_ids)
    )
    file_path = GRAPH_FIELD_SEP.join(
        set([dp["file_path"] for dp in edges_data if dp.get("file_path")] + already_file_paths)
    )

    for need_insert_id in [src_id, tgt_id]:
        if not (await knowledge_graph_inst.has_node(need_insert_id)):
            await knowledge_graph_inst.upsert_node(
                need_insert_id,
                node_data={
                    "entity_id": need_insert_id,
                    "source_id": source_id,
                    "description": description,
                    "entity_type": "UNKNOWN",
                    "file_path": file_path,
                    "created_at": int(time.time()),
                },
            )

    num_fragment = description.count(GRAPH_FIELD_SEP) + 1
    num_new_fragment = len(set([dp["description"] for dp in edges_data if dp.get("description")]))

    if num_fragment > 1:
        if num_fragment >= force_llm_summary_on_merge:
            lightrag_logger.log_relation_merge(src_id, tgt_id, num_fragment, num_new_fragment, is_llm_summary=True)

            description = await _handle_entity_relation_summary(
                f"({src_id}, {tgt_id})",
                description,
                llm_model_func,
                tokenizer,
                llm_model_max_token_size,
                summary_to_max_tokens,
                language,
                lightrag_logger,
            )
        else:
            lightrag_logger.log_relation_merge(src_id, tgt_id, num_fragment, num_new_fragment, is_llm_summary=False)

    await knowledge_graph_inst.upsert_edge(
        src_id,
        tgt_id,
        edge_data=dict(
            weight=weight,
            description=description,
            keywords=keywords,
            source_id=source_id,
            file_path=file_path,
            created_at=int(time.time()),
        ),
    )

    edge_data = dict(
        src_id=src_id,
        tgt_id=tgt_id,
        description=description,
        keywords=keywords,
        source_id=source_id,
        file_path=file_path,
        created_at=int(time.time()),
    )

    return edge_data


@timing_wrapper("merge_nodes_and_edges")
async def merge_nodes_and_edges(
    chunk_results: list,
    component: list[str],
    workspace: str,
    knowledge_graph_inst: BaseGraphStorage,
    entity_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    llm_model_func,
    tokenizer,
    llm_model_max_token_size,
    summary_to_max_tokens,
    addon_params,
    force_llm_summary_on_merge,
    lightrag_logger: LightRAGLogger,
) -> dict[str, int]:
    # Now using fine-grained locking inside _merge_nodes_and_edges_impl
    return await _merge_nodes_and_edges_impl(
        chunk_results,
        workspace,
        knowledge_graph_inst,
        entity_vdb,
        relationships_vdb,
        llm_model_func,
        tokenizer,
        llm_model_max_token_size,
        summary_to_max_tokens,
        addon_params,
        force_llm_summary_on_merge,
        lightrag_logger,
    )


async def _merge_nodes_and_edges_impl(
    chunk_results: list,
    workspace: str,
    knowledge_graph_inst: BaseGraphStorage,
    entity_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    llm_model_func,
    tokenizer,
    llm_model_max_token_size,
    summary_to_max_tokens,
    addon_params,
    force_llm_summary_on_merge,
    lightrag_logger: LightRAGLogger,
) -> dict[str, int]:
    """Internal implementation of merge_nodes_and_edges with fine-grained locking"""

    # Extract language from addon_params
    language = addon_params.get("language", "English")

    # Collect all nodes and edges from all chunks
    all_nodes = defaultdict(list)
    all_edges = defaultdict(list)

    for maybe_nodes, maybe_edges in chunk_results:
        # Collect nodes
        for entity_name, entities in maybe_nodes.items():
            all_nodes[entity_name].extend(entities)

        # Collect edges with sorted keys for undirected graph
        for edge_key, edges in maybe_edges.items():
            sorted_edge_key = tuple(sorted(edge_key))
            all_edges[sorted_edge_key].extend(edges)

    # Process entities with fine-grained locking
    entity_count = 0

    for entity_name, entities in all_nodes.items():
        # Create lock for this specific entity
        entity_lock = get_or_create_lock(f"entity:{entity_name}:{workspace}")

        async with entity_lock:
            # Process and update entity in graph db
            entity_data = await _merge_nodes_then_upsert(
                entity_name,
                entities,
                knowledge_graph_inst,
                llm_model_func,
                tokenizer,
                llm_model_max_token_size,
                summary_to_max_tokens,
                language,  # Pass language instead of addon_params
                force_llm_summary_on_merge,
                lightrag_logger,
                workspace,
            )

            # Update entity in vector db immediately under the same lock
            if entity_vdb is not None and entity_data:
                vdb_data = {
                    compute_mdhash_id(entity_data["entity_name"], prefix="ent-", workspace=workspace): {
                        "entity_name": entity_data["entity_name"],
                        "entity_type": entity_data["entity_type"],
                        "content": f"{entity_data['entity_name']}\n{entity_data['description']}",
                        "source_id": entity_data["source_id"],
                        "file_path": entity_data.get("file_path", "unknown_source"),
                    }
                }
                await entity_vdb.upsert(vdb_data)

            entity_count += 1

    # Process relationships with fine-grained locking
    relation_count = 0

    for edge_key, edges in all_edges.items():
        # Create lock for this specific relationship
        # Sort edge key to ensure consistent lock naming
        sorted_edge_key = tuple(sorted(edge_key))
        relationship_lock = get_or_create_lock(f"relationship:{sorted_edge_key[0]}:{sorted_edge_key[1]}:{workspace}")

        async with relationship_lock:
            # Process and update relationship in graph db
            edge_data = await _merge_edges_then_upsert(
                edge_key[0],
                edge_key[1],
                edges,
                knowledge_graph_inst,
                llm_model_func,
                tokenizer,
                llm_model_max_token_size,
                summary_to_max_tokens,
                language,  # Pass language instead of addon_params
                force_llm_summary_on_merge,
                lightrag_logger,
                workspace,
            )

            # Update relationship in vector db immediately under the same lock
            if relationships_vdb is not None and edge_data is not None:
                vdb_data = {
                    compute_mdhash_id(edge_data["src_id"] + edge_data["tgt_id"], prefix="rel-", workspace=workspace): {
                        "src_id": edge_data["src_id"],
                        "tgt_id": edge_data["tgt_id"],
                        "keywords": edge_data["keywords"],
                        "content": f"{edge_data['src_id']}\t{edge_data['tgt_id']}\n{edge_data['keywords']}\n{edge_data['description']}",
                        "source_id": edge_data["source_id"],
                        "file_path": edge_data.get("file_path", "unknown_source"),
                    }
                }
                await relationships_vdb.upsert(vdb_data)

            if edge_data is not None:
                relation_count += 1

    return {"entity_count": entity_count, "relation_count": relation_count}


@timing_wrapper("extract_entities")
async def extract_entities(
    chunks: dict[str, TextChunkSchema],
    use_llm_func: callable,
    entity_extract_max_gleaning: int,
    addon_params: dict,
    llm_model_max_async: int,
    lightrag_logger: LightRAGLogger,
) -> list:
    ordered_chunks = list(chunks.items())
    # add language and example number params to prompt
    language = addon_params.get("language", PROMPTS["DEFAULT_LANGUAGE"])
    entity_types = addon_params.get("entity_types", PROMPTS["DEFAULT_ENTITY_TYPES"])
    example_number = addon_params.get("example_number", None)
    if example_number and example_number < len(PROMPTS["entity_extraction_examples"]):
        examples = "\n".join(PROMPTS["entity_extraction_examples"][: int(example_number)])
    else:
        examples = "\n".join(PROMPTS["entity_extraction_examples"])

    example_context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=", ".join(entity_types),
        language=language,
    )
    # add example's format
    examples = examples.format(**example_context_base)

    entity_extract_prompt = PROMPTS["entity_extraction"]
    context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=",".join(entity_types),
        examples=examples,
        language=language,
    )

    continue_prompt = PROMPTS["entity_continue_extraction"].format(**context_base)
    if_loop_prompt = PROMPTS["entity_if_loop_extraction"]

    processed_chunks = 0
    total_chunks = len(ordered_chunks)

    async def _process_extraction_result(result: str, chunk_key: str, file_path: str = "unknown_source"):
        """Process a single extraction result (either initial or gleaning)
        Args:
            result (str): The extraction result to process
            chunk_key (str): The chunk key for source tracking
            file_path (str): The file path for citation
        Returns:
            tuple: (nodes_dict, edges_dict) containing the extracted entities and relationships
        """
        maybe_nodes = defaultdict(list)
        maybe_edges = defaultdict(list)

        records = split_string_by_multi_markers(
            result,
            [context_base["record_delimiter"], context_base["completion_delimiter"]],
        )

        for record in records:
            record = re.search(r"\((.*)\)", record)
            if record is None:
                continue
            record = record.group(1)
            record_attributes = split_string_by_multi_markers(record, [context_base["tuple_delimiter"]])

            if_entities = await _handle_single_entity_extraction(record_attributes, chunk_key, file_path)
            if if_entities is not None:
                maybe_nodes[if_entities["entity_name"]].append(if_entities)
                continue

            if_relation = await _handle_single_relationship_extraction(record_attributes, chunk_key, file_path)
            if if_relation is not None:
                maybe_edges[(if_relation["src_id"], if_relation["tgt_id"])].append(if_relation)

        return maybe_nodes, maybe_edges

    async def _process_single_content(chunk_key_dp: tuple[str, TextChunkSchema]):
        """Process a single chunk
        Args:
            chunk_key_dp (tuple[str, TextChunkSchema]):
                ("chunk-xxxxxx", {"tokens": int, "content": str, "full_doc_id": str, "chunk_order_index": int})
        Returns:
            tuple: (maybe_nodes, maybe_edges) containing extracted entities and relationships
        """
        nonlocal processed_chunks
        chunk_key = chunk_key_dp[0]
        chunk_dp = chunk_key_dp[1]
        content = chunk_dp["content"]
        # Get file path from chunk data or use default
        file_path = chunk_dp.get("file_path", "unknown_source")

        # Get initial extraction
        hint_prompt = entity_extract_prompt.format(**{**context_base, "input_text": content})

        final_result = await use_llm_func(hint_prompt)
        history = pack_user_ass_to_openai_messages(hint_prompt, final_result)

        # Process initial extraction with file path
        maybe_nodes, maybe_edges = await _process_extraction_result(final_result, chunk_key, file_path)

        # Process additional gleaning results
        for now_glean_index in range(entity_extract_max_gleaning):
            glean_result = await use_llm_func(continue_prompt, history_messages=history)

            history += pack_user_ass_to_openai_messages(continue_prompt, glean_result)

            # Process gleaning result separately with file path
            glean_nodes, glean_edges = await _process_extraction_result(glean_result, chunk_key, file_path)

            # Merge results - only add entities and edges with new names
            for entity_name, entities in glean_nodes.items():
                if entity_name not in maybe_nodes:  # Only accetp entities with new name in gleaning stage
                    maybe_nodes[entity_name].extend(entities)
            for edge_key, edges in glean_edges.items():
                if edge_key not in maybe_edges:  # Only accetp edges with new name in gleaning stage
                    maybe_edges[edge_key].extend(edges)

            if now_glean_index == entity_extract_max_gleaning - 1:
                break

            if_loop_result: str = await use_llm_func(if_loop_prompt, history_messages=history)
            if_loop_result = if_loop_result.strip().strip('"').strip("'").lower()
            if if_loop_result != "yes":
                break

        processed_chunks += 1
        entities_count = len(maybe_nodes)
        relations_count = len(maybe_edges)

        lightrag_logger.log_extraction_progress(processed_chunks, total_chunks, entities_count, relations_count)

        # Return the extracted nodes and edges for centralized processing
        return maybe_nodes, maybe_edges

    # Get max async tasks limit
    semaphore = asyncio.Semaphore(llm_model_max_async)

    async def _process_with_semaphore(chunk):
        async with semaphore:
            return await _process_single_content(chunk)

    tasks = []
    for c in ordered_chunks:
        task = asyncio.create_task(_process_with_semaphore(c))
        tasks.append(task)

    # Wait for tasks to complete or for the first exception to occur
    # This allows us to cancel remaining tasks if any task fails
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    # Check if any task raised an exception
    for task in done:
        if task.exception():
            # If a task failed, cancel all pending tasks
            # This prevents unnecessary processing since the parent function will abort anyway
            for pending_task in pending:
                pending_task.cancel()

            # Wait for cancellation to complete
            if pending:
                await asyncio.wait(pending)

            # Re-raise the exception to notify the caller
            raise task.exception()

    # If all tasks completed successfully, collect results
    chunk_results = [task.result() for task in tasks]

    # Return the chunk_results for later processing in merge_nodes_and_edges
    return chunk_results


async def build_query_context(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    tokenizer: Tokenizer,
    llm_model_func: callable,
    addon_params: dict,
    chunks_vdb: BaseVectorStorage = None,
):
    if query_param.model_func:
        use_model_func = query_param.model_func
    else:
        use_model_func = llm_model_func

    hl_keywords, ll_keywords = await get_keywords_from_query(
        query, query_param, tokenizer, use_model_func, addon_params
    )

    logger.debug(f"High-level keywords: {hl_keywords}")
    logger.debug(f"Low-level  keywords: {ll_keywords}")

    # Handle empty keywords
    if hl_keywords == [] and ll_keywords == []:
        logger.warning("low_level_keywords and high_level_keywords is empty")
        return None
    if ll_keywords == [] and query_param.mode in ["local", "hybrid"]:
        logger.warning(
            "low_level_keywords is empty, switching from %s mode to global mode",
            query_param.mode,
        )
        query_param.mode = "global"
    if hl_keywords == [] and query_param.mode in ["global", "hybrid"]:
        logger.warning(
            "high_level_keywords is empty, switching from %s mode to local mode",
            query_param.mode,
        )
        query_param.mode = "local"

    ll_keywords_str = ", ".join(ll_keywords) if ll_keywords else ""
    hl_keywords_str = ", ".join(hl_keywords) if hl_keywords else ""

    # Build context
    return await _build_query_context_from_keywords(
        ll_keywords_str,
        hl_keywords_str,
        knowledge_graph_inst,
        entities_vdb,
        relationships_vdb,
        text_chunks_db,
        query_param,
        tokenizer,
        chunks_vdb,
    )


async def kg_query(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    tokenizer: Tokenizer,
    llm_model_func: callable,
    addon_params: dict,
    system_prompt: str | None = None,
    chunks_vdb: BaseVectorStorage = None,
) -> str | AsyncIterator[str]:
    if query_param.model_func:
        use_model_func = query_param.model_func
    else:
        use_model_func = llm_model_func

    # Build context
    entities_context, relations_context, text_units_context = await build_query_context(
        query,
        knowledge_graph_inst,
        entities_vdb,
        relationships_vdb,
        text_chunks_db,
        query_param,
        tokenizer,
        llm_model_func,
        addon_params,
        chunks_vdb,
    )

    # 转换为 JSON 字符串
    entities_str = json.dumps(entities_context, ensure_ascii=False)
    relations_str = json.dumps(relations_context, ensure_ascii=False)
    text_units_str = json.dumps(text_units_context, ensure_ascii=False)

    context = f"""-----Entities(KG)-----

    ```json
    {entities_str}
    ```

    -----Relationships(KG)-----

    ```json
    {relations_str}
    ```

    -----Document Chunks(DC)-----

    ```json
    {text_units_str}
    ```

    """

    if query_param.only_need_context:
        return context
    if context is None:
        return PROMPTS["fail_response"]

    # Process conversation history
    history_context = ""
    if query_param.conversation_history:
        history_context = get_conversation_turns(query_param.conversation_history, query_param.history_turns)

    # Build system prompt
    user_prompt = query_param.user_prompt if query_param.user_prompt else PROMPTS["DEFAULT_USER_PROMPT"]
    sys_prompt_temp = system_prompt if system_prompt else PROMPTS["rag_response"]
    sys_prompt = sys_prompt_temp.format(
        context_data=context,
        response_type=query_param.response_type,
        history=history_context,
        user_prompt=user_prompt,
    )

    if query_param.only_need_prompt:
        return sys_prompt

    len_of_prompts = len(tokenizer.encode(query + sys_prompt))
    logger.debug(f"[kg_query]Prompt Tokens: {len_of_prompts}")

    response = await use_model_func(
        query,
        system_prompt=sys_prompt,
        stream=query_param.stream,
    )
    if isinstance(response, str) and len(response) > len(sys_prompt):
        response = (
            response.replace(sys_prompt, "")
            .replace("user", "")
            .replace("model", "")
            .replace(query, "")
            .replace("<system>", "")
            .replace("</system>", "")
            .strip()
        )

    return response


async def get_keywords_from_query(
    query: str,
    query_param: QueryParam,
    tokenizer: Tokenizer,
    llm_model_func: callable,
    addon_params: dict,
) -> tuple[list[str], list[str]]:
    """
    Retrieves high-level and low-level keywords for RAG operations.

    This function checks if keywords are already provided in query parameters,
    and if not, extracts them from the query text using LLM.

    Returns:
        A tuple containing (high_level_keywords, low_level_keywords)
    """
    # Check if pre-defined keywords are already provided
    if query_param.hl_keywords or query_param.ll_keywords:
        return query_param.hl_keywords, query_param.ll_keywords

    # Extract keywords using extract_keywords_only function which already supports conversation history
    hl_keywords, ll_keywords = await extract_keywords_only(query, query_param, tokenizer, llm_model_func, addon_params)
    return hl_keywords, ll_keywords


async def extract_keywords_only(
    text: str,
    param: QueryParam,
    tokenizer: Tokenizer,
    llm_model_func: callable,
    addon_params: dict,
) -> tuple[list[str], list[str]]:
    """
    Extract high-level and low-level keywords from the given 'text' using the LLM.
    This method does NOT build the final RAG context or provide a final answer.
    It ONLY extracts keywords (hl_keywords, ll_keywords).
    """
    # 2. Build the examples
    example_number = addon_params.get("example_number", None)
    if example_number and example_number < len(PROMPTS["keywords_extraction_examples"]):
        examples = "\n".join(PROMPTS["keywords_extraction_examples"][: int(example_number)])
    else:
        examples = "\n".join(PROMPTS["keywords_extraction_examples"])
    language = addon_params.get("language", PROMPTS["DEFAULT_LANGUAGE"])

    # 3. Process conversation history
    history_context = ""
    if param.conversation_history:
        history_context = get_conversation_turns(param.conversation_history, param.history_turns)

    # 4. Build the keyword-extraction prompt
    kw_prompt = PROMPTS["keywords_extraction"].format(
        query=text, examples=examples, language=language, history=history_context
    )

    len_of_prompts = len(tokenizer.encode(kw_prompt))
    logger.debug(f"[kg_query]Prompt Tokens: {len_of_prompts}")

    # 5. Call the LLM for keyword extraction
    if param.model_func:
        use_model_func = param.model_func
    else:
        use_model_func = llm_model_func

    result = await use_model_func(kw_prompt, keyword_extraction=True)

    # 6. Parse out JSON from the LLM response
    match = re.search(r"\{.*\}", result, re.DOTALL)
    if not match:
        logger.error("No JSON-like structure found in the LLM respond.")
        return [], []
    try:
        keywords_data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return [], []

    hl_keywords = keywords_data.get("high_level_keywords", [])
    ll_keywords = keywords_data.get("low_level_keywords", [])

    return hl_keywords, ll_keywords


async def _get_vector_context(
    query: str,
    chunks_vdb: BaseVectorStorage,
    query_param: QueryParam,
    tokenizer: Tokenizer,
) -> tuple[list, list, list] | None:
    """
    Retrieve vector context from the vector database.

    This function performs vector search to find relevant text chunks for a query,
    formats them with file path and creation time information.

    Args:
        query: The query string to search for
        chunks_vdb: Vector database containing document chunks
        query_param: Query parameters including top_k and ids
        tokenizer: Tokenizer for counting tokens

    Returns:
        Tuple (empty_entities, empty_relations, text_units) for combine_contexts,
        compatible with _get_edge_data and _get_node_data format
    """
    try:
        results = await chunks_vdb.query(query, top_k=query_param.top_k, ids=query_param.ids)
        if not results:
            return [], [], []

        valid_chunks = []
        for result in results:
            if "content" in result:
                # Directly use content from chunks_vdb.query result
                chunk_with_time = {
                    "content": result["content"],
                    "created_at": result.get("created_at", None),
                    "file_path": result.get("file_path", "unknown_source"),
                }
                valid_chunks.append(chunk_with_time)

        if not valid_chunks:
            return [], [], []

        maybe_trun_chunks = truncate_list_by_token_size(
            valid_chunks,
            key=lambda x: x["content"],
            max_token_size=query_param.max_token_for_text_unit,
            tokenizer=tokenizer,
        )

        logger.debug(
            f"Truncate chunks from {len(valid_chunks)} to {len(maybe_trun_chunks)} (max tokens:{query_param.max_token_for_text_unit})"
        )
        logger.info(f"Vector query: {len(maybe_trun_chunks)} chunks, top_k: {query_param.top_k}")

        if not maybe_trun_chunks:
            return [], [], []

        # Create empty entities and relations contexts
        entities_context = []
        relations_context = []

        # Create text_units_context directly as a list of dictionaries
        text_units_context = []
        for i, chunk in enumerate(maybe_trun_chunks):
            text_units_context.append(
                {
                    "id": i + 1,
                    "content": chunk["content"],
                    "file_path": chunk["file_path"],
                }
            )

        return entities_context, relations_context, text_units_context
    except Exception as e:
        logger.error(f"Error in _get_vector_context: {e}")
        return [], [], []


async def _build_query_context_from_keywords(
    ll_keywords: str,
    hl_keywords: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    tokenizer: Tokenizer,
    chunks_vdb: BaseVectorStorage = None,  # Add chunks_vdb parameter for mix mode
):
    logger.info(f"Process {os.getpid()} building query context...")

    # Handle local and global modes as before
    if query_param.mode == "local":
        entities_context, relations_context, text_units_context = await _get_node_data(
            ll_keywords,
            knowledge_graph_inst,
            entities_vdb,
            text_chunks_db,
            query_param,
            tokenizer,
        )
    elif query_param.mode == "global":
        entities_context, relations_context, text_units_context = await _get_edge_data(
            hl_keywords,
            knowledge_graph_inst,
            relationships_vdb,
            text_chunks_db,
            query_param,
            tokenizer,
        )
    else:  # hybrid or mix mode
        ll_data = await _get_node_data(
            ll_keywords,
            knowledge_graph_inst,
            entities_vdb,
            text_chunks_db,
            query_param,
            tokenizer,
        )
        hl_data = await _get_edge_data(
            hl_keywords,
            knowledge_graph_inst,
            relationships_vdb,
            text_chunks_db,
            query_param,
            tokenizer,
        )

        (
            ll_entities_context,
            ll_relations_context,
            ll_text_units_context,
        ) = ll_data

        (
            hl_entities_context,
            hl_relations_context,
            hl_text_units_context,
        ) = hl_data

        # Initialize vector data with empty lists
        vector_entities_context, vector_relations_context, vector_text_units_context = (
            [],
            [],
            [],
        )

        # Only get vector data if in mix mode
        if query_param.mode == "mix" and hasattr(query_param, "original_query"):
            # Get vector context in triple format
            vector_data = await _get_vector_context(
                query_param.original_query,  # We need to pass the original query
                chunks_vdb,
                query_param,
                tokenizer,
            )

            # If vector_data is not None, unpack it
            if vector_data is not None:
                (
                    vector_entities_context,
                    vector_relations_context,
                    vector_text_units_context,
                ) = vector_data

        # Combine and deduplicate the entities, relationships, and sources
        entities_context = process_combine_contexts(hl_entities_context, ll_entities_context, vector_entities_context)
        relations_context = process_combine_contexts(
            hl_relations_context, ll_relations_context, vector_relations_context
        )
        text_units_context = process_combine_contexts(
            hl_text_units_context, ll_text_units_context, vector_text_units_context
        )
    # not necessary to use LLM to generate a response
    if not entities_context and not relations_context:
        return None

    return entities_context, relations_context, text_units_context


async def _get_node_data(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    tokenizer: Tokenizer,
):
    # get similar entities
    logger.info(
        f"Query nodes: {query}, top_k: {query_param.top_k}, cosine: {entities_vdb.cosine_better_than_threshold}"
    )

    results = await entities_vdb.query(query, top_k=query_param.top_k, ids=query_param.ids)

    if not len(results):
        return "", "", ""

    # Extract all entity IDs from your results list
    node_ids = [r["entity_name"] for r in results]

    # Call the batch node retrieval and degree functions concurrently.
    nodes_dict, degrees_dict = await asyncio.gather(
        knowledge_graph_inst.get_nodes_batch(node_ids),
        knowledge_graph_inst.node_degrees_batch(node_ids),
    )

    # Now, if you need the node data and degree in order:
    node_datas = [nodes_dict.get(nid) for nid in node_ids]
    node_degrees = [degrees_dict.get(nid, 0) for nid in node_ids]

    if not all([n is not None for n in node_datas]):
        logger.warning("Some nodes are missing, maybe the storage is damaged")

    node_datas = [
        {
            **n,
            "entity_name": k["entity_name"],
            "rank": d,
            "created_at": k.get("created_at"),
        }
        for k, n, d in zip(results, node_datas, node_degrees)
        if n is not None
    ]  # what is this text_chunks_db doing.  dont remember it in airvx.  check the diagram.
    # get entitytext chunk
    use_text_units = await _find_most_related_text_unit_from_entities(
        node_datas,
        query_param,
        text_chunks_db,
        knowledge_graph_inst,
        tokenizer,
    )
    use_relations = await _find_most_related_edges_from_entities(
        node_datas,
        query_param,
        knowledge_graph_inst,
        tokenizer,
    )

    len_node_datas = len(node_datas)
    node_datas = truncate_list_by_token_size(
        node_datas,
        key=lambda x: x["description"] if x["description"] is not None else "",
        max_token_size=query_param.max_token_for_local_context,
        tokenizer=tokenizer,
    )
    logger.debug(
        f"Truncate entities from {len_node_datas} to {len(node_datas)} (max tokens:{query_param.max_token_for_local_context})"
    )

    logger.info(
        f"Local query uses {len(node_datas)} entites, {len(use_relations)} relations, {len(use_text_units)} chunks"
    )

    # build prompt
    entities_context = []
    for i, n in enumerate(node_datas):
        created_at = n.get("created_at", "UNKNOWN")
        if isinstance(created_at, (int, float)):
            created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))

        # Get file path from node data
        file_path = n.get("file_path", "unknown_source")

        entities_context.append(
            {
                "id": i + 1,
                "entity": n["entity_name"],
                "type": n.get("entity_type", "UNKNOWN"),
                "description": n.get("description", "UNKNOWN"),
                "rank": n["rank"],
                "created_at": created_at,
                "file_path": file_path,
            }
        )

    relations_context = []
    for i, e in enumerate(use_relations):
        created_at = e.get("created_at", "UNKNOWN")
        # Convert timestamp to readable format
        if isinstance(created_at, (int, float)):
            created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))

        # Get file path from edge data
        file_path = e.get("file_path", "unknown_source")

        relations_context.append(
            {
                "id": i + 1,
                "entity1": e["src_tgt"][0],
                "entity2": e["src_tgt"][1],
                "description": e["description"],
                "keywords": e["keywords"],
                "weight": e["weight"],
                "rank": e["rank"],
                "created_at": created_at,
                "file_path": file_path,
            }
        )

    text_units_context = []
    for i, t in enumerate(use_text_units):
        text_units_context.append(
            {
                "id": i + 1,
                "content": t["content"],
                "file_path": t.get("file_path", "unknown_source"),
            }
        )
    return entities_context, relations_context, text_units_context


async def _find_most_related_text_unit_from_entities(
    node_datas: list[dict],
    query_param: QueryParam,
    text_chunks_db: BaseKVStorage,
    knowledge_graph_inst: BaseGraphStorage,
    tokenizer: Tokenizer,
):
    text_units = [
        split_string_by_multi_markers(dp["source_id"], [GRAPH_FIELD_SEP])
        for dp in node_datas
        if dp["source_id"] is not None
    ]

    node_names = [dp["entity_name"] for dp in node_datas]
    batch_edges_dict = await knowledge_graph_inst.get_nodes_edges_batch(node_names)
    # Build the edges list in the same order as node_datas.
    edges = [batch_edges_dict.get(name, []) for name in node_names]

    all_one_hop_nodes = set()
    for this_edges in edges:
        if not this_edges:
            continue
        all_one_hop_nodes.update([e[1] for e in this_edges])

    all_one_hop_nodes = list(all_one_hop_nodes)

    # Batch retrieve one-hop node data using get_nodes_batch
    all_one_hop_nodes_data_dict = await knowledge_graph_inst.get_nodes_batch(all_one_hop_nodes)
    all_one_hop_nodes_data = [all_one_hop_nodes_data_dict.get(e) for e in all_one_hop_nodes]

    # Add null check for node data
    all_one_hop_text_units_lookup = {
        k: set(split_string_by_multi_markers(v["source_id"], [GRAPH_FIELD_SEP]))
        for k, v in zip(all_one_hop_nodes, all_one_hop_nodes_data)
        if v is not None and "source_id" in v  # Add source_id check
    }

    all_text_units_lookup = {}
    tasks = []

    for index, (this_text_units, this_edges) in enumerate(zip(text_units, edges)):
        for c_id in this_text_units:
            if c_id not in all_text_units_lookup:
                all_text_units_lookup[c_id] = index
                tasks.append((c_id, index, this_edges))

    # Process in batches tasks at a time to avoid overwhelming resources
    batch_size = 5
    results = []

    for i in range(0, len(tasks), batch_size):
        batch_tasks = tasks[i : i + batch_size]
        batch_results = await asyncio.gather(*[text_chunks_db.get_by_id(c_id) for c_id, _, _ in batch_tasks])
        results.extend(batch_results)

    for (c_id, index, this_edges), data in zip(tasks, results):
        all_text_units_lookup[c_id] = {
            "data": data,
            "order": index,
            "relation_counts": 0,
        }

        if this_edges:
            for e in this_edges:
                if e[1] in all_one_hop_text_units_lookup and c_id in all_one_hop_text_units_lookup[e[1]]:
                    all_text_units_lookup[c_id]["relation_counts"] += 1

    # Filter out None values and ensure data has content
    all_text_units = [
        {"id": k, **v}
        for k, v in all_text_units_lookup.items()
        if v is not None and v.get("data") is not None and "content" in v["data"]
    ]

    if not all_text_units:
        logger.warning("No valid text units found")
        return []

    all_text_units = sorted(all_text_units, key=lambda x: (x["order"], -x["relation_counts"]))
    all_text_units = truncate_list_by_token_size(
        all_text_units,
        key=lambda x: x["data"]["content"],
        max_token_size=query_param.max_token_for_text_unit,
        tokenizer=tokenizer,
    )

    logger.debug(
        f"Truncate chunks from {len(all_text_units_lookup)} to {len(all_text_units)} (max tokens:{query_param.max_token_for_text_unit})"
    )

    all_text_units = [t["data"] for t in all_text_units]
    return all_text_units


async def _find_most_related_edges_from_entities(
    node_datas: list[dict],
    query_param: QueryParam,
    knowledge_graph_inst: BaseGraphStorage,
    tokenizer: Tokenizer,
):
    node_names = [dp["entity_name"] for dp in node_datas]
    batch_edges_dict = await knowledge_graph_inst.get_nodes_edges_batch(node_names)

    all_edges = []
    seen = set()

    for node_name in node_names:
        this_edges = batch_edges_dict.get(node_name, [])
        for e in this_edges:
            sorted_edge = tuple(sorted(e))
            if sorted_edge not in seen:
                seen.add(sorted_edge)
                all_edges.append(sorted_edge)

    # Prepare edge pairs in two forms:
    # For the batch edge properties function, use dicts.
    edge_pairs_dicts = [{"src": e[0], "tgt": e[1]} for e in all_edges]
    # For edge degrees, use tuples.
    edge_pairs_tuples = list(all_edges)  # all_edges is already a list of tuples

    # Call the batched functions concurrently.
    edge_data_dict, edge_degrees_dict = await asyncio.gather(
        knowledge_graph_inst.get_edges_batch(edge_pairs_dicts),
        knowledge_graph_inst.edge_degrees_batch(edge_pairs_tuples),
    )

    # Reconstruct edge_datas list in the same order as the deduplicated results.
    all_edges_data = []
    for pair in all_edges:
        edge_props = edge_data_dict.get(pair)
        if edge_props is not None:
            if "weight" not in edge_props:
                logger.warning(f"Edge {pair} missing 'weight' attribute, using default value 0.0")
                edge_props["weight"] = 0.0

            combined = {
                "src_tgt": pair,
                "rank": edge_degrees_dict.get(pair, 0),
                **edge_props,
            }
            all_edges_data.append(combined)

    all_edges_data = sorted(all_edges_data, key=lambda x: (x["rank"], x["weight"]), reverse=True)
    all_edges_data = truncate_list_by_token_size(
        all_edges_data,
        key=lambda x: x["description"] if x["description"] is not None else "",
        max_token_size=query_param.max_token_for_global_context,
        tokenizer=tokenizer,
    )

    logger.debug(
        f"Truncate relations from {len(all_edges)} to {len(all_edges_data)} (max tokens:{query_param.max_token_for_global_context})"
    )

    return all_edges_data


async def _get_edge_data(
    keywords,
    knowledge_graph_inst: BaseGraphStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    tokenizer: Tokenizer,
):
    logger.info(
        f"Query edges: {keywords}, top_k: {query_param.top_k}, cosine: {relationships_vdb.cosine_better_than_threshold}"
    )

    results = await relationships_vdb.query(keywords, top_k=query_param.top_k, ids=query_param.ids)

    if not len(results):
        return "", "", ""

    # Prepare edge pairs in two forms:
    # For the batch edge properties function, use dicts.
    edge_pairs_dicts = [{"src": r["src_id"], "tgt": r["tgt_id"]} for r in results]
    # For edge degrees, use tuples.
    edge_pairs_tuples = [(r["src_id"], r["tgt_id"]) for r in results]

    # Call the batched functions concurrently.
    edge_data_dict, edge_degrees_dict = await asyncio.gather(
        knowledge_graph_inst.get_edges_batch(edge_pairs_dicts),
        knowledge_graph_inst.edge_degrees_batch(edge_pairs_tuples),
    )

    # Reconstruct edge_datas list in the same order as results.
    edge_datas = []
    for k in results:
        pair = (k["src_id"], k["tgt_id"])
        edge_props = edge_data_dict.get(pair)
        if edge_props is not None:
            if "weight" not in edge_props:
                logger.warning(f"Edge {pair} missing 'weight' attribute, using default value 0.0")
                edge_props["weight"] = 0.0

            # Use edge degree from the batch as rank.
            combined = {
                "src_id": k["src_id"],
                "tgt_id": k["tgt_id"],
                "rank": edge_degrees_dict.get(pair, k.get("rank", 0)),
                "created_at": k.get("created_at", None),
                **edge_props,
            }
            edge_datas.append(combined)

    edge_datas = sorted(edge_datas, key=lambda x: (x["rank"], x["weight"]), reverse=True)
    edge_datas = truncate_list_by_token_size(
        edge_datas,
        key=lambda x: x["description"] if x["description"] is not None else "",
        max_token_size=query_param.max_token_for_global_context,
        tokenizer=tokenizer,
    )
    use_entities, use_text_units = await asyncio.gather(
        _find_most_related_entities_from_relationships(
            edge_datas,
            query_param,
            knowledge_graph_inst,
            tokenizer,
        ),
        _find_related_text_unit_from_relationships(
            edge_datas,
            query_param,
            text_chunks_db,
            tokenizer,
        ),
    )
    logger.info(
        f"Global query uses {len(use_entities)} entites, {len(edge_datas)} relations, {len(use_text_units)} chunks"
    )

    relations_context = []
    for i, e in enumerate(edge_datas):
        created_at = e.get("created_at", "UNKNOWN")
        # Convert timestamp to readable format
        if isinstance(created_at, (int, float)):
            created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))

        # Get file path from edge data
        file_path = e.get("file_path", "unknown_source")

        relations_context.append(
            {
                "id": i + 1,
                "entity1": e["src_id"],
                "entity2": e["tgt_id"],
                "description": e["description"],
                "keywords": e["keywords"],
                "weight": e["weight"],
                "rank": e["rank"],
                "created_at": created_at,
                "file_path": file_path,
            }
        )

    entities_context = []
    for i, n in enumerate(use_entities):
        created_at = n.get("created_at", "UNKNOWN")
        # Convert timestamp to readable format
        if isinstance(created_at, (int, float)):
            created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))

        # Get file path from node data
        file_path = n.get("file_path", "unknown_source")

        entities_context.append(
            {
                "id": i + 1,
                "entity": n["entity_name"],
                "type": n.get("entity_type", "UNKNOWN"),
                "description": n.get("description", "UNKNOWN"),
                "rank": n["rank"],
                "created_at": created_at,
                "file_path": file_path,
            }
        )

    text_units_context = []
    for i, t in enumerate(use_text_units):
        text_units_context.append(
            {
                "id": i + 1,
                "content": t["content"],
                "file_path": t.get("file_path", "unknown"),
            }
        )
    return entities_context, relations_context, text_units_context


async def _find_most_related_entities_from_relationships(
    edge_datas: list[dict],
    query_param: QueryParam,
    knowledge_graph_inst: BaseGraphStorage,
    tokenizer: Tokenizer,
):
    entity_names = []
    seen = set()

    for e in edge_datas:
        if e["src_id"] not in seen:
            entity_names.append(e["src_id"])
            seen.add(e["src_id"])
        if e["tgt_id"] not in seen:
            entity_names.append(e["tgt_id"])
            seen.add(e["tgt_id"])

    # Batch approach: Retrieve nodes and their degrees concurrently with one query each.
    nodes_dict, degrees_dict = await asyncio.gather(
        knowledge_graph_inst.get_nodes_batch(entity_names),
        knowledge_graph_inst.node_degrees_batch(entity_names),
    )

    # Rebuild the list in the same order as entity_names
    node_datas = []
    for entity_name in entity_names:
        node = nodes_dict.get(entity_name)
        degree = degrees_dict.get(entity_name, 0)
        if node is None:
            logger.warning(f"Node '{entity_name}' not found in batch retrieval.")
            continue
        # Combine the node data with the entity name and computed degree (as rank)
        combined = {**node, "entity_name": entity_name, "rank": degree}
        node_datas.append(combined)

    len_node_datas = len(node_datas)
    node_datas = truncate_list_by_token_size(
        node_datas,
        key=lambda x: x["description"] if x["description"] is not None else "",
        max_token_size=query_param.max_token_for_local_context,
        tokenizer=tokenizer,
    )
    logger.debug(
        f"Truncate entities from {len_node_datas} to {len(node_datas)} (max tokens:{query_param.max_token_for_local_context})"
    )

    return node_datas


async def _find_related_text_unit_from_relationships(
    edge_datas: list[dict],
    query_param: QueryParam,
    text_chunks_db: BaseKVStorage,
    tokenizer: Tokenizer,
):
    text_units = [
        split_string_by_multi_markers(dp["source_id"], [GRAPH_FIELD_SEP])
        for dp in edge_datas
        if dp["source_id"] is not None
    ]
    all_text_units_lookup = {}

    async def fetch_chunk_data(c_id, index):
        if c_id not in all_text_units_lookup:
            chunk_data = await text_chunks_db.get_by_id(c_id)
            # Only store valid data
            if chunk_data is not None and "content" in chunk_data:
                all_text_units_lookup[c_id] = {
                    "data": chunk_data,
                    "order": index,
                }

    tasks = []
    for index, unit_list in enumerate(text_units):
        for c_id in unit_list:
            tasks.append(fetch_chunk_data(c_id, index))

    await asyncio.gather(*tasks)

    if not all_text_units_lookup:
        logger.warning("No valid text chunks found")
        return []

    all_text_units = [{"id": k, **v} for k, v in all_text_units_lookup.items()]
    all_text_units = sorted(all_text_units, key=lambda x: x["order"])

    # Ensure all text chunks have content
    valid_text_units = [t for t in all_text_units if t["data"] is not None and "content" in t["data"]]

    if not valid_text_units:
        logger.warning("No valid text chunks after filtering")
        return []

    truncated_text_units = truncate_list_by_token_size(
        valid_text_units,
        key=lambda x: x["data"]["content"],
        max_token_size=query_param.max_token_for_text_unit,
        tokenizer=tokenizer,
    )

    logger.debug(
        f"Truncate chunks from {len(valid_text_units)} to {len(truncated_text_units)} (max tokens:{query_param.max_token_for_text_unit})"
    )

    all_text_units: list[TextChunkSchema] = [t["data"] for t in truncated_text_units]

    return all_text_units


async def naive_query(
    query: str,
    chunks_vdb: BaseVectorStorage,
    query_param: QueryParam,
    llm_model_func,
    tokenizer,
    system_prompt: str | None = None,
) -> str | AsyncIterator[str]:
    if query_param.model_func:
        use_model_func = query_param.model_func
    else:
        use_model_func = llm_model_func

    _, _, text_units_context = await _get_vector_context(query, chunks_vdb, query_param, tokenizer)

    if text_units_context is None or len(text_units_context) == 0:
        return PROMPTS["fail_response"]

    text_units_str = json.dumps(text_units_context, ensure_ascii=False)
    if query_param.only_need_context:
        return f"""
---Document Chunks---

```json
{text_units_str}
```

"""
    # Process conversation history
    history_context = ""
    if query_param.conversation_history:
        history_context = get_conversation_turns(query_param.conversation_history, query_param.history_turns)

    # Build system prompt
    user_prompt = query_param.user_prompt if query_param.user_prompt else PROMPTS["DEFAULT_USER_PROMPT"]
    sys_prompt_temp = system_prompt if system_prompt else PROMPTS["naive_rag_response"]
    sys_prompt = sys_prompt_temp.format(
        content_data=text_units_str,
        response_type=query_param.response_type,
        history=history_context,
        user_prompt=user_prompt,
    )

    if query_param.only_need_prompt:
        return sys_prompt

    len_of_prompts = len(tokenizer.encode(query + sys_prompt))
    logger.debug(f"[naive_query]Prompt Tokens: {len_of_prompts}")

    response = await use_model_func(
        query,
        system_prompt=sys_prompt,
        stream=query_param.stream,
    )

    if isinstance(response, str) and len(response) > len(sys_prompt):
        response = (
            response[len(sys_prompt) :]
            .replace(sys_prompt, "")
            .replace("user", "")
            .replace("model", "")
            .replace(query, "")
            .replace("<system>", "")
            .replace("</system>", "")
            .strip()
        )

    return response


# ============= Merge Suggestions Functions =============


async def get_high_degree_nodes(
    graph_storage: BaseGraphStorage,
    max_analyze_nodes: int = 500,
    batch_size: int = 100,
    lightrag_logger=None,
) -> tuple[GraphNodeDataDict, int]:
    """
    Get high-degree nodes from the graph prioritized by connectivity.

    Args:
        graph_storage: Graph storage instance
        max_analyze_nodes: Maximum number of nodes to analyze (default: 500)
        batch_size: Batch size for processing (default: 100)
        lightrag_logger: Logger instance

    Returns:
        Tuple of (selected_nodes_dict, total_nodes_analyzed)

    Example:
        Input: Graph with 1000 nodes, max_analyze_nodes=300
        Output: (GraphNodeDataDict with 300 nodes, 1000)
    """
    # Get all node labels
    all_labels = await graph_storage.get_all_labels()
    if not all_labels:
        return GraphNodeDataDict(nodes_by_id={}), 0

    if lightrag_logger:
        lightrag_logger.debug(f"Found {len(all_labels)} total nodes in graph")

    # Process nodes in batches to get degrees
    high_degree_nodes = []
    all_degrees = {}

    for i in range(0, len(all_labels), batch_size):
        batch_labels = all_labels[i : i + batch_size]
        batch_degrees = await graph_storage.node_degrees_batch(batch_labels)

        # Collect all degrees for return
        all_degrees.update(batch_degrees)

        # Collect nodes with their degrees
        for label in batch_labels:
            degree = batch_degrees.get(label, 0)
            if degree > 0:  # Only consider connected nodes
                high_degree_nodes.append((label, degree))

    # Sort by degree and take top nodes
    high_degree_nodes.sort(key=lambda x: x[1], reverse=True)
    selected_labels = [label for label, _ in high_degree_nodes[:max_analyze_nodes]]

    # Get detailed node data for selected nodes (avoid redundant query in filter_and_group_entities)
    nodes_data_raw = {}
    if selected_labels:
        nodes_data_raw = await graph_storage.get_nodes_batch(selected_labels)

    # Convert raw dict data to GraphNodeData objects with degree information
    nodes_by_id = {}
    for label, raw_data in nodes_data_raw.items():
        # Ensure entity_id is set
        if "entity_id" not in raw_data:
            raw_data["entity_id"] = label

        # Add degree information to the node data
        raw_data["degree"] = all_degrees.get(label, 0)

        nodes_by_id[label] = GraphNodeData(**raw_data)

    if lightrag_logger:
        lightrag_logger.debug(f"Selected {len(selected_labels)} high-degree nodes and retrieved their data")

    return GraphNodeDataDict(nodes_by_id=nodes_by_id), len(all_labels)


async def filter_and_group_entities(
    selected_nodes_dict: GraphNodeDataDict,
    entity_types: list[str] | None = None,
) -> dict[str, list[GraphNodeData]]:
    """
    Filter nodes by entity types and group them by type.

    Args:
        selected_nodes_dict: Dictionary of selected nodes with their data
        entity_types: Optional filter for specific entity types

    Returns:
        Dictionary mapping entity types to lists of GraphNodeData objects

    Example:
        Input: selected_nodes_dict=GraphNodeDataDict(...), entity_types=['PERSON']
        Output: {'PERSON': [GraphNodeData(entity_id='entity1', ...)]}
    """
    # Filter by entity types if specified
    filtered_nodes = {}
    for label, node_data in selected_nodes_dict.nodes_by_id.items():
        if entity_types:
            entity_type = node_data.entity_type or ""
            if entity_type not in entity_types:
                continue
        filtered_nodes[label] = node_data

    if not filtered_nodes:
        return {}

    # Group entities by type
    from collections import defaultdict

    entities_by_type = defaultdict(list)
    for label, node_data in filtered_nodes.items():
        entity_type = node_data.entity_type or "UNKNOWN"
        filtered_node_data = GraphNodeData(
            entity_id=label,
            entity_name=node_data.entity_name or label,
            entity_type=entity_type,
            description=node_data.description or "",
            degree=node_data.degree,
            source_id=node_data.source_id,
            file_path=node_data.file_path,
            created_at=node_data.created_at,
        )
        entities_by_type[entity_type].append(filtered_node_data)

    return dict(entities_by_type)


async def analyze_entities_with_llm(
    entities_by_type: dict[str, list[GraphNodeData]],
    llm_model_func: callable,
    confidence_threshold: float = 0.6,
    batch_size: int = 50,
    max_suggestions: int = 10,  # Add max_suggestions parameter for early exit
    max_concurrent_llm_calls: int = 4,  # Add concurrent LLM calls limit
    tokenizer=None,
    llm_model_max_token_size: int = 32768,
    summary_to_max_tokens: int = 200,
    lightrag_logger=None,
) -> list[MergeSuggestion]:
    """
    Analyze entities using LLM to identify merge candidates with concurrent processing and early exit optimization.

    Args:
        entities_by_type: Dictionary mapping entity types to GraphNodeData lists
        llm_model_func: LLM function for analysis
        confidence_threshold: Minimum confidence score to accept suggestions (default: 0.6)
        batch_size: Batch size for LLM processing (default: 50)
        max_suggestions: Maximum suggestions to return - enables early exit (default: 10)
        max_concurrent_llm_calls: Maximum concurrent LLM calls (default: 4)
        tokenizer: Tokenizer for description handling
        llm_model_max_token_size: Max token size for LLM
        summary_to_max_tokens: Max tokens for summaries
        lightrag_logger: Logger instance

    Returns:
        List of MergeSuggestion objects (up to max_suggestions)

    Example:
        Input: entities_by_type={'PERSON': [GraphNodeData('Alice Smith'), GraphNodeData('A. Smith')]}
        Output: [MergeSuggestion(entities=[...], confidence_score=0.85, ...)]
    """
    suggestions = []

    if not llm_model_func:
        if lightrag_logger:
            lightrag_logger.warning("No LLM function provided, skipping LLM analysis")
        return suggestions

    # Track processed entities for debugging
    total_entities_processed = 0
    total_batches_prepared = 0

    # For early exit tracking
    seen_entities = set()

    # Prepare all batches for concurrent processing
    batch_tasks_data = []

    # Process each entity type and create batch task data
    for entity_type, entities_list in entities_by_type.items():
        if len(entities_list) < 2:
            if lightrag_logger:
                lightrag_logger.debug(f"Skipping {entity_type}: only {len(entities_list)} entities")
            continue  # Skip types with only one entity

        if lightrag_logger:
            lightrag_logger.debug(f"Preparing {entity_type}: {len(entities_list)} entities in batches of {batch_size}")

        # Create batch tasks for this entity type
        for i in range(0, len(entities_list), batch_size):
            batch_entities = entities_list[i : i + batch_size]
            total_batches_prepared += 1
            total_entities_processed += len(batch_entities)

            batch_tasks_data.append(
                {
                    "batch_id": total_batches_prepared,
                    "entity_type": entity_type,
                    "entities": batch_entities,
                    "batch_size": len(batch_entities),
                }
            )

    if not batch_tasks_data:
        if lightrag_logger:
            lightrag_logger.info("No valid batches to process")
        return suggestions

    if lightrag_logger:
        lightrag_logger.info(
            f"Starting concurrent LLM analysis: {total_batches_prepared} batches, "
            f"{total_entities_processed} entities, max_concurrent={max_concurrent_llm_calls}"
        )

    # Create semaphore for controlling concurrency and lock for protecting shared state
    semaphore = asyncio.Semaphore(max_concurrent_llm_calls)
    shared_state_lock = asyncio.Lock()  # Lock to protect shared variables
    successful_batches = 0
    processed_batches = 0

    async def _process_batch_with_semaphore(batch_data):
        """Process a single batch with semaphore control"""
        nonlocal suggestions, seen_entities, successful_batches, processed_batches

        async with semaphore:
            batch_id = batch_data["batch_id"]
            entity_type = batch_data["entity_type"]
            batch_entities = batch_data["entities"]

            if lightrag_logger:
                lightrag_logger.debug(f"Processing batch {batch_id} for {entity_type}: {len(batch_entities)} entities")

            try:
                batch_suggestions = await _batch_analyze_entities_with_llm(
                    batch_entities,
                    llm_model_func,
                    confidence_threshold,
                    tokenizer,
                    llm_model_max_token_size,
                    summary_to_max_tokens,
                    lightrag_logger,
                )

                # Protect shared state modifications with lock
                async with shared_state_lock:
                    processed_batches += 1

                    if batch_suggestions:
                        # Apply immediate filtering and deduplication
                        filtered_batch_suggestions = []
                        for suggestion in batch_suggestions:
                            entity_ids = {entity.entity_id for entity in suggestion.entities}
                            # Check for overlap with already seen entities
                            if not (entity_ids & seen_entities):
                                filtered_batch_suggestions.append(suggestion)
                                seen_entities.update(entity_ids)

                        successful_batches += 1

                        if lightrag_logger:
                            lightrag_logger.debug(
                                f"Batch {batch_id} produced {len(batch_suggestions)} raw suggestions, "
                                f"{len(filtered_batch_suggestions)} after filtering"
                            )

                        return filtered_batch_suggestions
                    else:
                        if lightrag_logger:
                            lightrag_logger.debug(f"Batch {batch_id} produced no suggestions")
                        return []

            except Exception as e:
                # Protect shared state modifications with lock
                async with shared_state_lock:
                    processed_batches += 1
                if lightrag_logger:
                    lightrag_logger.warning(f"Batch LLM analysis failed for {entity_type} batch {batch_id}: {e}")
                return []

    # Create tasks for all batches
    tasks = []
    for batch_data in batch_tasks_data:
        task = asyncio.create_task(_process_batch_with_semaphore(batch_data))
        tasks.append(task)

    # Wait for tasks to complete or for the first exception
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    # Check if any task raised an exception
    for task in done:
        if task.exception():
            # Cancel all pending tasks
            for pending_task in pending:
                pending_task.cancel()

            # Wait for cancellation to complete
            if pending:
                await asyncio.wait(pending)

            # Re-raise the exception
            raise task.exception()

    # Collect results from all completed tasks
    for task in done:
        task_suggestions = task.result()
        if task_suggestions:
            suggestions.extend(task_suggestions)
            # Early exit check
            if len(suggestions) >= max_suggestions:
                if lightrag_logger:
                    lightrag_logger.info(
                        f"Early exit: reached max_suggestions ({max_suggestions}) during concurrent processing"
                    )
                # Cancel remaining tasks if we have enough suggestions
                for pending_task in pending:
                    pending_task.cancel()
                if pending:
                    await asyncio.wait(pending)
                break

    # Wait for any remaining tasks if we haven't hit the limit
    if len(suggestions) < max_suggestions and pending:
        remaining_done, _ = await asyncio.wait(pending)
        for task in remaining_done:
            if not task.cancelled():
                task_suggestions = task.result()
                if task_suggestions:
                    suggestions.extend(task_suggestions)
                    # Early exit check
                    if len(suggestions) >= max_suggestions:
                        break

    # Sort by confidence before returning (only sort what we have)
    suggestions.sort(key=lambda x: x.confidence_score, reverse=True)

    # Trim to max_suggestions if needed
    if len(suggestions) > max_suggestions:
        suggestions = suggestions[:max_suggestions]

    # Final logging with comprehensive stats
    if lightrag_logger:
        lightrag_logger.info(
            f"Concurrent LLM analysis completed: {len(suggestions)} suggestions found. "
            f"Processed {processed_batches}/{total_batches_prepared} batches concurrently "
            f"({successful_batches} successful). Confidence threshold: {confidence_threshold}, "
            f"Max concurrent: {max_concurrent_llm_calls}"
        )

        if suggestions:
            confidence_scores = [s.confidence_score for s in suggestions]
            lightrag_logger.debug(
                f"Suggestion confidence range: {min(confidence_scores):.2f} - {max(confidence_scores):.2f}"
            )
        else:
            lightrag_logger.warning(
                f"No suggestions found! This may indicate: "
                f"1) Confidence threshold ({confidence_threshold}) too high, "
                f"2) LLM parsing issues, or "
                f"3) No actual merge candidates exist"
            )

    return suggestions


async def _batch_analyze_entities_with_llm(
    entities_list: list[GraphNodeData],
    llm_model_func: callable,
    confidence_threshold: float,
    tokenizer,
    llm_model_max_token_size: int,
    summary_to_max_tokens: int,
    lightrag_logger,
) -> list[MergeSuggestion]:
    """
    Analyze a batch of entities using LLM to identify merge candidates.

    Args:
        entities_list: List of GraphNodeData objects to analyze
        llm_model_func: LLM function for analysis
        confidence_threshold: Minimum confidence score for suggestions
        tokenizer: Tokenizer for handling description length
        llm_model_max_token_size: Max token size for LLM
        summary_to_max_tokens: Max tokens for description summaries
        lightrag_logger: Logger instance

    Returns:
        List of MergeSuggestion objects

    Example:
        Input: entities_list=[GraphNodeData('Apple Inc'), GraphNodeData('Apple Company')]
        Output: [MergeSuggestion(confidence_score=0.9, merge_reason='Same organization')]
    """
    try:
        # Prepare entities list for prompt with description handling
        entities_text = ""
        for i, entity in enumerate(entities_list):
            # Skip description summarization to save LLM calls and time
            # Previously we would summarize long descriptions using _handle_entity_relation_summary
            # Now we use the original description as-is
            description = entity.description or ""

            entities_text += f"Entity {i + 1}:\n"
            entities_text += f"- Name: {entity.entity_name or entity.entity_id}\n"
            entities_text += f"- Type: {entity.entity_type or 'UNKNOWN'}\n"
            entities_text += f"- Description: {description}\n"
            entities_text += f"- Degree: {entity.degree or 0}\n\n"

        # Use prompt from prompts.py
        from .prompt import PROMPTS

        prompt = PROMPTS["batch_merge_analysis"].format(
            entities_list=entities_text,
            tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
            record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
            completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
            graph_field_sep=GRAPH_FIELD_SEP,
        )

        if lightrag_logger:
            lightrag_logger.debug(f"Sending {len(entities_list)} entities to LLM for merge analysis")

        # Call LLM
        response = await llm_model_func(
            prompt,
            system_prompt="You are a knowledge graph expert specialized in identifying entities that should be merged. Analyze the provided entities and identify groups that refer to the same real-world objects.",
            stream=False,
            temperature=0.1,
        )

        if lightrag_logger:
            lightrag_logger.debug(f"Received LLM response of length {len(response)} characters")

        # Parse LLM response
        suggestions = parse_llm_merge_response(response, entities_list, confidence_threshold, lightrag_logger)
        return suggestions

    except Exception as e:
        if lightrag_logger:
            lightrag_logger.warning(f"Batch LLM analysis failed: {e}")
        return []


def parse_llm_merge_response(
    llm_response: str, entities_list: list[GraphNodeData], confidence_threshold: float, lightrag_logger
) -> list[MergeSuggestion]:
    """
    Parse LLM response to extract merge suggestions.

    Args:
        llm_response: Raw LLM response text
        entities_list: Original list of GraphNodeData entities analyzed
        confidence_threshold: Minimum confidence score for suggestions
        lightrag_logger: Logger instance

    Returns:
        List of MergeSuggestion objects

    Example:
        Input: llm_response='("merge_group"<|>Apple Inc,Apple Company<|>0.9<|>Same organization<|>...)'
        Output: [MergeSuggestion(entities=[...], confidence_score=0.9, ...)]
    """
    suggestions = []

    try:
        # Create entity lookup for quick access
        entity_lookup = {(entity.entity_name or entity.entity_id): entity for entity in entities_list}

        # Split by record delimiter
        from .prompt import PROMPTS

        records = llm_response.split(PROMPTS["DEFAULT_RECORD_DELIMITER"])

        if lightrag_logger:
            lightrag_logger.debug(f"Parsing LLM response: found {len(records)} potential records")

        parsed_count = 0
        filtered_count = 0

        for i, record in enumerate(records):
            record = record.strip()
            if not record or PROMPTS["DEFAULT_COMPLETION_DELIMITER"] in record:
                continue

            suggestion = parse_single_merge_record(record, entity_lookup, confidence_threshold, lightrag_logger)
            if suggestion:
                suggestions.append(suggestion)
                parsed_count += 1
            else:
                filtered_count += 1

        if lightrag_logger:
            lightrag_logger.debug(
                f"Parsed {parsed_count} valid suggestions, filtered out {filtered_count} invalid/low-confidence records"
            )

    except Exception as e:
        if lightrag_logger:
            lightrag_logger.warning(f"Failed to parse merge suggestions: {e}")

    return suggestions


def parse_single_merge_record(
    record: str, entity_lookup: dict[str, GraphNodeData], confidence_threshold: float, lightrag_logger=None
) -> MergeSuggestion | None:
    """
    Parse a single merge record from LLM response.

    Expected format:
    ("merge_group"<|>Entity A<SEP>Entity B<|>0.85<|>reason<|>target_name<|>target_type)

    Args:
        record: Raw record string from LLM
        entity_lookup: Dict mapping entity names to GraphNodeData
        confidence_threshold: Minimum confidence score to accept
        lightrag_logger: Logger for debugging

    Returns:
        MergeSuggestion if successfully parsed and meets threshold, None otherwise
    """
    try:
        # Import required constants and types
        from .prompt import GRAPH_FIELD_SEP, PROMPTS
        from .types import GraphNodeData

        # Extract content between quotes and parentheses
        content = record.split('("merge_group"')[1].strip()
        if content.endswith(")"):
            content = content[:-1]

        # Parse the content using tuple delimiter
        parts = content.split(PROMPTS["DEFAULT_TUPLE_DELIMITER"])

        # Filter out empty parts (especially the first one if content starts with delimiter)
        parts = [part.strip() for part in parts if part.strip()]

        if len(parts) != 5:  # Now expecting 5 parts instead of 6
            if lightrag_logger:
                lightrag_logger.warning(f"Record has {len(parts)} parts, expected 5. Parts: {parts}")
                lightrag_logger.debug(f"Raw record: {record[:200]}...")
            return None

        # Extract entity names from GRAPH_FIELD_SEP-separated list
        entity_names_str = parts[0].strip()
        entity_names = []
        seen_names = set()  # Prevent duplicate entity names in the same suggestion

        for name in entity_names_str.split(GRAPH_FIELD_SEP):
            name = name.strip()
            if name and name in entity_lookup:
                # Only add if we haven't seen this entity name before
                if name not in seen_names:
                    entity_names.append(name)
                    seen_names.add(name)
                elif lightrag_logger:
                    lightrag_logger.debug(f"Skipping duplicate entity name '{name}' in merge suggestion")
            elif name and lightrag_logger:
                lightrag_logger.debug(f"Entity '{name}' not found in lookup")

        if len(entity_names) < 2:
            if lightrag_logger:
                lightrag_logger.debug(f"Not enough unique valid entities found: {entity_names}")
            return None

        # Parse confidence score
        try:
            confidence_score = float(parts[1].strip())
        except ValueError:
            if lightrag_logger:
                lightrag_logger.warning(f"Invalid confidence score: {parts[1]}")
            return None

        # Check confidence threshold
        if confidence_score < confidence_threshold:
            if lightrag_logger:
                lightrag_logger.debug(f"Confidence {confidence_score} below threshold {confidence_threshold}")
            return None

        # Extract other fields (no longer processing description)
        merge_reason = parts[2].strip()
        suggested_name = parts[3].strip()
        suggested_type = parts[4].strip()

        # Build entities list
        entities = [entity_lookup[name] for name in entity_names]

        if lightrag_logger:
            lightrag_logger.debug(
                f"Successfully parsed suggestion: {entity_names} -> {suggested_name} (confidence: {confidence_score})"
            )

        # Create suggested target entity as GraphNodeData object (without description)
        suggested_target_entity = GraphNodeData(
            entity_id=suggested_name,  # Use suggested name as entity_id
            entity_name=suggested_name,
            entity_type=suggested_type,
        )

        return MergeSuggestion(
            entities=entities,
            confidence_score=confidence_score,
            merge_reason=merge_reason,
            suggested_target_entity=suggested_target_entity,
        )

    except Exception as e:
        if lightrag_logger:
            lightrag_logger.warning(f"Failed to parse merge record: {e}")
            lightrag_logger.debug(f"Record content: {record}")
        return None


def filter_and_deduplicate_suggestions(
    suggestions: list[MergeSuggestion], max_suggestions: int
) -> list[MergeSuggestion]:
    """
    Filter and deduplicate merge suggestions.

    Args:
        suggestions: List of MergeSuggestion objects
        max_suggestions: Maximum number of suggestions to return

    Returns:
        Filtered and deduplicated list of suggestions
    """
    # Handle edge case where max_suggestions is 0
    if max_suggestions <= 0:
        return []

    # Sort by confidence score (highest first)
    suggestions.sort(key=lambda x: x.confidence_score, reverse=True)

    # Remove duplicates (same entity appearing in multiple suggestions)
    seen_entities = set()
    filtered_suggestions = []

    for suggestion in suggestions:
        entity_ids = {entity.entity_id for entity in suggestion.entities}
        if not (entity_ids & seen_entities):  # No overlap with seen entities
            filtered_suggestions.append(suggestion)
            seen_entities.update(entity_ids)
            if len(filtered_suggestions) >= max_suggestions:
                break

    return filtered_suggestions


def calculate_edit_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Edit distance as integer
    """
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]
