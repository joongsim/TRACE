from trace_app.storage.database import build_engine, build_session_factory


def test_build_engine_returns_engine() -> None:
    """build_engine should return a SQLAlchemy Engine."""
    from sqlalchemy import Engine

    engine = build_engine("sqlite:///")
    assert isinstance(engine, Engine)


def test_build_session_factory_returns_callable() -> None:
    """build_session_factory should return a sessionmaker."""
    engine = build_engine("sqlite:///")
    session_factory = build_session_factory(engine)
    session = session_factory()
    assert session is not None
    session.close()
