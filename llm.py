"""llm — a thin provider adapter so the model is swappable (Ollama <-> Claude).

Everything else in the system is model-agnostic; this isolates the differences
between Ollama's OpenAI-ish API and Anthropic's Messages API behind one call:

    chat(messages, tools=None, schema=None) -> Response(.text, .tool_calls)

Config (env):
  LLM_BACKEND   ollama | anthropic            (default: ollama)
  LLM_MODEL     model id (default: qwen3:14b / claude-opus-4-8 per backend)

Neutral message format callers build (backend-independent):
  {"role": "user" | "assistant" | "tool", "content": str,
   "tool_calls":   [{"id","name","args"}]      # on an assistant turn, optional
   "tool_call_id": str, "name": str}           # on a tool-result turn

`tools` are given in OpenAI/Ollama function shape (the existing TOOLS list); the
adapter converts to Anthropic's shape when needed. Only one call site changes per
backend — the rest of the system never sees a provider.
"""

import os
from dataclasses import dataclass, field

BACKEND = os.environ.get("LLM_BACKEND", "ollama").lower()
_DEFAULT_MODEL = {"ollama": "qwen3:14b", "anthropic": "claude-opus-4-8"}
MODEL = os.environ.get("LLM_MODEL", _DEFAULT_MODEL.get(BACKEND, "qwen3:14b"))


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Response:
    text: str = ""
    tool_calls: list = field(default_factory=list)


def _json_text(text: str) -> str:
    """Strip markdown code fences if the model wrapped its JSON in them."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
        t = t.strip().rstrip("`").strip()
    return t


def parse(messages: list, schema: dict, model_cls, *, backend: str | None = None,
          model: str | None = None, retries: int = 2):
    """Structured output with VALIDATION + retry.

    `schema` drives constrained decoding (unchanged — the proven path); `model_cls` is a
    pydantic BaseModel that validates the RESULT (types, required fields, enums). On a
    validation/parse failure the error is fed back and the call retried, so a
    slightly-off reply is corrected instead of crashing a bare json.loads. Returns a
    validated `model_cls` instance; raises ValueError if it can't be validated in time.
    """
    convo = list(messages)
    last = None
    for _ in range(max(1, retries + 1)):
        resp = chat(convo, schema=schema, backend=backend, model=model)
        try:
            return model_cls.model_validate_json(_json_text(resp.text))
        except Exception as err:            # pydantic ValidationError / JSON error
            last = err
            convo = convo + [
                {"role": "assistant", "content": resp.text},
                {"role": "user", "content": (
                    "Your last reply did not match the required JSON schema "
                    f"({type(err).__name__}: {err}). Reply again with ONLY valid JSON "
                    "matching the schema — no prose, no code fences.")}]
    raise ValueError(f"structured output failed validation after {retries + 1} tries: {last}")


def chat(messages: list, tools: list | None = None, schema: dict | None = None,
         backend: str | None = None, model: str | None = None) -> Response:
    """Model-agnostic chat. Returns normalized text + tool calls.

    `backend`/`model` override the global config for THIS call — so a local-Ollama
    orchestrator can delegate a single step to Claude (the specialist) without
    changing the process-wide backend."""
    b = (backend or BACKEND).lower()
    # honor LLM_MODEL only when the call uses the globally-configured backend;
    # an explicit backend switch resolves to that backend's default model.
    m = model or (MODEL if b == BACKEND else _DEFAULT_MODEL.get(b, MODEL))
    if b == "anthropic":
        return _anthropic_chat(messages, tools, schema, m)
    return _ollama_chat(messages, tools, schema, m)


# --------------------------------------------------------------------------- #
# Ollama backend (default) — reproduces the system's current behavior.        #
# --------------------------------------------------------------------------- #

def _ollama_chat(messages, tools, schema, model=MODEL) -> Response:
    import ollama

    native = []
    for m in messages:
        if m["role"] == "tool":
            native.append({"role": "tool", "tool_name": m.get("name", ""),
                           "content": m["content"]})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            native.append({
                "role": "assistant", "content": m.get("content", ""),
                "tool_calls": [{"function": {"name": tc["name"], "arguments": tc["args"]}}
                               for tc in m["tool_calls"]],
            })
        else:
            native.append({"role": m["role"], "content": m["content"]})

    kwargs = {"model": model, "messages": native, "think": False}
    if tools:
        kwargs["tools"] = tools
    if schema:
        kwargs["format"] = schema

    msg = ollama.chat(**kwargs)["message"]
    calls = [ToolCall(id=f"call_{i}", name=tc["function"]["name"],
                      args=tc["function"]["arguments"])
             for i, tc in enumerate(msg.get("tool_calls") or [])]
    return Response(text=msg.get("content", "") or "", tool_calls=calls)


# --------------------------------------------------------------------------- #
# Anthropic backend (Claude). Best-effort; requires `anthropic` + an API key.  #
# --------------------------------------------------------------------------- #

def _to_anthropic_messages(messages) -> list:
    out = []
    for m in messages:
        if m["role"] == "tool":
            out.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                 "content": m["content"]}]})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                blocks.append({"type": "tool_use", "id": tc["id"],
                               "name": tc["name"], "input": tc["args"]})
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


def _anthropic_chat(messages, tools, schema, model=MODEL) -> Response:
    import anthropic

    client = anthropic.Anthropic()
    kwargs = {
        "model": model,
        "max_tokens": 16000,
        "messages": _to_anthropic_messages(messages),
    }
    if tools:
        # No thinking in the tool loop: adaptive thinking emits thinking blocks that
        # must be replayed across turns for tool continuity, which the neutral
        # message format doesn't carry. Single-shot calls (below) can think freely.
        kwargs["tools"] = [{"name": t["function"]["name"],
                            "description": t["function"].get("description", ""),
                            "input_schema": t["function"]["parameters"]}
                           for t in tools]
    else:
        kwargs["thinking"] = {"type": "adaptive"}
    if schema:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}

    resp = client.messages.create(**kwargs)
    text, calls = "", []
    for block in resp.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, args=block.input))
    return Response(text=text, tool_calls=calls)
