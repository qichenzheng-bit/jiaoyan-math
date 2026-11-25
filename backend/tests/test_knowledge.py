from app.api.knowledge import would_cycle

def test_cycle_check():
    rows=[("a","b","contains"),("b","c","contains")]
    assert would_cycle(rows,"c","a","contains")
    assert not would_cycle(rows,"a","c","contains")
    assert not would_cycle(rows,"c","a","prerequisite")
