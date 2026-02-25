from celery import Celery
from app.config import settings
import asyncio
from app.services.llm import chat_with_context

celery_app = Celery(
    "openzero_tasks",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Berlin",
    enable_utc=True,
)

@celery_app.task
def background_llm_task(user_message: str, include_projects: bool = False, include_people: bool = True):
    # Execute the async function in a synchronous celery task using asyncio.run
    return asyncio.run(chat_with_context(
        user_message=user_message,
        history=None,
        include_projects=include_projects,
        include_people=include_people
    ))
