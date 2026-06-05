"""Isolated PoE chat — separate LLM context with PoE-only tools.

Full chat experience parallel to main NEXUS chat:
- Own tool registry (13 poe_* tools)
- Own conversation history (in-memory, per session)
- Own system prompt (poe_expert)
- Mode-aware: shares mode with main chat (auto/light/heavy/CLI bridges)
"""

import json
import logging
import re
from typing import AsyncIterator

from providers.base import Message, TaskType

logger = logging.getLogger(__name__)

_MAX_HISTORY = 40

# Detect PoB codes and paste URLs in user messages
_POB_CODE_RE = re.compile(r"[eE][NnJj][A-Za-z0-9+/=_-]{100,}")
_POB_URL_RE = re.compile(r"https?://(?:pobb\.in|pastebin\.com)/\S+")

_POE_SYSTEM_PROMPT = """You are an expert Path of Exile 1 build advisor and economy analyst.
You know PoE mechanics at a professional level: damage calculation, defense layers, atlas strategy, crafting, trading.

Rules:
- ALWAYS use tools for real data. Never guess prices or stats.
- When analyzing a build, check: elemental resists (cap 75%), chaos res (aim 0%+), life/ES pool, DPS, recovery.
- Flag specific weaknesses with actionable fixes and estimated cost.
- For starter recommendations: prioritize budget, HC viability, clear speed, boss capability.
- Currency values change — always fetch current rates before making cost estimates.
- Respond in the same language as the user (Russian if they write in Russian).
- Be concise and data-driven. No filler text.
- When using tools, briefly mention what you're checking (e.g. "checking prices...")."""

# Session state
_history: list[dict] = []

# Lazy-loaded tools
_tool_registry: dict | None = None
_tool_schemas: list | None = None


def _get_tools():
    """Build isolated tool registry (only PoE tools, loaded once)."""
    global _tool_registry, _tool_schemas
    if _tool_registry is not None:
        return _tool_registry, _tool_schemas

    from poe_intel.tools import get_tool_definitions

    defs = get_tool_definitions()
    _tool_registry = {}
    schemas = []
    for d in defs:
        _tool_registry[d["name"]] = d["func"]
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": d["name"],
                    "description": d["description"],
                    "parameters": d["parameters"],
                },
            }
        )
    _tool_schemas = schemas
    logger.info("PoE chat tools loaded: %d", len(_tool_registry))
    return _tool_registry, _tool_schemas


def _resolve_provider(router, mode: str):
    """Get provider + model based on current mode."""
    if mode == "light":
        route = router.select_provider(TaskType.CHAT, prefer_light=True)
    elif mode == "heavy":
        route = router.select_provider(TaskType.CHAT, prefer_light=False, max_tier=1)
    else:
        # auto or fallback
        route = router.select_provider(TaskType.CHAT)

    if route:
        return route
    return None, None


async def _execute_tool(tools: dict, tc: dict) -> tuple[str, str, str]:
    """Execute a single tool call. Returns (name, result, tool_id)."""
    fn_name = tc.get("function", {}).get("name", "")
    fn_args = tc.get("function", {}).get("arguments", {})
    tool_id = tc.get("id", "")

    func = tools.get(fn_name)
    if not func:
        return fn_name, f"Unknown tool: {fn_name}", tool_id

    try:
        if isinstance(fn_args, str):
            fn_args = json.loads(fn_args)
        result = await func(**fn_args)
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        result = f"Error: {e}"

    return fn_name, result, tool_id


async def _pre_parse_build(message: str) -> tuple[str, str | None]:
    """Detect PoB code or URL in message, parse it, return (clean_message, parsed_build).

    PoB codes are 10-20K chars — too long for LLM tool call arguments.
    Pre-parsing avoids the tool_use_failed error.
    """
    # Check for pobb.in / pastebin URL
    url_match = _POB_URL_RE.search(message)
    if url_match:
        url = url_match.group(0)
        try:
            from poe_intel.tools import poe_parse_build

            parsed = await poe_parse_build(url)
            clean = message.replace(url, "[build link]").strip()
            return clean, parsed
        except Exception as e:
            logger.warning("Pre-parse URL failed: %s", e)
            return message, f"[Failed to parse build URL: {e}]"

    # Check for raw PoB code (base64, very long)
    code_match = _POB_CODE_RE.search(message)
    if code_match:
        code = code_match.group(0)
        try:
            from poe_intel.tools import poe_parse_build

            parsed = await poe_parse_build(code)
            # Replace the huge code with a placeholder in the message
            clean = message.replace(code, "[PoB code]").strip()
            return clean, parsed
        except Exception as e:
            logger.warning("Pre-parse PoB code failed: %s", e)
            return message, f"[Failed to parse PoB code: {e}]"

    return message, None


