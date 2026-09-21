# Three test files are standalone scripts with their own runners and
# hand-rolled fixtures (run them directly: `python3 tests/test_broll.py`).
# pytest would otherwise collect their helper functions and report
# "fixture not found" errors. The remaining files are pytest-native.
collect_ignore = [
    "test_broll.py",
    "test_finish_reel.py",
    "test_render_reel.py",
]
