"""
Redis Configuration for Task Queue
Handles connection to Redis for background job processing

Best Practices:
- Connection pooling for efficiency
- Let RQ manage socket_timeout automatically (needs 415+ seconds for BLPOP)
- TCP keepalive to prevent idle connection drops
- Retry on timeout for transient network issues
"""
import os
from redis import Redis, ConnectionPool
from rq import Queue
import logging

logger = logging.getLogger(__name__)


def get_redis_connection():
    """
    Get Redis connection with connection pooling for production reliability
    
    Connection pooling provides:
    - Reuse of connections (better performance)
    - Automatic connection management
    - Better handling of connection limits
    
    Returns:
        Redis connection object or None if connection fails
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    try:
        # Create connection pool (production best practice)
        pool = ConnectionPool.from_url(
            redis_url,
            decode_responses=False,  # Required by RQ
            socket_connect_timeout=10,
            socket_keepalive=True,  # Prevent idle timeouts
            socket_keepalive_options={},
            retry_on_timeout=True,
            health_check_interval=30,
            max_connections=50  # Limit pool size
            # socket_timeout is NOT set - RQ manages it automatically
            # RQ sets socket_timeout = dequeue_timeout + 10 (typically 415s)
            # This allows BLPOP to wait for jobs without timing out
        )
        
        # Create Redis connection from pool
        redis_conn = Redis(connection_pool=pool)
        
        # Test connection
        redis_conn.ping()
        logger.info(f"✅ Redis connected with connection pool: {redis_url}")
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
