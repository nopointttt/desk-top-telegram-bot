# Файл: C:\desk_top\src\services\rag_client.py
import logging
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
        # ... (этот метод без изменений)
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small", input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logging.error(f"Failed to create embedding: {e}")
            return []

    async def save_summary(self, session_id: int, user_id: int, summary_text: str):
        if not self.index:
            logging.error("Cannot save summary: Pinecone index is not initialized.")
            return

        embedding = await self.get_embedding(summary_text)
        if not embedding:
            return

        vector_id = f"session-{session_id}"
        metadata = {"user_id": user_id, "summary": summary_text}
        
        try:
            self.index.upsert(vectors=[(vector_id, embedding, metadata)])
            logging.info(f"Summary for session {session_id} saved to RAG.")
        except Exception as e:
            logging.error(f"Failed to upsert summary for session {session_id}: {e}")

    async def find_relevant_summaries(self, user_id: int, query_text: str, top_k: int = 3) -> list[str]:
        if not self.index:
            logging.error("Cannot find summaries: Pinecone index is not initialized.")
            return []
            
        query_embedding = await self.get_embedding(query_text)
        if not query_embedding:
            return []

        try:
            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                filter={"user_id": user_id},
                include_metadata=True
            )
            summaries = [match['metadata']['summary'] for match in results['matches']]
            logging.info(f"Found {len(summaries)} relevant summaries for user {user_id}.")
            return summaries
        except Exception as e:
            logging.error(f"Error querying Pinecone: {e}")
            return []