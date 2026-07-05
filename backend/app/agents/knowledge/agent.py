"""
Knowledge Agent — RAG-based fitness and nutrition knowledge base.

Unlike the Memory Agent (which stores user-specific information),
the Knowledge Agent maintains the application's domain knowledge:
- Exercise science and biomechanics
- Nutrition and sports dietetics
- Swimming technique fundamentals
- Recovery and sleep science
- Injury prevention and management

Uses RAG to ground Coach Agent responses in evidence, reducing hallucinations.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.vectorstores import VectorStoreRetriever
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.agents.base import AgentState, BaseAgent
from app.services.llm.provider import get_embedding_model
from app.core.logging import get_logger

logger = get_logger("agent.knowledge")

KNOWLEDGE_DOMAINS = {
    "exercise": "Exercise science, biomechanics, muscle physiology, progressive overload",
    "nutrition": "Sports nutrition, macros, Indian vegetarian protein sources, nutrient timing",
    "swimming": "Swimming technique, freestyle mechanics, breathing, stroke progression",
    "recovery": "Sleep science, active recovery, deload protocols, injury management",
    "fat_loss": "Evidence-based fat loss strategies, body recomposition, metabolic adaptation",
    "hypertrophy": "Muscle hypertrophy research, volume landmarks, frequency optimization",
}


class KnowledgeAgent(BaseAgent):
    """
    Provides evidence-based domain knowledge via RAG.

    This agent runs early in the pipeline to ground Coach Agent responses
    in exercise science and nutrition research.
    """

    name = "knowledge_agent"
    description = "RAG over fitness/nutrition knowledge base to prevent hallucinations"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db
        self.embedding_model = get_embedding_model()

    @property
    def system_prompt(self) -> str:
        return (
            "You are a sports science expert. "
            "Provide evidence-based information from the knowledge base."
        )

    async def process(self, state: AgentState) -> AgentState:
        """Retrieve relevant knowledge to ground the coach's response."""
        self._append_trace(state, "Retrieving domain knowledge")

        query = state.get("user_message", "")
        relevant_knowledge = await self._retrieve_knowledge(query)

        # Inject knowledge into state for use by other agents
        if "permanent_memory" not in state:
            state["permanent_memory"] = {}
        state["permanent_memory"]["knowledge_context"] = relevant_knowledge

        self._append_trace(state, f"Retrieved {len(relevant_knowledge)} knowledge chunks")
        return state

    async def _retrieve_knowledge(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search the knowledge base using vector similarity."""
        if not query:
            return []

        query_embedding = self.embedding_model.embed_query(query)

        # Stringify vector — asyncpg cannot serialize list[float] as vector directly
        vec_str = f"[{','.join(str(v) for v in query_embedding)}]"

        sql = text(f"""
            SELECT content, chunk_metadata, source_type,
                   1 - (embedding <=> '{vec_str}'::vector) AS similarity
            FROM embeddings
            WHERE source_type = 'knowledge'
              AND 1 - (embedding <=> '{vec_str}'::vector) > 0.35
            ORDER BY embedding <=> '{vec_str}'::vector
            LIMIT :top_k
        """)

        result = await self.db.execute(sql, {"top_k": top_k})
        rows = result.fetchall()

        return [
            {
                "content": row.content,
                "metadata": row.chunk_metadata,
                "source": row.source_type,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    async def index_knowledge_document(
        self, content: str, domain: str, source: str
    ) -> int:
        """
        Index a knowledge document into the vector store.

        Called during initial setup and when new knowledge is added.
        Returns the number of chunks indexed.
        """
        from app.db.models.memory import Embedding

        chunks = self._chunk_text(content, chunk_size=500, overlap=50)
        indexed = 0

        for i, chunk in enumerate(chunks):
            embedding = self.embedding_model.embed_query(chunk)
            doc = Embedding(
                source_type="knowledge_base",
                content=chunk,
                embedding=embedding,
                embedding_model="text-embedding-3-small",
                chunk_index=i,
                chunk_metadata={"domain": domain, "source": source},
            )
            self.db.add(doc)
            indexed += 1

        await self.db.flush()
        logger.info("Knowledge indexed", domain=domain, chunks=indexed)
        return indexed

    def _chunk_text(
        self, text: str, chunk_size: int = 500, overlap: int = 50
    ) -> list[str]:
        """Split text into overlapping chunks for embedding."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i : i + chunk_size])
            chunks.append(chunk)
        return chunks
