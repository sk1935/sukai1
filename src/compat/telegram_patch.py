"""
Compatibility helpers for python-telegram-bot when running on Python 3.13.

Python 3.13 prevents adding new attributes to classes that define ``__slots__``
without ``__dict__``. The upstream ``Updater`` class dynamically assigns the
private ``__polling_cleanup_cb`` attribute, which now raises an ``AttributeError``.
Additionally, classes with ``__slots__`` cannot be used with weak references,
which causes issues in ``JobQueue.set_application()``.

This module patches both issues.
"""
from __future__ import annotations

from typing import Any, Optional

_patch_completed = False


def patch_telegram_weakrefs() -> bool:
    """
    Patch JobQueue to avoid weak reference issues with Application objects.
    
    Returns True if the patch was applied, False otherwise.
    """
    try:
        from telegram.ext import JobQueue
    except Exception as exc:
        print(f"[Patch] ⚠️ JobQueue import failed; skipping weakref patch: {exc}")
        return False
    
    # Check if already patched
    if hasattr(JobQueue, '_patched_weakref'):
        return False
    
    # Create a weakref-like wrapper class
    class WeakRefWrapper:
        """Wrapper that mimics weakref.ref() behavior but stores a strong reference."""
        def __init__(self, obj):
            self._obj = obj
        
        def __call__(self):
            """Return the stored object (mimics weakref.ref()() behavior)."""
            return self._obj
        
        def __bool__(self):
            """Return True if object exists (always True for our wrapper)."""
            return self._obj is not None
    
    # Patch set_application to use wrapper instead of weakref
    original_set_application = JobQueue.set_application
    
    def patched_set_application(self, application):
        # Store application in a wrapper that mimics weakref behavior
        # This avoids weak reference issues while maintaining API compatibility
        wrapper = WeakRefWrapper(application)
        object.__setattr__(self, '_application', wrapper)
    
    JobQueue.set_application = patched_set_application
    JobQueue._patched_weakref = True
    
    print("[Patch] ✅ Applied JobQueue weakref compatibility fix for Python 3.13")
    return True


def patch_updater_slots() -> bool:
    """
    Ensure ``Updater`` instances can store ``__polling_cleanup_cb`` without errors
    by adding it to the class's __slots__.

    Returns True if the patch was applied, False otherwise.
    """
    global _patch_completed

    if _patch_completed:
        return False

    try:
        from telegram.ext import Updater
    except Exception as exc:  # pragma: no cover - import errors are informational
        print(f"[Patch] ⚠️ Telegram Updater import failed; skipping patch: {exc}")
        return False

    attr_name = "_Updater__polling_cleanup_cb"

    # Check if already patched
    if hasattr(Updater, attr_name) and attr_name in getattr(Updater, '__slots__', []):
        _patch_completed = True
        return False

    # Use a property descriptor with a regular dict (using id() as key)
    # This avoids weak reference issues with __slots__ classes
    # Note: Slight memory leak risk, but acceptable for bot applications
    _cleanup_registry: dict[int, Optional[Any]] = {}
    
    def _get_cleanup_cb(self: Any) -> Optional[Any]:
        return _cleanup_registry.get(id(self))
    
    def _set_cleanup_cb(self: Any, value: Optional[Any]) -> None:
        if value is None:
            _cleanup_registry.pop(id(self), None)
        else:
            _cleanup_registry[id(self)] = value
    
    def _del_cleanup_cb(self: Any) -> None:
        _cleanup_registry.pop(id(self), None)
    
    # Install the property descriptor
    setattr(
        Updater,
        attr_name,
        property(_get_cleanup_cb, _set_cleanup_cb, _del_cleanup_cb),
    )

    _patch_completed = True
    print("[Patch] ✅ Applied Updater compatibility fix for Python 3.13")
    return True


def patch_all() -> bool:
    """
    Apply all compatibility patches for Python 3.13.
    
    Returns True if at least one patch was applied, False otherwise.
    """
    updater_patched = patch_updater_slots()
    jobqueue_patched = patch_telegram_weakrefs()
    return updater_patched or jobqueue_patched


__all__ = ["patch_updater_slots", "patch_telegram_weakrefs", "patch_all"]
