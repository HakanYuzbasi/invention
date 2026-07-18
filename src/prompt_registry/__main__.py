"""Allow `python -m prompt_registry` as an alternative to the console script."""

from .cli import entrypoint

if __name__ == "__main__":
    entrypoint()
