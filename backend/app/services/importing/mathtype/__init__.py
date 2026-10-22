"""Pure-Python MTEF (MathType Equation Format) to MathML converter.

Replaces the Ruby mathtype_to_mathml_plus gem with native Python.
Supports MTEF v3 (Equation Editor 3.x) and v5 (MathType 4.0+).

Usage:
    from app.services.importing.mathtype import mtef_to_mathml

    mathml = mtef_to_mathml(ole_bytes)
    # => "<math xmlns='http://www.w3.org/1998/Math/MathML'>...</math>"
"""

from .mathml import mtef_to_mathml
