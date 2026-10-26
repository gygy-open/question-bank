"""Subscript/superscript element mover.

Ported from the Ruby mathtype_to_mathml gem's mover.rb. MathType stores
subscripts and superscripts as standalone templates (tmSUB, tmSUP, tmSUBSUP).
MathML requires them to wrap around a base element. This module moves the
base character/template into the script template's slot.

Handles the same edge cases as the Ruby version:
- Fenced expressions (parentheses, brackets)
- Empty preceding/following siblings (isotope notation)
- Inverted embellishments (char → embell to embell → char)
"""

from lxml import etree


PARENS_SELECTORS = {
    "tmPARENS", "tmBRACK", "tmBRACE", "tmOBRACK",
    "tmOBRACE", "tmHBRACK", "tmHBRACE",
}
SUBSUP_SELECTORS = {"tmSUP", "tmSUB", "tmSUBSUP"}
OPEN_PAREN_CODES = {"0x0028", "0x005B", "0x007B"}

# MT spacing/invisible characters that should be transparent to the
# sub/sup base-selection logic. When these appear between a script
# template and its intended base (common in isotope notation like
# 12-C-16-O), the mover should skip them rather than treating them as
# the base element.
_MT_SPACE_CODES = {
    "0xEF01",  # MT Zero Space      -> U+200B ZERO WIDTH SPACE
    "0xEF02",  # MT Thin Space      -> U+2009 THIN SPACE
    "0xEF03",  # MT Medium Space    -> U+205F MEDIUM MATHEMATICAL SPACE
    "0xEF04",  # MT Thick Space     -> U+2009 (thick)
    "0xEF05",  # MT Em Space        -> U+2003 EM SPACE
    "0xEF06",  # MT 2 Em Space      -> U+2003 U+2003
    "0xEF08",  # MT 1 Point Space   -> U+200A HAIR SPACE
}

# Characters that should not act as base elements for sub/sup
# templates. These are separators/delimiters that appear between
# formula groups (e.g., Chinese comma in multi-isotope formulas
# like 12-C-16-O、13-C-16-O).
_NON_BASE_CODES = {
    "0x3001",  # CJK IDEOGRAPHIC COMMA (、)
    "0x3002",  # CJK IDEOGRAPHIC FULL STOP (。)
}
CLOSE_PAREN_CODES = {"0x0029", "0x005D", "0x007D"}
OPEN_CLOSE_PAIRS = {
    "0x0028": "0x0029",
    "0x005B": "0x005D",
    "0x007B": "0x007D",
}


def move(xml_root: etree._Element) -> None:
    """Apply all mover transformations to the MTEF XML tree."""
    _last_preceding[id(xml_root)] = []
    # Strip MT spacing characters (layout artifacts) before mover runs
    # so they don't interfere with base selection or appear as orphans.
    _strip_mt_spaces(xml_root)
    _move_following_subsup(xml_root)
    _move_preceding_subsup(xml_root)
    _invert_char_embell(xml_root)
    _last_preceding.pop(id(xml_root), None)


def _move_following_subsup(root: etree._Element) -> None:
    """Move base elements into following-style sub/sup templates.

    For tmSUP/tmSUB/tmSUBSUP without tvSU_PRECEDES, the base character
    normally precedes the template in the XML tree. We look for preceding
    siblings and move the last one into the template.
    """
    for el in _find_subsup_templates(root, include_precedes=False):
        siblings = _get_new_preceding_siblings(el)

        # Filter out unsuitable base candidates (spacing chars, populated
        # sub/sup templates) that are layout artifacts, not real content.
        siblings = _filter_base_candidates(siblings)

        if not siblings:
            # No suitable preceding sibling: try following siblings
            # (isotope notation workaround: base follows the template).
            # When the base follows the template, this is semantically a
            # "precedes" superscript (e.g. nuclear isotope notation 12-C).
            # Mark the template with tvSU_PRECEDES so the XSLT generates
            # <mmultiscripts> with <mprescripts/> for left-side placement.
            _add_precedes_variation(el)
            following = _filter_base_candidates(_get_following_siblings(el))
            if not following:
                continue
            node = etree.Element("slot")
            _move_into(following[0], node)
            _insert_before_slot(el, node)
            continue

        node = etree.Element("slot")

        base = siblings[-1]
        if _has_close_paren(base):
            siblings_rev = list(reversed(siblings))
            keep = []
            for s in siblings_rev:
                if s.getnext() is not None and _has_open_paren(s.getnext()):
                    break
                keep.insert(0, s)
            _move_paren(keep, node)
        elif _is_parens_template(base):
            base.getparent().remove(base)
            node.append(base)
        else:
            base.getparent().remove(base)
            node.append(base)

        _insert_before_slot(el, node)


