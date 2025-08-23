# Файл: C:\desk_top\src\services\rag_client.py
import logging
import tiktoken
from pinecone import Pinecone, PodSpec
from openai import AsyncOpenAI
from src.config import PINECONE_API_KEY, OPENAI_API_KEY

PINECONE_INDEX_NAME = "desk-top-agent"
EMBEDDING_DIMENSION = 1536

class RAGClient:
    def __init__(self):
        if not PINECONE_API_KEY or not OPENAI_API_KEY:
            raise ValueError("Pinecone or OpenAI API key not found in .env file.")
        
        self.pinecone = Pinecone(api_key=PINECONE_API_KEY)
        self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.index = None
        logging.info("RAGClient instance created.")

        # Настройка токенайзера для оценки бюджета RAG
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4o")
        except Exception as e:
            logging.warning(f"Could not get encoding for gpt-4o in RAGClient, fallback to cl100k_base. Error: {e}")
            self.encoding = tiktoken.get_encoding("cl100k_base")

        # Бюджет токенов под RAG-контекст (соответствует ~60% от 100k из LLMClient)
        self.RAG_TOKEN_BUDGET = 60_000
        # Верхняя граница, сколько кандидатов запрашивать у Pinecone до обрезки по токенам
        self.MAX_CANDIDATES = 20
        self.MIN_TOP_K = 3

    def _count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def _trim_summaries_by_budget(self, summaries: list[str], budget_tokens: int) -> list[str]:
        if budget_tokens <= 0 or not summaries:
            return []
        selected = []
        used = 0
        sep_tokens = self._count_tokens("\n\n")
        for i, s in enumerate(summaries):
            t = self._count_tokens(s)
            add = t if i == 0 else t + sep_tokens
            if used + add > budget_tokens:
                break
            selected.append(s)
            used += add
        return selected

    async def initialize(self):
        """Проверяет, существует ли индекс, создает его, если нет, и подключается."""
        try:
            if PINECONE_INDEX_NAME not in self.pinecone.list_indexes().names():
                logging.warning(f"Index '{PINECONE_INDEX_NAME}' not found. Creating a new one...")
                self.pinecone.create_index(
                    name=PINECONE_INDEX_NAME,
                    dimension=EMBEDDING_DIMENSION,
                    metric="cosine",
                    spec=PodSpec(environment="gcp-starter") # Уточняем окружение для Starter-плана
                )
                logging.info("Index created successfully. Please wait a moment for it to initialize.")
            
            self.index = self.pinecone.Index(PINECONE_INDEX_NAME)
            logging.info(f"Successfully connected to Pinecone index '{PINECONE_INDEX_NAME}'.")
        except Exception as e:
            logging.error(f"Failed to initialize Pinecone index: {e}")
            # В случае ошибки self.index останется None

    async def get_embedding(self, text: str) -> list[float]:
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small", input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logging.error(f"Failed to create embedding: {e}")
            return []

    async def save_summary(self, session_id: int, user_id: int, summary_text: str, project_id: int | None = None):
        if not self.index:
            logging.error("Cannot save summary: Pinecone index is not initialized.")
            return

        embedding = await self.get_embedding(summary_text)
        if not embedding:
            return

        vector_id = f"session-{session_id}"
        metadata = {"user_id": user_id, "summary": summary_text}
        if project_id is not None:
            metadata["project_id"] = project_id
        
        try:
            self.index.upsert(vectors=[(vector_id, embedding, metadata)])
            logging.info(f"Summary for session {session_id} saved to RAG.")
        except Exception as e:
            logging.error(f"Failed to upsert summary for session {session_id}: {e}")

    async def find_relevant_summaries(
        self,
        user_id: int,
        query_text: str,
        top_k: int = 3,
        project_id: int | None = None,
        project_ids: list[int] | None = None,
    ) -> list[str]:
        if not self.index:
            logging.error("Cannot find summaries: Pinecone index is not initialized.")
            return []
            
        query_embedding = await self.get_embedding(query_text)
        if not query_embedding:
            return []

        try:
            flt = {"user_id": user_id}
            # Приоритет: явный список project_ids, затем одиночный project_id, иначе — глобально по user_id
            if project_ids is not None:
                if len(project_ids) == 0:
                    return []
                # Pinecone metadata filter: { field: {"$in": [...] } }
                flt["project_id"] = {"$in": project_ids}
            elif project_id is not None:
                flt["project_id"] = project_id
            # Динамический запрос: запрашиваем максимум кандидатов, затем обрезаем по бюджету
            effective_k = max(self.MIN_TOP_K, min(self.MAX_CANDIDATES, int(top_k) if isinstance(top_k, int) else self.MIN_TOP_K))
            results = self.index.query(
                vector=query_embedding,
                top_k=effective_k,
                filter=flt,
                include_metadata=True
            )
            matches = results.get('matches', []) if isinstance(results, dict) else getattr(results, 'matches', [])
            # Преобразуем в [(summary, score)] и отсортируем по score убыв.
            pairs = []
            for m in matches:
                md = m.get('metadata', {}) if isinstance(m, dict) else getattr(m, 'metadata', {})
                summary = md.get('summary') if isinstance(md, dict) else None
                score = m.get('score') if isinstance(m, dict) else getattr(m, 'score', 0)
                if summary:
                    pairs.append((summary, score))
            pairs.sort(key=lambda x: x[1], reverse=True)

            candidates = [s for s, _ in pairs]
            selected = self._trim_summaries_by_budget(candidates, self.RAG_TOKEN_BUDGET)

            # Метрики
            total_candidates = len(candidates)
            selected_tokens = self._count_tokens("\n\n".join(selected)) if selected else 0
            logging.info(
                f"RAG query user={user_id}, proj={project_id or project_ids}, "
                f"effective_k={effective_k}, candidates={total_candidates}, selected={len(selected)}, "
                f"selected_tokens={selected_tokens}/{self.RAG_TOKEN_BUDGET}"
            )

            return selected
        except Exception as e:
            logging.error(f"Error querying Pinecone: {e}")
            return []