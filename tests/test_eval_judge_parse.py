"""Pure-unit RED spec for the judge-JSON parse contract (EVL-03).

Targets ``evaluation.eval_llm.parse_judge_response`` — a module-level helper that
does NOT exist yet (Plan 04-03 adds it). The import is deferred into each test
body, so these fail RED on the missing symbol rather than at collection time.

``parse_judge_response`` operates on a raw string only (no OpenAI client, no
network): it must turn a well-formed judge JSON into a dict of the three D-10
dimensions — accuracy / completeness / hallucination (NOT the scaffold's
``no_hallucination``) — as ints in the 1-5 range, and degrade a malformed /
non-JSON string to a graceful all-zero default without raising.
"""


def test_wellformed_judge_json_parses_to_three_int_dimensions():
    """A valid judge JSON yields the three D-10 dimensions as ints in 1-5."""
    from evaluation.eval_llm import parse_judge_response

    raw = (
        '{"accuracy": 5, "completeness": 3, "hallucination": 4, '
        '"rationale": "grounded in the retrieved context"}'
    )

    scores = parse_judge_response(raw)

    for dim in ("accuracy", "completeness", "hallucination"):
        assert dim in scores
        assert isinstance(scores[dim], int)
        assert 1 <= scores[dim] <= 5


def test_malformed_response_returns_graceful_zero_default():
    """A non-JSON string never raises — it returns all three dimensions as 0."""
    from evaluation.eval_llm import parse_judge_response

    scores = parse_judge_response("the model refused to answer in JSON")

    assert scores["accuracy"] == 0
    assert scores["completeness"] == 0
    assert scores["hallucination"] == 0
