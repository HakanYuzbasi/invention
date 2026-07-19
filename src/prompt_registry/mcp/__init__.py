"""Read-only MCP stdio server for the prompt registry.

This package is an ACCESS LAYER ONLY. It exposes search/inspect/render over
the registry through the composition-only ReadOnlyRegistry facade and a
read-only SQLite connection. It contains no mutation, evaluation, or model
execution code by construction — see tests/test_mcp_readonly_invariant.py.

The MCP SDK is an optional extra: `pip install 'prompt-registry[mcp]'`.
This module deliberately imports nothing from the SDK so it can always be
imported for diagnostics.
"""
