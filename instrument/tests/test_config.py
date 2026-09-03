"""CONTRACTS for Config.from_env — the instrument's only env reader.

Previously untested despite being the single point where deployment
environment reaches the runtime. Pins: defaults, every override,
the tolerate-garbage-ints policy (fall back to default rather than
crash a container boot on a typo), and empty-string handling.
"""

from __future__ import annotations

from instrument.config import DEFAULT_CONFIG, Config, from_env


def test_defaults_without_env(monkeypatch):
    for var in ("INSTRUMENT_HOST", "INSTRUMENT_PORT",
                "INSTRUMENT_RESPONSE_SHAPE", "INSTRUMENT_MAX_WORDS",
                "INSTRUMENT_MAX_BODY_BYTES", "INSTRUMENT_CATALOG_VERSION",
                "INSTRUMENT_REFERENCES_DIR", "INSTRUMENT_BOOTSTRAP_B"):
        monkeypatch.delenv(var, raising=False)
    cfg = from_env()
    assert cfg == DEFAULT_CONFIG
    assert cfg.references_dir is None
    assert cfg.bootstrap_b == 200


def test_every_override(monkeypatch):
    monkeypatch.setenv("INSTRUMENT_HOST", "127.0.0.1")
    monkeypatch.setenv("INSTRUMENT_PORT", "9001")
    monkeypatch.setenv("INSTRUMENT_RESPONSE_SHAPE", "compact")
    monkeypatch.setenv("INSTRUMENT_MAX_WORDS", "5000")
    monkeypatch.setenv("INSTRUMENT_MAX_BODY_BYTES", "40000")
    monkeypatch.setenv("INSTRUMENT_CATALOG_VERSION", "v2")
    monkeypatch.setenv("INSTRUMENT_REFERENCES_DIR", "/etc/instrument/refs")
    monkeypatch.setenv("INSTRUMENT_BOOTSTRAP_B", "50")
    cfg = from_env()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9001
    assert cfg.response_shape == "compact"
    assert cfg.max_words == 5000
    assert cfg.max_body_bytes == 40000
    assert cfg.catalog_version == "v2"
    assert cfg.references_dir == "/etc/instrument/refs"
    assert cfg.bootstrap_b == 50


def test_garbage_int_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("INSTRUMENT_PORT", "not-a-port")
    monkeypatch.setenv("INSTRUMENT_MAX_WORDS", "10k")
    cfg = from_env()
    assert cfg.port == DEFAULT_CONFIG.port
    assert cfg.max_words == DEFAULT_CONFIG.max_words


def test_empty_string_means_unset(monkeypatch):
    monkeypatch.setenv("INSTRUMENT_PORT", "")
    monkeypatch.setenv("INSTRUMENT_REFERENCES_DIR", "")
    cfg = from_env()
    assert cfg.port == DEFAULT_CONFIG.port
    assert cfg.references_dir is None


def test_config_is_frozen():
    import dataclasses
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        Config().port = 1  # type: ignore[misc]
