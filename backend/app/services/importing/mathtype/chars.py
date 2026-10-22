"""Character code → MathML replacement.

Ported from the Ruby mathtype_to_mathml gem's char_replacer.rb.
Replaces <char mt_code_value='0xXXXX'/> elements with actual MathML
token elements (<mi>, <mn>, <mo>, <mtext>) based on the character's
Unicode code point and variation (mathmode/textmode).

Characters in private-use ranges (0xE000-0xF8FF) that don't have
known mappings are replaced with "Unsupported" markers, which are
later stripped by the OMML cleaner.
"""

import re
from lxml import etree

UNSUPPORTED = "Unsupported (Char)"
DEFAULT_TEXTMODE = "(Char)"
DEFAULT_MATHMODE = "<mi>(Char)</mi>"

# ── Replacement rules ─────────────────────────────────────
# Each entry: (range_start, range_end, {variation: template})
# Template uses (Char) placeholder for the actual Unicode character.
# Template uses (CharHex) placeholder for &#xXXXX; entity.

REPLACEMENTS: list[tuple] = [
    # Digits 0-9
    (0x0030, 0x0039, {"mathmode": "<mn>(Char)</mn>", "textmode": "(Char)"}),
    # Latin uppercase A-Z
    (0x0041, 0x005A, {"mathmode": "<mi>(Char)</mi>", "textmode": "(Char)"}),
    # Latin lowercase a-z
    (0x0061, 0x007A, {"mathmode": "<mi>(Char)</mi>", "textmode": "(Char)"}),

    # Basic operators
    (0x0021, 0x0021, {"mathmode": "<mo>(Char)</mo>"}),  # !
    (0x0028, 0x0029, {"mathmode": "<mo stretchy='false'>(Char)</mo>"}),  # ( )
    (0x002A, 0x002A, {"mathmode": "<mo>(Char)</mo>"}),  # *
    (0x002B, 0x002B, {"mathmode": "<mo>(Char)</mo>"}),  # +
    (0x002C, 0x002C, {"mathmode": "<mo>(Char)</mo>"}),  # ,
    (0x002D, 0x002D, {"mathmode": "<mo>(Char)</mo>"}),  # -
    (0x002E, 0x002E, {"mathmode": "<mo>(Char)</mo>"}),  # .
    (0x002F, 0x002F, {"mathmode": "<mo>(Char)</mo>"}),  # /
    (0x003A, 0x003B, {"mathmode": "<mo>(Char)</mo>"}),  # : ;
    (0x003C, 0x003E, {"mathmode": "<mo>(CharHex)</mo>"}),  # < >
    (0x003D, 0x003D, {"mathmode": "<mo>(Char)</mo>"}),  # =
    (0x005B, 0x005D, {"mathmode": "<mo stretchy='false'>(Char)</mo>"}),  # [ ]
    (0x007E, 0x007E, {"mathmode": "<mo>(Char)</mo>"}),  # ~

    # Latin-1 Supplement
    (0x00A0, 0x00BB, {"mathmode": "<mo>(CharHex)</mo>"}),
    (0x00BC, 0x00BE, {"mathmode": "<mn>(CharHex)</mn>"}),
    # Spacing modifier letters (0x02C6-0x02FF)
    (0x02C6, 0x02FF, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Combining diacritical marks
    (0x0300, 0x036F, {"mathmode": "<mo>(CharHex)</mo>"}),

    # General Punctuation
    (0x2010, 0x2027, {"mathmode": "<mo>(CharHex)</mo>"}),
    (0x2030, 0x2069, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Superscripts and Subscripts
    (0x2070, 0x209F, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Currency
    (0x20A0, 0x20CF, {"mathmode": "<mi>(CharHex)</mi>"}),

    # Combining marks for symbols
    (0x20D0, 0x20FF, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Letterlike Symbols
    (0x2100, 0x214F, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Number Forms
    (0x2150, 0x218F, {"mathmode": "<mn>(CharHex)</mn>"}),

    # Arrows
    (0x2190, 0x21FF, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Mathematical Operators
    (0x2200, 0x22FF, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Miscellaneous Technical
    (0x2300, 0x23FF, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Box Drawing, Block Elements, Geometric Shapes
    (0x2500, 0x25FF, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Miscellaneous Symbols, Dingbats
    (0x2600, 0x27BF, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Supplemental Arrows
    (0x27F0, 0x2AFF, {"mathmode": "<mo>(CharHex)</mo>"}),

    # CJK Symbols
    (0x3000, 0x303F, {"mathmode": "<mo>(CharHex)</mo>"}),

    # Spaces (various Unicode ranges)
    (0x2000, 0x200B, {"mathmode": "<mtext>(CharHex)</mtext>"}),
    (0xFEFF, 0xFEFF, {"mathmode": "<mtext>(CharHex)</mtext>"}),

    # Fraktur, Double-Struck, Script: handled via fontmaps in XSLT,
    # fall back to mi with mathvariant

    # Private Use Area — MathType specific mappings
    (0xE901, 0xE901, {"mathmode": "<mo>&#x2A72;</mo>", "textmode": "&#x2A72;"}),  # + above =
    (0xE902, 0xE902, {"mathmode": "<mo>&#x2A71;</mo>", "textmode": "&#x2A71;"}),  # + below =
    (0xE903, 0xE903, {"mathmode": "<mo>&#x2A26;</mo>", "textmode": "&#x2A26;"}),  # + above ~
    (0xE904, 0xE904, {"mathmode": "<mo>&#x2A24;</mo>", "textmode": "&#x2A24;"}),  # + below ~
    (0xE90B, 0xE90B, {"mathmode": "<mo>&#x2287;</mo>", "textmode": "&#x2287;"}),  # superset or =
    (0xE90C, 0xE90C, {"mathmode": "<mo>&#x2286;</mo>", "textmode": "&#x2286;"}),  # subset or =
    (0xE922, 0xE922, {"mathmode": "<mo>&#x22DA;</mo>", "textmode": "&#x22DA;"}),  # <= >
    (0xE92D, 0xE92D, {"mathmode": "<mo>&#x22DB;</mo>", "textmode": "&#x22DB;"}),  # >= <
    (0xE932, 0xE932, {"mathmode": "<mo>&#x2272;</mo>", "textmode": "&#x2272;"}),  # < approx
    (0xE933, 0xE933, {"mathmode": "<mo>&#x2273;</mo>", "textmode": "&#x2273;"}),  # > approx
    (0xE93A, 0xE93B, {"mathmode": "<mo>(CharHex)</mo>"}),  # precedes/succeeds or =
    (0xE98F, 0xE98F, {"mathmode": "<mo>&#x00B7;</mo>", "textmode": "&#x00B7;"}),  # middle dot
    (0xED10, 0xED13, {"mathmode": "<mo>(CharHex)</mo>", "textmode": "(CharHex)"}),  # d, e, i, j
    (0xED16, 0xED16, {"mathmode": "<mo>(CharHex)</mo>", "textmode": "(CharHex)"}),  # Capital D

    # Unsupported ranges in Private Use Area
    (0xE000, 0xE900, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xE905, 0xE90A, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xE90D, 0xE921, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xE923, 0xE923, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xE925, 0xE92C, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xE92E, 0xE931, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xE934, 0xE939, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xE93C, 0xE98E, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xE990, 0xED09, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xED14, 0xED15, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xED17, 0xEF06, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    # 0xEF01-0xEF06: MT spacing chars (Zero Space, Thin/Medium/Thick/Em/2Em Space).
    # These are transparent layout artifacts, not content. Mark UNSUPPORTED
    # so they fall through to the XSLT char.xsl which maps them correctly.
    (0xEF07, 0xEFFF, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xF034, 0xF07F, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xF0B4, 0xF0BF, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xF0CA, 0xF0FF, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
    (0xF134, 0xF8FF, {"mathmode": UNSUPPORTED, "textmode": UNSUPPORTED}),
]


def _find_replacement(mt_code: int, variation: str) -> str | None:
    """Find the replacement template for a MathType character code."""
    for start, end, templates in REPLACEMENTS:
        if start <= mt_code <= end:
            if variation in templates:
                return templates[variation]
            if variation == "textmode":
                return DEFAULT_TEXTMODE
            return templates.get("mathmode") or DEFAULT_MATHMODE
    return None


def replace(xml_root: etree._Element) -> None:
    """Replace all <char> elements with MathML token elements.

    Uses the REPLACEMENTS table and falls back to XSLT char.xsl
    handling for codes not in the table.
    """
    for char_el in list(xml_root.iter("char")):
        mt_text = char_el.findtext("mt_code_value") or ""
        if not mt_text.startswith("0x"):
            continue

        mt_code = int(mt_text[2:], 16)
        variation = char_el.findtext("variation") or "mathmode"

        replacement_tmpl = _find_replacement(mt_code, variation)
        if replacement_tmpl is None:
            continue

        if replacement_tmpl == UNSUPPORTED:
            # Leave for XSLT to handle (may produce "Unsupported" text)
            continue

        # Build replacement XML — NO namespace, since XSLT works on MTEF XML
        actual_char = chr(mt_code)
        xml_str = replacement_tmpl.replace("(Char)", actual_char)
        xml_str = xml_str.replace("(CharHex)", f"&#x{mt_code:04X};")

        try:
            replacement_node = etree.fromstring(f"<root>{xml_str}</root>")
        except etree.XMLSyntaxError:
            continue

        # Insert replacement nodes before char, then remove char
        parent = char_el.getparent()
        if parent is None:
            continue

        children = list(replacement_node)
        if children:
            # Has child elements (e.g., <mi>, <mn>, <mo>)
            idx = list(parent).index(char_el)
            for child in children:
                parent.insert(idx, child)
                idx += 1
        elif replacement_node.text is not None:
            # Plain text replacement (textmode: just the character)
            # Create a text-bearing element matching the context
            # Ruby Nokogiri does: char.replace(DocumentFragment.parse("6"))
            # which creates a text node. lxml needs an element wrapper.
            if replacement_node.text:
                mtext = etree.Element("mtext")
                mtext.text = replacement_node.text
                idx = list(parent).index(char_el)
                parent.insert(idx, mtext)
        parent.remove(char_el)
