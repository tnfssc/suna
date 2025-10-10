"""
Utility functions for Stagehand API operations.
"""
import asyncio
import json
from uuid import UUID

from daytona_sdk import AsyncSandbox

from core.sandbox.sandbox import get_or_start_sandbox
from core.services.supabase import DBConnection
from core.utils.config import config
from core.utils.logger import logger


async def ensure_browser(thread_id: UUID) -> bool:
    """
    Ensure the browser (Stagehand API) is running and healthy for a given thread.

    This function checks if the Stagehand API server is accessible and attempts to
    restart it if needed. Can be used without creating BrowserTool instances.

    Args:
        thread_id: The thread ID to ensure browser for

    Returns:
        bool: True if browser is healthy/ready, False otherwise
    """
    try:
        # Get database client
        db = DBConnection()
        client = await db.client

        # Get thread data
        thread_result = await client.table('threads').select('*').eq('thread_id', str(thread_id)).execute()

        if not thread_result.data or len(thread_result.data) == 0:
            logger.warning(f"Thread {thread_id} not found")
            return False

        thread = thread_result.data[0]

        if not thread.get('sandbox'):
            logger.warning(f"No sandbox found for thread {thread_id}")
            return False

        sandbox_id = thread['sandbox'].get('id')

        if not sandbox_id:
            logger.warning(f"No sandbox ID found for thread {thread_id}")
            return False

        # Get or start the sandbox
        sandbox = await get_or_start_sandbox(sandbox_id)

        # Simple health check curl command
        curl_cmd = "curl -s -X GET 'http://localhost:8004/api' -H 'Content-Type: application/x-www-form-urlencoded'"

        logger.debug(f"Checking Stagehand API health for thread {thread_id} with: {curl_cmd}")

        response = await sandbox.process.exec(curl_cmd, timeout=10)
        if response.exit_code != 0:
            logger.warning(f"Stagehand API server health check failed for thread {thread_id} with exit code {response.exit_code}")
            # Try to restart the Stagehand API (with built-in retries)
            return await _restart_stagehand_api(sandbox, thread_id)
        
        # If we reach here, exit_code was 0 (success)
        return True

    except Exception as e:
        logger.error(f"Error checking Stagehand API health for thread {thread_id}: {e}")
        return False


async def _restart_stagehand_api(sandbox: AsyncSandbox, thread_id: UUID) -> bool:
    """
    Attempt to restart the Stagehand API server with retry logic.
    
    The browserApi init function can fail transiently due to browser startup issues,
    so we retry the init call multiple times.

    Args:
        sandbox: The sandbox instance
        thread_id: Thread ID for logging

    Returns:
        bool: True if restart was successful, False otherwise
    """
    openrouter_model_api_key = config.OPENROUTER_API_KEY
    openrouter_model_name = '@preset/action-ai-model-c'

    cmd = f"curl --request POST --url http://localhost:8004/api/init --header 'content-type: application/x-www-form-urlencoded' --data 'api_key={openrouter_model_api_key}' --data 'model_name={openrouter_model_name}'"
    
    # Retry the init call up to 3 times
    for attempt in range(3):
        try:
            logger.info(f"Attempting to initialize Stagehand API (attempt {attempt + 1}/3) for thread {thread_id}")
            response = await sandbox.process.exec(cmd, timeout=90)

            if response.exit_code == 0:
                logger.info(f"Stagehand API server initialized successfully for thread {thread_id}")
                return True
            else:
                logger.warning(f"Stagehand API init attempt {attempt + 1} failed for thread {thread_id}: {response.result}")
                
        except Exception as e:
            logger.warning(f"Error on init attempt {attempt + 1} for thread {thread_id}: {e}")
        
        # Wait before retrying (except after the last attempt)
        if attempt < 2:
            await asyncio.sleep(2)
    
    logger.error(f"Failed to initialize Stagehand API after 3 attempts for thread {thread_id}")
    return False
