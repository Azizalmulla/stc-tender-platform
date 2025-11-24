"""
RQ Worker Process
Runs background jobs for tender processing

Usage:
    python worker.py

The worker will:
- Connect to Redis
- Listen for jobs on 'default' queue
- Process jobs with automatic retries
- Handle failures gracefully
"""
import sys
import logging
from rq import Worker, Queue, Connection
from app.core.redis_config import get_redis_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Start the RQ worker"""
    try:
        # Get Redis connection
        redis_conn = get_redis_connection()
        
        if redis_conn is None:
            logger.error("❌ Cannot start worker: Redis connection failed")
            logger.error("Make sure REDIS_URL environment variable is set")
            logger.error("Or start local Redis with: redis-server")
            sys.exit(1)
        
        # Create queues to listen on
        queues = [
            Queue('high_priority', connection=redis_conn),
            Queue('default', connection=redis_conn),
            Queue('low_priority', connection=redis_conn)
        ]
        
        logger.info("🚀 Starting RQ worker...")
        logger.info(f"📋 Listening on queues: {[q.name for q in queues]}")
        logger.info("Press Ctrl+C to stop")
        
        # Start worker
        with Connection(redis_conn):
            worker = Worker(queues)
            worker.work(with_scheduler=True)
            
    except KeyboardInterrupt:
        logger.info("\n👋 Worker stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Worker error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