def _move_preceding_subsup(root: etree._Element) -> None:
    """Move base elements into preceding-style sub/sup templates.

    For tmSUP/tmSUB/tmSUBSUP with tvSU_PRECEDES, the base character
    follows the template. We look for following siblings and move
    the first one into the template.
    """
    for el in _find_subsup_templates(root, include_precedes=True):
        siblings = _get_following_siblings(el)

        # Filter out unsuitable base candidates
        siblings = _filter_base_candidates(siblings)

        if not siblings:
            preceding = _filter_base_candidates(
                _get_new_preceding_siblings(el))
            if not preceding:
                continue
            node = etree.Element("slot")
            _move_into(preceding[-1], node)
            _insert_before_slot(el, node)
            continue

        node = etree.Element("slot")

        base = siblings[0]
        if _has_open_paren(base):
            keep = []
            for s in siblings:
                keep.append(s)
                if s.getnext() is not None and _has_close_paren(s.getnext()):
                    break
            _move_paren(keep, node)
        elif _is_parens_template(base):
            base.getparent().remove(base)
            node.append(base)
        else:
            base.getparent().remove(base)
            node.append(base)

        _insert_before_slot(el, node)


def _invert_char_embell(root: etree._Element) -> None:
    """Invert char → embell to embell → char.

    The XSLT expects <embell><char/></embell>, but MathType stores
    <char><embell/></char>.
    """
    for char_el in root.xpath("//char[embell]"):
        embell = char_el.find("embell")
        if embell is None:
            continue
        char_el.remove(embell)
        clone = etree.Element("char")
        for child in list(char_el):
            char_el.remove(child)
            clone.append(child)
        clone.text = char_el.text
        clone.tail = char_el.tail
        for attr_key, attr_val in char_el.attrib.items():
            clone.set(attr_key, attr_val)
        embell.append(clone)
        parent = char_el.getparent()
        if parent is not None:
            idx = list(parent).index(char_el)
            parent.remove(char_el)
            parent.insert(idx, embell)


# ── helpers ──────────────────────────────────────────────

_last_preceding = {}

def _get_new_preceding_siblings(el) -> list:
    """Get preceding siblings (tmpl or char) that haven't been consumed yet."""
    all_prev = el.xpath("preceding-sibling::tmpl | preceding-sibling::char")
    key = id(el.getroottree().getroot())
    last = _last_preceding.get(key, [])
    new = [s for s in all_prev if s not in last]
    _last_preceding[key] = all_prev
    return new


def _get_following_siblings(el) -> list:
    """Get following siblings (tmpl or char)."""
    return el.xpath("following-sibling::tmpl | following-sibling::char")


def _find_subsup_templates(root, include_precedes=False):
    """Find all sub/sup template elements."""
    results = []
    for el in root.iter("tmpl"):
        sel = (el.findtext("selector") or "")
        if sel not in SUBSUP_SELECTORS:
            continue
        variations = [v.text for v in el.findall("variation") if v.text]
        has_precedes = "tvSU_PRECEDES" in variations
        if has_precedes == include_precedes:
            results.append(el)
    return results


