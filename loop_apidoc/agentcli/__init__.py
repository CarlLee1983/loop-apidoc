"""Agent-native extraction support.

The interactive agent (driven by skills/loop-apidoc/SKILL.md) extracts sources
itself and writes inventory.json + endpoints/*.json; this package only assembles
that agent-written JSON (assemble.py), converts inventory.json into plan stage
answers (extraction.py), and preprocesses PDFs to markdown (preprocess.py).
"""
