"""Tests for the verb-animal replica name generator."""

from mcpworks_api.core.replica_names import (
    ANIMALS,
    POOL_SIZE,
    VERBS,
    generate_replica_name,
)


class TestReplicaNameGenerator:
    def test_generates_verb_animal_format(self):
        name = generate_replica_name()
        parts = name.split("-")
        assert len(parts) == 2
        assert parts[0] in VERBS
        assert parts[1] in ANIMALS

    def test_pool_size_at_least_2500(self):
        assert POOL_SIZE >= 2500

    def test_unique_within_existing(self):
        existing = {"bold-ant", "brave-bear"}
        name = generate_replica_name(existing_names=existing)
        assert name not in existing

    def test_avoids_collisions(self):
        names: set[str] = set()
        for _ in range(50):
            name = generate_replica_name(existing_names=names)
            assert name not in names
            names.add(name)

    def test_exhaustive_fallback(self):
        almost_full = {f"{v}-{a}" for v in VERBS for a in ANIMALS}
        keep = almost_full.pop()
        name = generate_replica_name(existing_names=almost_full)
        assert name == keep

    def test_raises_when_pool_exhausted(self):
        full_pool = {f"{v}-{a}" for v in VERBS for a in ANIMALS}
        import pytest

        with pytest.raises(RuntimeError, match="No unique replica names available"):
            generate_replica_name(existing_names=full_pool)
