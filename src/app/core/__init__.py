"""Pure position core: no filesystem, no clock, no framework, no presentation.

Everything in this package is deterministic and independently testable.
Nothing here imports from ``infrastructure`` or ``config``; the dependency
arrow only ever points inward.

Import the modules directly (``app.core.models``, ``app.core.periods``,
``app.core.profiles``, ``app.core.calculations``) rather than re-exporting
them here, so the package has one obvious public surface.
"""
