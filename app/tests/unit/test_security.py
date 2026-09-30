"""
Regression test for a real bug found while manually testing this project:
create_access_token() previously produced byte-identical tokens when called
twice within the same second for the same user, because RS256 signing is
deterministic and the JWT payload (sub, role, scopes, exp, iat) was
identical at one-second granularity. Fixed by adding a unique `jti` claim.
"""
from app.core.security import create_access_token


def test_access_tokens_are_unique_even_within_the_same_second():
    tokens = {
        create_access_token(subject="user-1", role="user", scopes=["rag:query"])
        for _ in range(20)
    }
    assert len(tokens) == 20, "create_access_token produced a duplicate token in a tight loop"