async def poe_chat(user_message: str, router, mode: str = "auto") -> dict:
    """Process a message. Returns {response, tools_used, provider, model, mode}.

    For auto/light/heavy: uses PoE tool loop with provider routing.
    """
    tools, schemas = _get_tools()

    # Pre-parse PoB codes/URLs before sending to LLM (too large for tool args)
    clean_message, build_data = await _pre_parse_build(user_message)

    _history.append({"role": "user", "content": user_message})
    if len(_history) > _MAX_HISTORY:
        _history[:] = _history[-_MAX_HISTORY:]

    # Build messages — inject parsed build as context if found
    msg_content = clean_message
    if build_data:
        msg_content = f"{clean_message}\n\n[AUTO-PARSED BUILD DATA]\n{build_data}"

    messages = [
        Message(role="system", content=_POE_SYSTEM_PROMPT),
        *[Message(role=m["role"], content=m["content"]) for m in _history[:-1]],
        Message(role="user", content=msg_content),
    ]

    provider, model = _resolve_provider(router, mode)
    if not provider:
        return {
            "response": "Error: no LLM provider available.",
            "tools_used": [],
            "provider": "",
            "model": "",
            "mode": mode,
        }

    tools_used = []

    for _round in range(5):
        result = await provider.complete(messages=messages, model=model, tools=schemas)

        if not result.tool_calls:
            response = result.content or ""
            _history.append({"role": "assistant", "content": response})
            return {
                "response": response,
                "tools_used": tools_used,
                "provider": provider.name,
                "model": model,
                "mode": mode,
            }

        messages.append(
            Message(
                role="assistant",
                content=result.content or "",
                tool_calls=result.tool_calls,
            )
        )

        for tc in result.tool_calls:
            fn_name, tool_result, tool_id = await _execute_tool(tools, tc)
            tools_used.append({"name": fn_name, "result_preview": tool_result[:200]})
            messages.append(
                Message(role="tool", content=tool_result, tool_call_id=tool_id)
            )

    return {
        "response": "Error: too many tool call rounds.",
        "tools_used": tools_used,
        "provider": provider.name,
        "model": model,
        "mode": mode,
    }


async def poe_chat_via_bridge(user_message: str, bridge, bridge_type: str) -> dict:
    """Process a message via CLI bridge (claude/codex/cursor/copilot).

    Enhances prompt with PoE context and streams through the bridge.
    """
    # Pre-parse PoB codes/URLs before sending to bridge
    clean_message, build_data = await _pre_parse_build(user_message)

    _history.append({"role": "user", "content": user_message})
    if len(_history) > _MAX_HISTORY:
        _history[:] = _history[-_MAX_HISTORY:]

    # Build context from recent history
    context_lines = []
    for m in _history[-6:-1]:  # last few messages for context
        role = "User" if m["role"] == "user" else "Assistant"
        context_lines.append(f"{role}: {m['content'][:300]}")
    context = "\n".join(context_lines)

    enhanced = (
        f"[PoE Expert Mode] You are a Path of Exile expert. "
        f"Answer based on deep PoE knowledge: builds, economy, mechanics, crafting.\n"
    )
    if context:
        enhanced += f"\nRecent conversation:\n{context}\n"
    if build_data:
        enhanced += f"\n[AUTO-PARSED BUILD DATA]\n{build_data}\n"
    enhanced += f"\nUser: {clean_message}"

    # Collect all chunks from bridge stream
    chunks = []
    tools_used = []
    try:
        async for event in bridge.stream_response(enhanced):
            etype = event.get("type")
            if etype == "chunk":
                chunks.append(str(event.get("data", "")))
            elif etype == "tool":
                tools_used.append({"name": str(event.get("name", ""))})
            elif etype == "error":
                raise RuntimeError(str(event.get("message", "CLI failed")))
    except Exception as e:
        response = f"Error: {e}"
        _history.append({"role": "assistant", "content": response})
        return {
            "response": response,
            "tools_used": tools_used,
            "provider": bridge_type,
            "model": "",
            "mode": bridge_type,
        }

    response = "".join(chunks).strip()
    if not response:
        response = f"{bridge_type.title()} CLI returned empty response."

    _history.append({"role": "assistant", "content": response})
    return {
        "response": response,
        "tools_used": tools_used,
        "provider": bridge_type,
        "model": "",
        "mode": bridge_type,
    }


def get_history() -> list[dict]:
    return list(_history)


def clear_history():
    _history.clear()
