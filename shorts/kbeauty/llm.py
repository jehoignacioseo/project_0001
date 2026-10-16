"""Thin wrapper around the Anthropic SDK for the three call shapes the pipeline uses:
structured JSON (vision or text), web-searched research (server tool), and plain text.
Credentials: ANTHROPIC_API_KEY or an `ant auth login` profile. KB_MOCK=1 skips the API."""
import base64
import json
from pathlib import Path

from config import EFFORT, MODEL

_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(timeout=600.0)
    return _client


def _image_block(path):
    p = Path(path)
    mt = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": mt,
                                        "data": base64.b64encode(p.read_bytes()).decode()}}


def _check_refusal(resp):
    if resp.stop_reason == "refusal":
        sd = getattr(resp, "stop_details", None)
        raise RuntimeError(f"model refused: {getattr(sd, 'category', None)} {getattr(sd, 'explanation', '')}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("response truncated (max_tokens); raise max_tokens")


def _create(**kw):
    """Prefer the beta endpoint with server-side refusal fallbacks; fall back to the plain endpoint
    if the account/platform does not accept the beta."""
    import anthropic
    c = client()
    try:
        return c.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
    except anthropic.BadRequestError:
        return c.messages.create(**kw)


def structured(system, content, schema, images=(), max_tokens=16000, effort=None):
    """content: str or list of blocks. Returns parsed JSON that validates against `schema`."""
    blocks = [_image_block(p) for p in images]
    if isinstance(content, str):
        blocks.append({"type": "text", "text": content})
    else:
        blocks.extend(content)
    resp = _create(
        model=MODEL, max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": blocks}],
        output_config={"format": {"type": "json_schema", "schema": schema}, "effort": effort or EFFORT},
    )
    _check_refusal(resp)
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def research(system, prompt, max_uses=12, max_tokens=16000, max_continuations=5):
    """Run Claude with the web search server tool and return its final prose answer (with the
    URLs it cited). Handles pause_turn by resuming."""
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}]
    messages = [{"role": "user", "content": prompt}]
    for _ in range(max_continuations + 1):
        resp = _create(model=MODEL, max_tokens=max_tokens, tools=tools,
                       system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                       messages=messages, output_config={"effort": EFFORT})
        _check_refusal(resp)
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    text, urls = [], []
    for b in resp.content:
        if b.type == "text":
            text.append(b.text)
            for cit in (getattr(b, "citations", None) or []):
                u = getattr(cit, "url", None)
                if u and u not in urls:
                    urls.append(u)
        elif b.type == "web_search_tool_result" and isinstance(b.content, list):
            for r in b.content:
                u = getattr(r, "url", None)
                if u and u not in urls:
                    urls.append(u)
    return "\n".join(text), urls


def text(system, prompt, max_tokens=4000, effort="medium"):
    resp = _create(model=MODEL, max_tokens=max_tokens, system=system,
                   messages=[{"role": "user", "content": prompt}], output_config={"effort": effort})
    _check_refusal(resp)
    return "".join(b.text for b in resp.content if b.type == "text")
