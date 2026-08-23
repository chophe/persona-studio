from __future__ import annotations

from persona_studio.story import batch_documents


def make_doc(name: str, size: int) -> tuple[str, str]:
    return name, "x" * size


class TestBatchDocuments:
    def test_small_docs_fit_one_batch(self):
        docs = [make_doc(f"d{i}", 100) for i in range(5)]
        batches = batch_documents(docs, context_window=128000)
        assert len(batches) == 1
        assert len(batches[0]) == 5

    def test_splits_on_budget(self):
        docs = [make_doc(f"d{i}", 1000) for i in range(10)]
        tiny_window = 1000 * 4 // 800
        batches = batch_documents(docs, context_window=tiny_window)
        assert len(batches) > 1

    def test_oversized_doc_gets_own_batch(self):
        docs = [make_doc("huge", 10_000_000), make_doc("small", 10)]
        batches = batch_documents(docs, context_window=128000)
        assert len(batches) >= 2
        assert batches[0] == ["x" * 10_000_000]

    def test_preserves_order_and_completeness(self):
        texts = [f"text-{i}" for i in range(50)]
        docs = [(f"d{i}", t) for i, t in enumerate(texts)]
        batches = batch_documents(docs, context_window=1)
        flattened = [item for batch in batches for item in batch]
        assert sorted(flattened) == sorted(texts)

    def test_empty_input(self):
        assert batch_documents([], 128000) == []
