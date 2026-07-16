"""RED contract for the Qdrant collection + idempotent upsert (ING-04/05/06).

Live-Qdrant integration: uses the ``qdrant_client`` / ``throwaway_collection``
fixtures from conftest, which skip cleanly when Qdrant is unreachable. No real
OpenAI key is needed — vectors are dummy 1536-length lists.

Contracts encoded:
  * The pipeline collection-setup path creates the collection at size=1536,
    cosine distance.
  * After upserting points, ``count(exact=True).count`` is > 0.
  * Re-upserting the SAME deterministic-id points leaves the count unchanged
    (idempotency at the Qdrant layer).
  * A pre-existing wrong-size collection self-heals to 1536 (delete + recreate).

Target imports are deferred into test bodies so unimplemented symbols fail RED,
never at collection time. RED until Plan 01-04 lands.
"""

EXPECTED_DIM = 1536


def _dummy_points(qdrant_models, count):
    """Build ``count`` PointStructs with deterministic ids and 1536-dim vectors.

    Args:
        qdrant_models: The imported ``qdrant_client.models`` module.
        count: Number of points to build.

    Returns:
        list: PointStruct instances with stable ids so re-upsert overwrites.
    """
    from ingestion.run_pipeline import point_id

    return [
        qdrant_models.PointStruct(
            id=point_id("test_src", i, f"chunk {i}"),
            vector=[0.1] * EXPECTED_DIM,
            payload={"source": "test_src", "position": i},
        )
        for i in range(count)
    ]


def test_collection_setup_creates_1536_cosine(qdrant_client, throwaway_collection):
    """The pipeline collection-setup path yields a size=1536 cosine collection."""
    from qdrant_client.models import Distance

    from ingestion.run_pipeline import ensure_collection

    ensure_collection(qdrant_client, throwaway_collection)

    info = qdrant_client.get_collection(throwaway_collection)
    params = info.config.params.vectors
    assert params.size == EXPECTED_DIM
    assert params.distance == Distance.COSINE


def test_upsert_yields_nonzero_count(qdrant_client, throwaway_collection):
    """After upsert the exact point count is greater than zero (ING-06)."""
    import qdrant_client.models as qmodels

    from ingestion.run_pipeline import ensure_collection

    ensure_collection(qdrant_client, throwaway_collection)
    qdrant_client.upsert(
        collection_name=throwaway_collection,
        points=_dummy_points(qmodels, 5),
    )
    assert qdrant_client.count(throwaway_collection, exact=True).count > 0


def test_reupsert_is_idempotent(qdrant_client, throwaway_collection):
    """Re-upserting identical-id points leaves the count unchanged (ING-05)."""
    import qdrant_client.models as qmodels

    from ingestion.run_pipeline import ensure_collection

    ensure_collection(qdrant_client, throwaway_collection)
    points = _dummy_points(qmodels, 5)

    qdrant_client.upsert(collection_name=throwaway_collection, points=points)
    first = qdrant_client.count(throwaway_collection, exact=True).count

    qdrant_client.upsert(collection_name=throwaway_collection, points=points)
    second = qdrant_client.count(throwaway_collection, exact=True).count

    assert first == second


def test_wrong_size_collection_self_heals_to_1536(qdrant_client, throwaway_collection):
    """A pre-existing wrong-width collection is recreated at 1536."""
    from qdrant_client.models import Distance, VectorParams

    from ingestion.run_pipeline import ensure_collection

    # Deliberately create the collection at the wrong (smaller) width.
    qdrant_client.create_collection(
        collection_name=throwaway_collection,
        vectors_config=VectorParams(size=512, distance=Distance.COSINE),
    )

    ensure_collection(qdrant_client, throwaway_collection)

    info = qdrant_client.get_collection(throwaway_collection)
    assert info.config.params.vectors.size == EXPECTED_DIM
