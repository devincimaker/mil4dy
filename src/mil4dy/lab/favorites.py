"""Compatibility alias. Persistence lives in history.py."""

from .history import HistoryRecord as FavoriteRecord
from .history import HistoryStore as FavoriteStore
from .history import TrackIdentity

__all__ = ["FavoriteRecord", "FavoriteStore", "TrackIdentity"]
