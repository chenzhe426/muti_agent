from os import environ
from dotenv import load_dotenv

load_dotenv()

class Config:
    OPENAI_API_KEY: str = environ.get("OPENAI_API_KEY", "")
    DATA_PATH: str = "./customer_support_chat/data"
    LOG_LEVEL: str = environ.get("LOG_LEVEL", "DEBUG")
    SQLITE_DB_PATH: str = environ.get(
        "SQLITE_DB_PATH", "./customer_support_chat/data/travel2.sqlite"
    )
    METADATA_DB_PATH: str = environ.get(
        "METADATA_DB_PATH", "./customer_support_chat/data/metadata.sqlite"
    )
    QDRANT_URL: str = environ.get("QDRANT_URL", "http://localhost:6333")
    RECREATE_COLLECTIONS: bool = environ.get("RECREATE_COLLECTIONS", "False")
    LIMIT_ROWS: int = environ.get("LIMIT_ROWS", "100")

    # ==================== LLM 配置 ====================
    LLM_PROVIDER: str = environ.get("LLM_PROVIDER", "openai")
    LLM_BASE_URL: str = environ.get("LLM_BASE_URL", "http://localhost:8001/v1")
    LLM_MODEL: str = environ.get("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    OLLAMA_BASE_URL: str = environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    LLM_MAX_CONCURRENT: int = int(environ.get("LLM_MAX_CONCURRENT", "10"))

    # ==================== Redis 配置 ====================
    # 状态存储类型: "memory" | "redis"
    CHECKPOINTER_TYPE: str = environ.get("CHECKPOINTER_TYPE", "memory")

    # Redis 连接配置
    REDIS_URL: str = environ.get("REDIS_URL", "redis://localhost:6379")
    REDIS_MAX_CONNECTIONS: int = int(environ.get("REDIS_MAX_CONNECTIONS", "50"))
    REDIS_THREAD_COUNT: int = int(environ.get("REDIS_THREAD_COUNT", "10"))

def get_settings():
    return Config()