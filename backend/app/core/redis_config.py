"""
Redis Configuration for Task Queue
Handles connection to Redis for background job processing
"""
import os
from redis import Redis
from rq import Queue
import logging

logger = logging.getLogger(__name__)


def get_redis_connection():
    """
    Get Redis connection with fallback to local development
    
    Returns:
        Redis connection object
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    try:
        redis_conn = Redis.from_url(
            redis_url,
            decode_responses=False,  # Keep bytes for compatibility
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        # Test connection
        redis_conn.ping()
        logger.info(f"✅ Redis connected: {redis_url}")
        return redis_conn
        
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        logger.warning("Running without task queue - jobs will run synchronously")
        return None


def get_task_queue(name: str = "default"):
    """
    Get RQ task queue
    
    Args:
        name: Queue name (default, high_priority, low_priority)
        
    Returns:
        RQ Queue object or None if Redis unavailable
    """
    redis_conn = get_redis_connection()
    
    if redis_conn is None:
        return None
    
    try:
        queue = Queue(name, connection=redis_conn)
        logger.info(f"✅ Task queue '{name}' ready")
        return queue
    except Exception as e:
        logger.error(f"❌ Failed to create queue '{name}': {e}")
        return None


# Global queue instances
default_queue = get_task_queue("default")
high_priority_queue = get_task_queue("high_priority")
low_priority_queue = get_task_queue("low_priority")
