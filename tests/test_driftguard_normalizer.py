from onyxlib.drift.normalizer import normalize_config


def test_normalize_config_filters_comments_and_whitespace():
    raw = """
    ! comment
    ip   http  server

      interface Gi0/1
       description  Uplink
    # another comment
    """
    normalized = normalize_config(raw)
    assert normalized == [
        "ip http server",
        "interface Gi0/1",
        "description Uplink",
    ]
