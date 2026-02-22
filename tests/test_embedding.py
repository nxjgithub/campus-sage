from __future__ import annotations

from app.core.settings import Settings, reset_settings
from app.rag.embedding import (
    HttpEmbeddingClient,
    LocalEmbeddingClient,
    _build_embedding_endpoint,
    get_embedder,
    reset_embedder,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict[str, object]:
        return self._payload


def test_http_embedding_client_calls_openai_compatible_endpoint(
    monkeypatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "http")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://mock.local/v1/")
    monkeypatch.setenv("EMBEDDING_API_PATH", "embeddings")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "demo-embed")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    monkeypatch.setenv("VECTOR_DIM", "3")
    reset_settings()
    reset_embedder()
    settings = Settings()

    captured: dict[str, object] = {}

    def fake_post(
        url: str,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: int,
        trust_env: bool,
    ) -> _FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["trust_env"] = trust_env
        return _FakeResponse(
            200,
            {
                "data": [
                    {"index": 1, "embedding": [0, 1, 0]},
                    {"index": 0, "embedding": [1, 0, 0]},
                ]
            },
        )

    monkeypatch.setattr("app.rag.embedding.httpx.post", fake_post)
    embedder = HttpEmbeddingClient(settings)
    vectors = embedder.embed_texts(["first", "second"])

    assert captured["url"] == "http://mock.local/v1/embeddings"
    assert captured["json"] == {
        "model": "demo-embed",
        "input": ["first", "second"],
        "dimensions": 3,
    }
    assert captured["trust_env"] is False
    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


def test_build_embedding_endpoint_normalizes_path() -> None:
    assert _build_embedding_endpoint("http://localhost:8001/v1/", "embeddings") == (
        "http://localhost:8001/v1/embeddings"
    )
    assert _build_embedding_endpoint("http://localhost:8001/v1", "/embeddings") == (
        "http://localhost:8001/v1/embeddings"
    )


def test_get_embedder_supports_local_backend(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    reset_settings()
    reset_embedder()
    settings = Settings()

    embedder = get_embedder(settings)

    assert isinstance(embedder, LocalEmbeddingClient)
    reset_embedder()
    reset_settings()
