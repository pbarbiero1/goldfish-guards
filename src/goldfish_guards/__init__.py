# ONE home for the version: pyproject.toml. 0.4.1/0.4.2 shipped with this
# string hand-kept and stale at "0.4.0" (Leaftosser, 4044). A source-tree run
# must NOT ask installed metadata — an ambient stale dist answers fluently for
# the wrong tree (this repair's own first cut failed its test exactly so).
def _version():
    import pathlib, re
    _pp = pathlib.Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    if _pp.is_file():
        m = re.search(r'^version = "([^"]+)"', _pp.read_text(), re.M)
        if m:
            return m.group(1)
    try:
        from importlib.metadata import version as _v
        return _v("goldfish-guards")
    except Exception:
        return "unknown"
__version__ = _version()
