"""LLM abstraction with FakeLLM (offline) and LangChain backends."""
from __future__ import annotations

from dataclasses import dataclass

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.config import get_settings


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class BaseLLM:
    model: str = "base"

    async def ainvoke(self, system: str, messages: list[dict]) -> LLMResult:  # pragma: no cover
        raise NotImplementedError


class FakeLLM(BaseLLM):
    """Deterministic offline model for local dev and tests."""

    model = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, system: str, messages: list[dict]) -> LLMResult:
        self.calls += 1
        sys = system.lower()
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        convo_text = "\n".join(m.get("content", "") for m in messages)

        if "calc:" in last_user.lower() and "OBSERVATION:" not in convo_text:
            expr = last_user.lower().split("calc:", 1)[1].strip()
            resp = f'CALL calculator {{"expr": "{expr}"}}'
        elif "reviewer" in sys or "review" in sys:
            writer_turns = sum(1 for m in messages if m.get("name") == "Writer")
            if writer_turns >= 2:
                resp = "APPROVE — the draft meets the bar."
            else:
                resp = "REVISE — tighten the hook and trim adjectives."
        else:
            role_hint = system.splitlines()[0][:60] if system else "agent"
            resp = f"[{role_hint}] handled: {last_user[:200]}".strip()

        pt = _estimate_tokens(system + convo_text)
        ct = _estimate_tokens(resp)
        return LLMResult(text=resp, prompt_tokens=pt, completion_tokens=ct, model=self.model)


class LangChainLLM(BaseLLM):
    """Real model via LangChain; provider SDK is imported lazily."""

    def __init__(self, model: str, provider: str, api_key: str) -> None:
        self.model = model
        self._provider = provider
        self._api_key = api_key
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        if self._provider == "openai":
            self._client = ChatOpenAI(model=self.model, api_key=self._api_key, temperature=0.3)
        elif self._provider == "anthropic":
            self._client = ChatAnthropic(model=self.model, api_key=self._api_key, temperature=0.3)
        elif self._provider == "groq":
            self._client = ChatOpenAI(
                model=self.model,
                api_key=self._api_key,
                base_url="https://api.groq.com/openai/v1",
                temperature=0.3,
            )
        elif self._provider == "openrouter":
            self._client = ChatOpenAI(
                model=self.model,
                api_key=self._api_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=0.3,
            )
        elif self._provider == "mistral":
            self._client = ChatOpenAI(
                model=self.model,
                api_key=self._api_key,
                base_url="https://api.mistral.ai/v1",
                temperature=0.3,
            )
        elif self._provider == "gemini":
            self._client = ChatGoogleGenerativeAI(
                model=self.model,
                google_api_key=self._api_key,
                temperature=0.3,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {self._provider}")

    async def ainvoke(self, system: str, messages: list[dict]) -> LLMResult:
        self._ensure_client()
        lc_msgs = [SystemMessage(content=system)]
        for m in messages:
            if m.get("role") == "assistant":
                lc_msgs.append(AIMessage(content=m["content"]))
            else:
                lc_msgs.append(HumanMessage(content=m["content"]))

        resp = await self._client.ainvoke(lc_msgs)
        meta = getattr(resp, "usage_metadata", None) or {}
        pt = meta.get("input_tokens", _estimate_tokens(system))
        ct = meta.get("output_tokens", _estimate_tokens(resp.content))
        return LLMResult(text=resp.content, prompt_tokens=pt, completion_tokens=ct, model=self.model)


def get_llm(model: str | None = None) -> BaseLLM:
    """Return the configured LLM, falling back to FakeLLM when no API key is set."""
    settings = get_settings()
    model = model or settings.default_model
    if settings.llm_provider == "fake" or model == "fake" or not settings.llm_api_key:
        return FakeLLM()
    return LangChainLLM(model=model, provider=settings.llm_provider, api_key=settings.llm_api_key)
