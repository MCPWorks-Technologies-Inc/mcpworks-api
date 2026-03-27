"""Verb-animal name generator for agent cluster replicas.

Generates unique, human-friendly names like "daring-duck" or "swift-falcon"
for individual replicas within an agent cluster. Names are unique within
a cluster but may be reused across different clusters.
"""

import random
from collections.abc import Collection

VERBS = [
    "bold",
    "brave",
    "bright",
    "brisk",
    "calm",
    "clear",
    "clever",
    "cool",
    "crisp",
    "daring",
    "eager",
    "even",
    "fair",
    "fast",
    "fierce",
    "firm",
    "fleet",
    "fluid",
    "frank",
    "fresh",
    "glad",
    "grand",
    "great",
    "keen",
    "kind",
    "lively",
    "lucid",
    "merry",
    "mighty",
    "noble",
    "plain",
    "prime",
    "proud",
    "pure",
    "quick",
    "quiet",
    "rapid",
    "ready",
    "sharp",
    "sleek",
    "smart",
    "smooth",
    "snappy",
    "solid",
    "steady",
    "stout",
    "strong",
    "sturdy",
    "super",
    "swift",
]

ANIMALS = [
    "ant",
    "badger",
    "bear",
    "bison",
    "cobra",
    "condor",
    "crane",
    "crow",
    "deer",
    "dolphin",
    "dove",
    "duck",
    "eagle",
    "elk",
    "falcon",
    "finch",
    "fox",
    "frog",
    "goat",
    "goose",
    "gull",
    "hawk",
    "heron",
    "horse",
    "ibis",
    "jay",
    "kite",
    "lark",
    "lion",
    "lynx",
    "marten",
    "mink",
    "moose",
    "newt",
    "otter",
    "owl",
    "panda",
    "parrot",
    "pike",
    "puma",
    "quail",
    "ram",
    "raven",
    "robin",
    "salmon",
    "seal",
    "shrike",
    "snake",
    "squid",
    "stork",
    "swan",
    "tern",
    "tiger",
    "trout",
    "viper",
    "vole",
    "wasp",
    "whale",
    "wolf",
    "wren",
]

POOL_SIZE = len(VERBS) * len(ANIMALS)


def generate_replica_name(existing_names: Collection[str] = (), max_retries: int = 10) -> str:
    for _ in range(max_retries):
        name = f"{random.choice(VERBS)}-{random.choice(ANIMALS)}"
        if name not in existing_names:
            return name

    all_names = [f"{v}-{a}" for v in VERBS for a in ANIMALS]
    random.shuffle(all_names)
    for name in all_names:
        if name not in existing_names:
            return name

    raise RuntimeError(
        f"No unique replica names available (pool={POOL_SIZE}, existing={len(existing_names)})"
    )
