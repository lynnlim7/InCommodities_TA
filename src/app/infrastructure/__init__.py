"""Adapters for the outside world: reading trades, and reporting what could not be read.

Depends on ``app.core``; nothing in ``app.core`` depends on this package.

Import the modules directly (``app.infrastructure.csv_repository``,
``app.infrastructure.schemas``, ``app.infrastructure.errors``) rather than
re-exporting them here, so the package has one obvious public surface.
"""
