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

from abc import ABC
from typing import Any, List, Optional

from aperag.query.query import QueryWithEmbedding
from aperag.vectorstore.connector import VectorStoreConnectorAdaptor


class ContextManager(ABC):
    def __init__(self, collection_name, embedding_model, vectordb_type, vectordb_ctx):
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.vectordb_type = vectordb_type
        self.adaptor = VectorStoreConnectorAdaptor(vectordb_type, vectordb_ctx)

    def query(self, query, score_threshold=0.5, topk=3, vector=None, index_types=None, chat_id=None):
        """
        Query vectors with optional filtering by index types and chat_id

        Args:
            query: Query string
            score_threshold: Similarity threshold
            topk: Number of results to return
            vector: Pre-computed query vector (optional)
            index_types: List of index types to include (e.g., ["vector", "vision", "summary"])
                        If None, no filtering is applied
            chat_id: Chat ID to filter chat documents (optional)

        Returns:
            List of DocumentWithScore objects
        """
        if vector is None:
            vector = self.embedding_model.embed_query(query)

        # Create filter based on index_types and chat_id if provided
        filter_condition = self._create_combined_filter(index_types, chat_id)

        query_embedding = QueryWithEmbedding(query=query, top_k=topk, embedding=vector)
        results = self.adaptor.connector.search(
            query_embedding,
            collection_name=self.collection_name,
            query_vector=query_embedding.embedding,
            with_vectors=True,
            limit=query_embedding.top_k,
            consistency="majority",
            search_params={"hnsw_ef": 128, "exact": False},
            score_threshold=score_threshold,
            filter=filter_condition,
        )
        return results.results

    def _create_index_types_filter(self, index_types: List[str]) -> Optional[Any]:
        """
        Create a filter to include only specified index types

        Args:
            index_types: List of index types to include (e.g., ["vector", "vision", "summary"])

        Returns:
            Filter object specific to the vector database type, or None if not supported
        """
        if not index_types:
            return None

        if self.vectordb_type == "qdrant":
            from qdrant_client.models import FieldCondition, Filter, IsEmptyCondition, MatchAny, PayloadField

            return Filter(
                should=[
                    FieldCondition(key="indexer", match=MatchAny(any=index_types)),
                    # compitable with existing vectors don't have indexer field
                    IsEmptyCondition(
                        is_empty=PayloadField(key="indexer"),
                    ),
                ]
            )

        # Add support for other vector databases here
        # elif self.vectordb_type == "pinecone":
        #     return {"indexer": {"$in": indexer_values}}
        # elif self.vectordb_type == "weaviate":
        #     return {"where": {"operator": "Or", "operands": [...]}}

        return None

    def _create_combined_filter(
        self, index_types: Optional[List[str]] = None, chat_id: Optional[str] = None
    ) -> Optional[Any]:
        """
        Create a combined filter for index types and chat_id

        Args:
            index_types: List of index types to include (e.g., ["vector", "vision", "summary"])
            chat_id: Chat ID to filter chat documents

        Returns:
            Filter object specific to the vector database type, or None if no filters
        """
        if not index_types and not chat_id:
            return None

        if self.vectordb_type == "qdrant":
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                IsEmptyCondition,
                MatchAny,
                MatchValue,
                PayloadField,
            )

            conditions = []

            # Add index_types filter
            if index_types:
                index_types_condition = [
                    FieldCondition(key="indexer", match=MatchAny(any=index_types)),
                    # Compatible with existing vectors that don't have indexer field
                    IsEmptyCondition(is_empty=PayloadField(key="indexer")),
                ]
                conditions.extend(index_types_condition)

            # Add chat_id filter
            if chat_id:
                chat_id_condition = FieldCondition(key="chat_id", match=MatchValue(value=chat_id))
                if conditions:
                    # If we have index_types conditions, combine them with AND logic
                    return Filter(must=[chat_id_condition, Filter(should=conditions)])
                else:
                    # Only chat_id filter
                    return Filter(must=[chat_id_condition])

            # Only index_types filter
            return Filter(should=conditions)

        # Add support for other vector databases here
        return None
