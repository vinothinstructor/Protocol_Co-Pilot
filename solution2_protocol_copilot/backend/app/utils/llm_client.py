from abc import ABC, abstractmethod
from app.config import settings, LLMMode


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, prompt: str, *, agent: str, context: dict | None = None) -> str: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...


class MockLLMClient(LLMClient):
    async def complete(self, prompt, *, agent, context=None) -> str:
        return "__MOCK_FALLBACK__"

    async def embed(self, text) -> list[float]:
        return _deterministic_pseudo_embedding(text, settings.embedding_dim)


class FakeLLMClient(LLMClient):
    # Phase 1: same as mock for embed; complete returns deterministic stub.
    # Real fake scoring logic added in Phase 2.
    async def complete(self, prompt, *, agent, context=None) -> str:
        return "__FAKE_STUB__"

    async def embed(self, text) -> list[float]:
        return _deterministic_pseudo_embedding(text, settings.embedding_dim)


class CachedLLMClient(LLMClient):
    # Phase 1: stub. Real cache replay added in Phase 2.
    async def complete(self, prompt, *, agent, context=None) -> str:
        raise NotImplementedError("Cache replay implemented in Phase 2")

    async def embed(self, text) -> list[float]:
        raise NotImplementedError("Cached embeddings implemented in Phase 2")


class LiveLLMClient(LLMClient):
    def __init__(self):
        # Fail loudly if credentials missing (Solution 1 lesson — silent failure hangs later)
        missing = [k for k in ("azure_openai_endpoint", "azure_openai_api_key")
                   if not getattr(settings, k)]
        if missing:
            raise RuntimeError(f"LiveLLMClient missing Azure config: {missing}")
        from openai import AsyncAzureOpenAI
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    async def complete(self, prompt, *, agent, context=None) -> str:
        resp = await self._client.chat.completions.create(
            model=settings.azure_llm_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return resp.choices[0].message.content

    async def embed(self, text) -> list[float]:
        resp = await self._client.embeddings.create(
            model=settings.azure_embedding_deployment,
            input=text,
        )
        return resp.data[0].embedding


def _deterministic_pseudo_embedding(text: str, dim: int) -> list[float]:
    """Hash-seeded pseudo-embedding for dev/mock mode without Azure.
    NOT semantically meaningful — only exercises the vector-search code path."""
    import hashlib
    import random
    seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec]


def get_llm_client() -> LLMClient:
    return {
        LLMMode.MOCK: MockLLMClient,
        LLMMode.FAKE: FakeLLMClient,
        LLMMode.CACHED: CachedLLMClient,
        LLMMode.LIVE: LiveLLMClient,
    }[settings.llm_mode]()
