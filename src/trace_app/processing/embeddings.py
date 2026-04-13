"""Pure functions for generating rule embeddings."""

from sentence_transformers import SentenceTransformer

from trace_app.storage.models import Rule


def build_embed_text(rule: Rule) -> str:
    return f"{rule.title}\n\n{rule.abstract or ''}\n\n{rule.full_text[:2048]}"


def load_model(name: str) -> SentenceTransformer:
    return SentenceTransformer(name)


def embed_batch(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    return model.encode(texts, convert_to_numpy=True).tolist()
