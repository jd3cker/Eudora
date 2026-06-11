from .base import Side, Signal, Strategy
from .sma_crossover import SmaCrossover

#: Registry so strategies can be selected by name from config.
REGISTRY = {
    SmaCrossover.name: SmaCrossover,
}


def build(name: str, **params) -> Strategy:
    """Instantiate a strategy by its registered name."""
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown strategy {name!r}; available: {sorted(REGISTRY)}"
        )
    return cls(**params)


__all__ = ["Side", "Signal", "Strategy", "SmaCrossover", "REGISTRY", "build"]
