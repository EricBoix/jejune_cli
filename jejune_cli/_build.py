"""Self-registering Docker image build registry.

Each component that owns a Docker image calls register_build() at module level.
jejune build iterates the registry filtered by the active role's components.
"""

from typing import Callable

# Maps component name → (build_fn, is_built_fn | None)
_BUILD_REGISTRY: dict[str, tuple[Callable[[bool], None], Callable[[], bool] | None]] = {}


def register_build(
    component: str,
    fn: Callable[[bool], None],
    is_built: Callable[[], bool] | None = None,
) -> None:
    """Register a Docker image builder for a named component.

    fn(no_cache) builds the image; is_built() reports whether it already exists.
    """
    _BUILD_REGISTRY[component] = (fn, is_built)
