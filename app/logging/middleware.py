"""
Request correlation middleware.

Binds a unique request_id into structlog's contextvars for the lifetime of
one request, and echoes it back as a response header. Once RAG/agent
requests fan out into multiple downstream calls (retriever, LLM, tools,
eval hooks), this request_id is what lets you grep one request's full
trace out of the logs.
"""
import uuid

import structlog
from fastapi import Request


async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
