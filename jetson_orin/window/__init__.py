"""Benchmark window (locked clocks + fan) and page-cache clear for the AGX Orin.

Implements the shared machine-CLI contract (lobes-cli
``docs/contracts/machine-cli-window.md``) for ``orin window``, ``orin drop-caches``
and ``orin grant-permissions``. The thor CLI's version is *cited*, not imported:
the design mirrors it (``jetson_clocks --store/--restore`` under
``${XDG_STATE_HOME:-~/.local/state}/orin/``) with Orin specifics (nvpmodel mode
names such as ``MAXN``; a GPU devfreq node under ``17000000.gpu``).
"""
