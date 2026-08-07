"""Single source for the engine_semver stamped onto every FactSnapshot."""

from importlib import metadata


def engine_semver() -> str:
    try:
        return metadata.version("sitara-astro")
    except metadata.PackageNotFoundError:  # pragma: no cover - installed in all envs
        from sitara_astro import __version__

        return __version__
