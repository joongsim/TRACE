"""Prefect flow for generating and storing rule embeddings."""

from prefect import flow
from sqlalchemy import select

from trace_app.config import Settings
from trace_app.processing.embeddings import build_embed_text, embed_batch, load_model
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_embeddings
from trace_app.storage.models import Rule


@flow(name="embed_rules", log_prints=True)
def embed_rules(batch_size: int | None = None) -> None:
    """Embed all rules where embedding IS NULL. Safe to re-run."""
    settings = Settings()  # ty: ignore[missing-argument]
    effective_batch_size = batch_size if batch_size is not None else settings.embedding_batch_size

    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    model = load_model(settings.embedding_model)

    session = session_factory()
    try:
        rules = session.execute(select(Rule).where(Rule.embedding.is_(None))).scalars().all()

        total = len(rules)
        embedded = 0

        for i in range(0, total, effective_batch_size):
            batch = rules[i : i + effective_batch_size]
            texts = [build_embed_text(r) for r in batch]
            vectors = embed_batch(model, texts)
            save_embeddings(session, [r.rule_id for r in batch], vectors)
            session.commit()
            embedded += len(batch)
            print(f"embedded {embedded}/{total}")
    finally:
        session.close()

    print(f"done: {embedded} rules embedded")


if __name__ == "__main__":
    embed_rules()