def _add_precedes_variation(el) -> None:
    """Add tvSU_PRECEDES variation to a sub/sup template.

    Called when the base is taken from following siblings (the superscript
    appears before the base, as in nuclear isotope notation 12-C).
    """
    existing = {v.text for v in el.findall("variation") if v.text}
    if "tvSU_PRECEDES" not in existing:
        var_el = etree.Element("variation")
        var_el.text = "tvSU_PRECEDES"
        el.append(var_el)


def _is_mt_space_char(el) -> bool:
    """Check if element is an MT spacing/invisible character.

    These characters are used for layout spacing in MathType and should
    not be treated as meaningful base elements for sub/sup templates.
    """
    if el.tag != "char":
        return False
    code = el.findtext("mt_code_value") or ""
    return code in _MT_SPACE_CODES


def _is_populated_subsup(el) -> bool:
    """Check if element is a sub/sup template that already has its base filled.

    After the mover processes a tmSUP/tmSUB/tmSUBSUP template, it contains
    the base element in its first slot. Such templates should not be treated
    as base candidates for other sub/sup templates.
    """
    if el.tag != "tmpl":
        return False
    sel = el.findtext("selector") or ""
    if sel not in SUBSUP_SELECTORS:
        return False
    # Check if the template already has a non-empty slot[0] (the base)
    slots = el.findall("slot")
    if not slots:
        return False
    # If the first slot has children, it's been populated
    first_slot = slots[0]
    return len(list(first_slot)) > 0


def _strip_mt_spaces(xml_root: etree._Element) -> None:
    """Remove MT zero-width spaces from the XML tree.

    The MT Zero Space (0xEF01 / U+200B) is an invisible layout artifact
    that should not affect the semantic structure. Other MT spacing chars
    (thin space, em space, etc.) provide visible spacing and are kept.
    """
    for char_el in list(xml_root.iter("char")):
        code = char_el.findtext("mt_code_value") or ""
        if code == "0xEF01":
            parent = char_el.getparent()
            if parent is not None:
                parent.remove(char_el)


def _filter_base_candidates(siblings: list) -> list:
    """Filter out elements that are not suitable base candidates.

    Removes:
    - MT spacing/invisible characters (layout artifacts)
    - Already-populated sub/sup templates (already consumed their base)
    - Delimiter/separator characters that separate formula groups
    """
    return [s for s in siblings
            if not _is_mt_space_char(s)
            and not _is_populated_subsup(s)
            and not _is_non_base_char(s)]


def _is_non_base_char(el) -> bool:
    """Check if element is a delimiter/separator that shouldn't be a base."""
    if el.tag != "char":
        return False
    code = el.findtext("mt_code_value") or ""
    return code in _NON_BASE_CODES


def _has_open_paren(el) -> bool:
    """Check if element is an opening parenthesis/bracket/brace."""
    code = el.findtext("mt_code_value") or ""
    return code in OPEN_PAREN_CODES


def _has_close_paren(el) -> bool:
    """Check if element is a closing parenthesis/bracket/brace."""
    code = el.findtext("mt_code_value") or ""
    return code in CLOSE_PAREN_CODES


def _is_parens_template(el) -> bool:
    """Check if element is a fence template."""
    sel = el.findtext("selector") or ""
    return sel in PARENS_SELECTORS


def _move_into(src, dst) -> None:
    """Move element from its parent into dst."""
    parent = src.getparent()
    if parent is not None:
        parent.remove(src)
    dst.append(src)


def _move_paren(siblings, node) -> None:
    """Move parenthesized sibling group into node."""
    if not siblings:
        return
    open_code = siblings[0].findtext("mt_code_value") or ""
    close_code = OPEN_CLOSE_PAIRS.get(open_code)
    if close_code is None:
        return
    for s in siblings:
        _move_into(s, node)
        if (s.findtext("mt_code_value") or "") == close_code:
            break


def _insert_before_slot(el, node) -> None:
    """Insert node before the first <slot> child of el."""
    first_slot = el.find("slot")
    if first_slot is not None:
        idx = list(el).index(first_slot)
        el.insert(idx, node)
    else:
        el.append(node)
