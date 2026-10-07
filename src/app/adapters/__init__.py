"""Adapters for the outside world: reading trades, and reporting what could not be read.

Depends on ``app.core``; nothing in ``app.core`` depends on this package.

Import the modules directly (``app.adapters.csv_repository``,
``app.adapters.csv_schema``, ``app.adapters.errors``) rather than
re-exporting them here, so the package has one obvious public surface.
"""
