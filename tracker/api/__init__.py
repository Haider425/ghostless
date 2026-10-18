"""Read-only web API over the collected data. Requires the `api` extra:

pip install -e ".[api]"
ghostless serve
"""

from tracker.api.app import create_app

__all__ = ["create_app"]
