import logging
from typing import Optional

from django.conf import settings
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        try:
            _client = MongoClient(
                settings.MONGODB_HOST,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=30000,
                maxPoolSize=50,
                minPoolSize=5,
            )
            _client.admin.command('ping')
            logger.info("MongoDB connected: %s / %s", settings.MONGODB_HOST, settings.MONGODB_DB)
        except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
            logger.error("MongoDB connection failed: %s", exc)
            raise
    return _client


def get_db() -> Database:
    return get_mongo_client()[settings.MONGODB_DB]


def get_collection(name: str) -> Collection:
    return get_db()[name]


def close_connection() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed.")


def documents_col() -> Collection:
    return get_collection(settings.MONGO_COLLECTIONS['DOCUMENTS'])

def chunks_col() -> Collection:
    return get_collection(settings.MONGO_COLLECTIONS['CHUNKS'])

def chat_sessions_col() -> Collection:
    return get_collection(settings.MONGO_COLLECTIONS['CHAT_SESSIONS'])

def messages_col() -> Collection:
    return get_collection(settings.MONGO_COLLECTIONS['MESSAGES'])

def analytics_col() -> Collection:
    return get_collection(settings.MONGO_COLLECTIONS['ANALYTICS'])

def otps_col() -> Collection:
    return get_collection(settings.MONGO_COLLECTIONS['OTPS'])

def feedback_col() -> Collection:
    return get_collection(settings.MONGO_COLLECTIONS['FEEDBACK'])


def create_indexes() -> None:
    """Create all MongoDB indexes. Safe to call repeatedly."""
    try:
        documents_col().create_index([('user_id', ASCENDING)])
        documents_col().create_index([('file_hash', ASCENDING)])
        documents_col().create_index([('created_at', DESCENDING)])

        chunks_col().create_index([('document_id', ASCENDING)])
        chunks_col().create_index([('user_id', ASCENDING)])

        chat_sessions_col().create_index([('user_id', ASCENDING)])
        chat_sessions_col().create_index([('created_at', DESCENDING)])
        chat_sessions_col().create_index([('title', 'text')])

        messages_col().create_index([('session_id', ASCENDING)])
        messages_col().create_index([('created_at', ASCENDING)])
        messages_col().create_index([('content', 'text')])

        # One verdict per message: rating again updates rather than stacking.
        feedback_col().create_index([('message_id', ASCENDING)], unique=True)
        feedback_col().create_index([('rating', ASCENDING), ('created_at', DESCENDING)])

        analytics_col().create_index([('user_id', ASCENDING)])
        analytics_col().create_index([('created_at', DESCENDING)])

        # One live code per email per flow, and let Mongo sweep away spent
        # records on its own so nothing has to run a cleanup job.
        otps_col().create_index([('email', ASCENDING), ('purpose', ASCENDING)], unique=True)
        otps_col().create_index([('purge_at', ASCENDING)], expireAfterSeconds=0)

        logger.info("MongoDB indexes created/verified.")
    except Exception as exc:
        logger.error("Failed to create MongoDB indexes: %s", exc)
        raise
