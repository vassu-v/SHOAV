from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from pydantic import ValidationError

from ..models import McpToolCallRequest


def create_mcp_router(*, mcp_transport: Any, tool_gateway: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/mcp")
    async def get_mcp_transport(request: Request):
        return await mcp_transport.handle_get_request(request)

    @router.post("/mcp")
    async def post_mcp_transport(request: Request):
        return await mcp_transport.handle_post_request(request)

    @router.delete("/mcp")
    async def delete_mcp_transport(request: Request):
        return await mcp_transport.handle_delete_request(request)

    @router.get("/mcp/tools")
    async def list_mcp_tools() -> list[dict[str, Any]]:
        return tool_gateway.list_tools()

    @router.post("/mcp/tools/call")
    async def call_mcp_tool(payload: Any = Body(...)) -> dict[str, Any]:
        # Validated here rather than by FastAPI so a malformed envelope (arguments not
        # an object, name missing) comes back as a readable isError result like every
        # other bad call, not an HTTP 422 with raw pydantic internals.
        try:
            request = McpToolCallRequest.model_validate(payload)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in err.get('loc', ())) or 'body'}: {err.get('msg', 'invalid')}"
                for err in exc.errors(include_url=False, include_context=False, include_input=False)
            )
            message = (
                f"Invalid tool call: {details}. Send a JSON object like "
                '{"name": "<tool>", "arguments": {...}} where arguments is an object.'
            )
            return {
                "content": [{"type": "text", "text": message}],
                "structuredContent": {"error": message},
                "isError": True,
            }
        return (await tool_gateway.call_tool(request)).model_dump(exclude_none=True, by_alias=True)

    return router
