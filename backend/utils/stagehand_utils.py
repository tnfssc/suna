"""
Utility functions for Stagehand API operations.
"""
import asyncio
import json
from uuid import UUID

from daytona_sdk import AsyncSandbox
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.utils.logger import logger


async def ensure_browser(thread_id: UUID, db: AsyncSession) -> bool:
    """
    Ensure the Stagehand API server is running and healthy for a given thread.
    
    This function:
    1. Gets the sandbox for the thread
    2. Checks if Stagehand API is healthy
    3. If not healthy, attempts to restart it up to 3 times
    
    Args:
        thread_id: The UUID of the thread
        db: Database session
        
    Returns:
        bool: True if Stagehand API is healthy or successfully restarted, False otherwise
    """
    try:
        # Import here to avoid circular dependencies
        from core.sandbox.sandbox import get_or_start_sandbox
        from core.threads import Thread
        
        # Get thread from database
        result = await db.execute(
            select(Thread).where(col(Thread.thread_id) == thread_id)
        )
        thread = result.scalar_one_or_none()
        
        if not thread:
            logger.error(f"Thread {thread_id} not found")
            return False
        
        # Get or create sandbox for this thread
        if not thread.sandbox or not thread.sandbox.get("sandbox_id"):
            logger.error(f"No sandbox found for thread {thread_id}")
            return False
        
        sandbox_id = thread.sandbox["sandbox_id"]
        sandbox = await get_or_start_sandbox(sandbox_id)
        
        if not sandbox:
            logger.error(f"Failed to get sandbox {sandbox_id} for thread {thread_id}")
            return False
        
        # Check Stagehand API health
        curl_cmd = "curl -s -X GET 'http://localhost:8004/api' -H 'Content-Type: application/json'"
        
        logger.debug(f"Checking Stagehand API health for thread {thread_id} with: {curl_cmd}")

        response = await sandbox.process.exec(curl_cmd, timeout=10)
        if response.exit_code != 0:
            logger.warning(f"Stagehand API server health check failed for thread {thread_id} with exit code {response.exit_code}")
            # Retry restart up to 3 times
            for attempt in range(3):
                logger.info(f"Attempting to restart Stagehand API (attempt {attempt + 1}/3) for thread {thread_id}")
                restart_success = await _restart_stagehand_api(sandbox, thread_id)
                if restart_success:
                    return True
                if attempt < 2:  # Don't sleep after the last attempt
                    await asyncio.sleep(2)  # Wait 2 seconds between retries

            logger.error(f"Failed to restart Stagehand API after 3 attempts for thread {thread_id}")
            return False
        
        # If we reach here, exit_code was 0 (success)
        return True

    except Exception as e:
        logger.error(f"Error ensuring browser for thread {thread_id}: {e}")
        return False


async def _restart_stagehand_api(sandbox: AsyncSandbox, thread_id: UUID) -> bool:
    """
    Attempt to restart the Stagehand API server.
    
    Args:
        sandbox: The sandbox instance
        thread_id: The UUID of the thread (for logging)
        
    Returns:
        bool: True if restart successful, False otherwise
    """
    try:
        from core.utils.config import config
        
        # Pass API key securely as environment variable
        env_vars = {"GEMINI_API_KEY": config.GEMINI_API_KEY}
        
        response = await sandbox.process.exec(
            "curl -X POST 'http://localhost:8004/api/init' -H 'Content-Type: application/json' -d '{\"api_key\": \"'$GEMINI_API_KEY'\"}'",
            timeout=90,
            env=env_vars
        )
        
        if response.exit_code == 0:
            # Verify the restart was successful
            verify_cmd = "curl -s -X GET 'http://localhost:8004/api' -H 'Content-Type: application/json'"
            verify_response = await sandbox.process.exec(verify_cmd, timeout=10)
            
            if verify_response.exit_code == 0:
                try:
                    result = json.loads(verify_response.result)
                    if result.get("status") == "healthy":
                        logger.info(f"✅ Stagehand API server successfully restarted for thread {thread_id}")
                        return True
                except json.JSONDecodeError:
                    logger.warning(f"Stagehand API restart verification returned invalid JSON for thread {thread_id}")
                    return False
        
        logger.warning(f"Stagehand API server restart failed for thread {thread_id}: {response.result}")
        return False
        
    except Exception as e:
        logger.error(f"Error restarting Stagehand API for thread {thread_id}: {e}")
        return False
