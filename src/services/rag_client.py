# Файл: C:\desk_top\src\services\rag_client.py
import logging
import pinecone
from openai import AsyncOpenAI
from src.config import PINECONE_API_KEY, OPENAI_API_KEY

# Имя вашего индекса в Pinecone. 
# Убедитесь, что вы создали его в своей учетной записи Pinecone.
PINECONE_INDEX_NAME = "desk-top-agent"
# Размерность векторов для модели text-embedding-3-small
EMBEDDING_DIMENSION = 1536

class RAGClient:
    def __init__(self):
        if not PINECONE_API_KEY or not OPENAI_API_KEY:
            raise ValueError("Pinecone or OpenAI API key not found.")
        
        # Pinecone больше не использует environments, инициализация стала проще
        self.pinecone = pinecone.Pinecone(api_key=PINECONE_API_KEY)
        self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.index = None
        logging.info("RAGClient initialized.")

    async def _initialize_index(self):
        """Проверяет, существует ли индекс, и создает его, если нет."""
        if PINECONE_INDEX_NAME not in self.pinecone.list_indexes().names():
            logging.info(f"Creating Pinecone index '{PINECONE_INDEX_NAME}'...")
            self.pinecone.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine" # 'cosine' хорошо подходит для семантического сходства
            )
            logging.info("Index created successfully.")
        self.index = self.pinecone.Index(PINECONE_INDEX_NAME)

    async def get_embedding(self, text: str) -> list[float]:
        """Создает векторное представление (эмбеддинг) для текста."""
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logging.error(f"Failed to create embedding: {e}")
            return []

    async def save_summary(self, session_id: int, user_id: int, summary_text: str):
        """Сохраняет итоги сессии в RAG-базу."""
        if not self.index:
            await self._initialize_index()

        embedding = await self.get_embedding(summary_text)
        if not embedding:
            return

        vector_id = f"session-{session_id}"
        metadata = {
            "user_id": user_id,
            "summary": summary_text
        }
        
        self.index.upsert(vectors=[(vector_id, embedding, metadata)])
        logging.info(f"Summary for session {session_id} saved to RAG.")

    async def find_relevant_summaries(self, user_id: int, query_text: str, top_k: int = 3) -> list[str]:
        """Находит наиболее релевантные итоги прошлых сессий."""
        if not self.index:
            await self._initialize_index()
            
        query_embedding = await self.get_embedding(query_text)
        if not query_embedding:
            return []

        # Фильтруем результаты только для текущего пользователя
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            filter={"user_id": user_id},
            include_metadata=True
        )
        
        summaries = [match['metadata']['summary'] for match in results['matches']]
        logging.info(f"Found {len(summaries)} relevant summaries for user {user_id}.")
        return summaries