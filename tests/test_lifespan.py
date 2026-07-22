"""RED contract for the FastAPI lifespan single-construction wiring (SC1/D-01/INT-01).

Unit test, no network. The four shared-client constructors are patched at their
``api.main`` import site, the ``lifespan(app)`` async context is entered once
(driven with stdlib :func:`asyncio.run` on an inline helper, matching the
``collect_stream`` idiom), and we assert each constructor was called EXACTLY once
and its instance parked on ``app.state``. This is the SC1 contract: shared
clients are built once at startup, never per request.

RED until Wave 2 (05-02): ``api.main`` today has no ``lifespan`` and does not
import ``QdrantClient`` / ``AsyncOpenAI`` / ``OpenAI`` / ``create_engine``, and
``monitoring.db`` does not exist — so the patch targets / imports below raise.
The plan that turns this green adds the lifespan handler that constructs the
clients once, stores them on ``app.state``, and calls
``metadata.create_all(engine, checkfirst=True)``.
"""

import asyncio


def _drive_lifespan(app, lifespan):
    """Enter and exit the lifespan async context once on a fresh event loop.

    Args:
        app: The FastAPI application instance.
        lifespan: The ``@asynccontextmanager`` lifespan handler.
    """

    async def _run():
        async with lifespan(app):
            pass

    asyncio.run(_run())


def test_clients_constructed_once_and_parked_on_state(mocker):
    """Each shared client is built exactly once and stored on app.state (SC1/D-01)."""
    qdrant = mocker.patch("api.main.QdrantClient")
    aopenai = mocker.patch("api.main.AsyncOpenAI")
    openai = mocker.patch("api.main.OpenAI")
    create_engine = mocker.patch("api.main.create_engine")

    from api.main import app, lifespan

    _drive_lifespan(app, lifespan)

    qdrant.assert_called_once()
    aopenai.assert_called_once()
    openai.assert_called_once()
    create_engine.assert_called_once()

    assert app.state.qdrant is qdrant.return_value
    assert app.state.aopenai is aopenai.return_value
    assert app.state.openai is openai.return_value
    assert app.state.engine is create_engine.return_value


def test_tables_created_idempotently_at_startup(mocker):
    """Startup calls metadata.create_all(engine, checkfirst=True) — idempotent DDL (D-02)."""
    mocker.patch("api.main.QdrantClient")
    mocker.patch("api.main.AsyncOpenAI")
    mocker.patch("api.main.OpenAI")
    create_engine = mocker.patch("api.main.create_engine")
    create_all = mocker.patch("monitoring.db.metadata.create_all")

    from api.main import app, lifespan

    _drive_lifespan(app, lifespan)

    create_all.assert_called_once()
    # Engine is the injected one; create is idempotent (checkfirst=True).
    assert create_all.call_args.args[0] is create_engine.return_value
    assert create_all.call_args.kwargs.get("checkfirst") is True
