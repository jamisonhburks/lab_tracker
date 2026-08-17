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

import token_meter                    # token accounting; capture is a no-op unless metered

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
    in_tok: int = 0
    out_tok: int = 0


def _field(obj, name, default=0):
    """Read `name` off a provider response that may be a dict or an SDK object."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            return getter(name, default)
        except Exception:
            pass
    return getattr(obj, name, default)


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
    for attempt in range(max(1, retries + 1)):
        # a re-ask after a bad parse is rework — mark its tokens `retry` so the audit can see it.
        if attempt == 0:
            resp = chat(convo, schema=schema, backend=backend, model=model)
        else:
            with token_meter.outcome("retry"):
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

    raw = ollama.chat(**kwargs)
    msg = raw["message"]
    calls = [ToolCall(id=f"call_{i}", name=tc["function"]["name"],
                      args=tc["function"]["arguments"])
             for i, tc in enumerate(msg.get("tool_calls") or [])]
    in_tok = _field(raw, "prompt_eval_count")     # Ollama reports token counts (cost-free, ADR-0060)
    out_tok = _field(raw, "eval_count")
    token_meter.on_llm_call("ollama", model, in_tok, out_tok)
    return Response(text=msg.get("content", "") or "", tool_calls=calls,
                    in_tok=int(in_tok or 0), out_tok=int(out_tok or 0))


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
    usage = getattr(resp, "usage", None)            # PAID tokens — always metered
    in_tok = getattr(usage, "input_tokens", 0) or 0
    out_tok = getattr(usage, "output_tokens", 0) or 0
    token_meter.on_llm_call("anthropic", model, in_tok, out_tok)
    return Response(text=text, tool_calls=calls, in_tok=int(in_tok), out_tok=int(out_tok))
