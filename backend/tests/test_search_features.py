from app.core.search_features import search_features,formula_shape

def test_features_are_bounded_and_candidate_only():
    a=search_features(r"求 $\int_0^1 x^2 dx$")
    b=search_features(r"求 $\int_0^2 x^3 dx$")
    assert set(a)&set(b)
    assert any(k.startswith("m:") for k in set(a)&set(b))
    assert len(search_features("".join(chr(0x4e00+i) for i in range(6000))))<=129
