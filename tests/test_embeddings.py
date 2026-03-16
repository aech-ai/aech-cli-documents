from types import SimpleNamespace

import pytest

from aech_cli_documents.corpus.database import Corpus, create_corpus
from aech_cli_documents.corpus import embeddings


def _reset_embedding_runtime() -> None:
    embeddings._client = None
    embeddings._client_config = None
    embeddings._embedding_dim = None


def test_encode_batch_uses_openai_compatible_endpoint(monkeypatch):
    _reset_embedding_runtime()
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://host.docker.internal:1234/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-bge-m3@fp16")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "2")

    calls = []

    class FakeClient:
        def __init__(self):
            self.embeddings = self

        def create(self, model, input):
            calls.append((model, input))
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=index, embedding=[float(index + 1), 0.5])
                    for index, _ in enumerate(input)
                ]
            )

    monkeypatch.setattr(embeddings, "_get_openai_client", lambda: FakeClient())

    vectors = embeddings.encode_batch(["first", "second", "third"])

    assert calls == [
        ("text-embedding-bge-m3@fp16", ["first", "second"]),
        ("text-embedding-bge-m3@fp16", ["third"]),
    ]
    assert len(vectors) == 3
    assert vectors[0] == pytest.approx([1.0, 0.5])
    assert vectors[1] == pytest.approx([2.0, 0.5])
    assert vectors[2] == pytest.approx([1.0, 0.5])
    assert embeddings.get_embedding_dimension() == 2


def test_batch_cosine_similarity_handles_non_normalized_vectors():
    similarities = embeddings.batch_cosine_similarity(
        [3.0, 4.0],
        [[6.0, 8.0], [4.0, -3.0], [0.0, 0.0]],
    )

    assert similarities == pytest.approx([1.0, 0.0, 0.0])


def test_corpus_embedding_model_mismatch_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://host.docker.internal:1234/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-bge-m3@fp16")
    corpus = create_corpus(tmp_path / "docs.db")
    corpus.close()

    reopened = Corpus(tmp_path / "docs.db")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-nomic-embed-text-v1.5")

    with pytest.raises(RuntimeError, match="Corpus embedding model mismatch"):
        reopened.ensure_configured_embedding_model()
