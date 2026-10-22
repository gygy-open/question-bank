"""Direct MathML builder from parsed MTEF record tree.

Bypasses the MTEF XML → XSLT path entirely. Builds MathML elements
directly from the semantic record structure, which is simpler and
more robust than trying to match the Ruby gem's XML format exactly.
"""

from lxml import etree

MATHML_NS = "http://www.w3.org/1998/Math/MathML"

# Unicode mappings for known MathType code points→Unicode code points
# (from the char replacer's REPLACEMENTS and the gem's char.xsl)
def _mt_code_to_char(mt_code_str: str) -> str:
    """Convert MathType 0xXXXX code to Unicode character."""
    code = int(mt_code_str, 16)
    # Private Use Area mappings (MathType-specific)
    pua_map = {
        0xE901: 0x2A72, 0xE902: 0x2A71, 0xE903: 0x2A26, 0xE904: 0x2A24,
        0xE90B: 0x2287, 0xE90C: 0x2286, 0xE922: 0x22DA, 0xE92D: 0x22DB,
        0xE932: 0x2272, 0xE933: 0x2273, 0xE98F: 0x00B7,
    }
    if code in pua_map:
        return chr(pua_map[code])
    # Standard Unicode
    try:
        return chr(code)
    except ValueError:
        return "?"


def _move_subsup_bases(tree: dict) -> None:
    """Move base objects into sub/sup templates in the record tree.

    Single-pass, right-to-left processing within each list so that
    indices remain valid after removals.
    """
    def _process(objects: list) -> None:
        i = len(objects) - 1
        while i >= 0:
            obj = objects[i]
            # Recurse first (bottom-up)
            for child_list_key in ("subobjects", "objects"):
                child_list = obj.get(child_list_key, [])
                if child_list:
                    _process(child_list)
            # Then process this level
            if obj.get("type") == "tmpl" and obj.get("selector") in ("tmSUB", "tmSUP", "tmSUBSUP"):
                if i > 0:
                    prev = objects[i - 1]
                    prev_t = prev.get("type", "")
                    if prev_t not in ("size", "end", "full", "sub", "sub2", "sym", "subsym"):
                        subobjects = obj.get("subobjects", [])
                        base_line = {"type": "line", "options": 0, "objects": [prev]}
                        insert_pos = 0
                        for j, so in enumerate(subobjects):
                            so_t = so.get("type", "")
                            if so_t in ("size", "sub", "sub2", "sym", "subsym", "full"):
                                insert_pos = j + 1
                            elif so_t == "line":
                                break
                        subobjects.insert(insert_pos, base_line)
                        objects.pop(i - 1)
            i -= 1

    eq = tree.get("equation")
    if eq:
        _process(eq.get("objects", []))


def build_mathml(equation_data: dict) -> str | None:
    """Build MathML string directly from parsed equation data."""
    # Pre-process: move sub/sup bases into templates
    _move_subsup_bases(equation_data)

    math_el = etree.Element(f"{{{MATHML_NS}}}math")
    math_el.set("display", "block")

    mrow = etree.SubElement(math_el, f"{{{MATHML_NS}}}mrow")

    eq = equation_data.get("equation")
    if eq:
        _build_objects(mrow, eq.get("objects", []))

    # Remove namespace prefixes for clean output
    out = etree.tostring(math_el, encoding="unicode")
    # lxml uses ns0: prefix — replace with default namespace
    out = out.replace('ns0:', '').replace(':ns0', '')
    out = out.replace(f' xmlns:ns0="{MATHML_NS}"', f' xmlns="{MATHML_NS}"')
    return out


def _build_objects(parent, objects: list) -> None:
    """Build MathML for a sequence of objects."""
    for obj in objects:
        _build_object(parent, obj)


def _build_object(parent, obj: dict) -> None:
    """Build MathML for a single parsed object."""
    t = obj.get("type", "")

    if t == "char":
        _build_char_mathml(parent, obj)
    elif t == "tmpl":
        _build_tmpl_mathml(parent, obj)
    elif t == "line":
        _build_line_mathml(parent, obj)
    elif t in ("end",):
        pass
    elif t in ("full", "sub", "sub2", "sym", "subsym"):
        pass  # Size markers don't produce MathML


def _build_char_mathml(parent, obj: dict) -> None:
    """Build MathML token element for a character."""
    mt = obj.get("mt_code_value", "0x0000")
    ch = _mt_code_to_char(mt)
    var = obj.get("variation", "mathmode")

    if var == "textmode":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mtext")
    elif ch.isdigit() or ch in ".+-":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mn")
    elif ch in "()[]{}|,;:!?*/=<>≤≥±×÷∑∏∫√∞∂∇∈∉⊂⊃⊆⊇∪∩∧∨¬→←↔⇒⇐⇔°′″∼≈≅≠≡∝∠⊥":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mo")
    else:
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mi")
    el.text = ch


def _build_tmpl_mathml(parent, obj: dict) -> None:
    """Build MathML for a template. Handles all 38 MTEF template types."""
    sel = obj.get("selector", "")
    subobjects = obj.get("subobjects", [])
    variations = obj.get("variation", [])

    raw_slots = _split_into_slots(subobjects)
    _SIZE_TYPES = {"full", "sub", "sub2", "sym", "subsym", "size"}
    slots = [s for s in raw_slots if not (len(s) == 1 and s[0].get("type") in _SIZE_TYPES)]

    # ── Fractions ────────────────────────────────────
    if sel == "tmFRACT":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mfrac")
        if "tvFR_SLASH" in variations:
            el.set("bevelled", "true")
        _build_slot_mathml(el, slots[0] if len(slots) >= 1 else [])
        _build_slot_mathml(el, slots[1] if len(slots) >= 2 else [])
        return

    # ── Scripts ──────────────────────────────────────
    if sel == "tmSUB":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}msub")
        _build_slot_mathml(el, slots[0] if len(slots) >= 1 else [])
        _build_slot_mathml(el, slots[1] if len(slots) >= 2 else [])
        return
    if sel == "tmSUP":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}msup")
        _build_slot_mathml(el, slots[0] if len(slots) >= 1 else [])
        _build_slot_mathml(el, slots[1] if len(slots) >= 2 else [])
        return
    if sel == "tmSUBSUP":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}msubsup")
        _build_slot_mathml(el, slots[0] if len(slots) >= 1 else [])
        _build_slot_mathml(el, slots[1] if len(slots) >= 2 else [])
        _build_slot_mathml(el, slots[2] if len(slots) >= 3 else [])
        return

    # ── Roots ────────────────────────────────────────
    if sel == "tmROOT":
        if "tvROOT_NTH" in variations and len(slots) >= 2:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}mroot")
            _build_slot_mathml(el, slots[0])
            _build_slot_mathml(el, slots[1])
        else:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}msqrt")
            _build_slot_mathml(el, slots[0] if slots else [])
        return

    # ── Fences (parentheses, brackets, braces, etc.) ─
    fence_map = {"tmPAREN": "(", "tmBRACK": "[", "tmBRACE": "{",
                 "tmANGLE": "⟨", "tmBAR": "|", "tmDBAR": "‖",
                 "tmFLOOR": "⌊", "tmCEILING": "⌈", "tmOBRACK": "〚"}
    if sel in fence_map:
        if len(slots) >= 1:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}mrow")
            mo_l = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
            mo_l.text = fence_map[sel]
            _build_slot_mathml(el, slots[0])
            # Right fence depends on template options
            close_map = {"tmPAREN": ")", "tmBRACK": "]", "tmBRACE": "}",
                         "tmANGLE": "⟩", "tmBAR": "|", "tmDBAR": "‖",
                         "tmFLOOR": "⌋", "tmCEILING": "⌉", "tmOBRACK": "〛"}
            mo_r = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
            mo_r.text = close_map.get(sel, ")")
        return

    # ── Over/Under bars ──────────────────────────────
    if sel in ("tmOBAR", "tmUBAR"):
        bar_char = "¯" if sel == "tmOBAR" else "_"
        accent_attr = "true" if sel == "tmOBAR" else None
        if sel == "tmOBAR":
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}mover")
            if accent_attr: el.set("accent", accent_attr)
        else:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}munder")
            el.set("accentunder", "true")
        _build_slot_mathml(el, slots[0] if slots else [])
        mo = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
        mo.text = bar_char
        if "tvBAR_DOUBLE" in variations:
            # Double bar: nest another mover/munder
            pass
        return

    # ── Vectors ──────────────────────────────────────
    if sel == "tmVEC":
        arrow = "→"
        if "tvVE_LEFT" in variations: arrow = "←"
        if "tvVE_HARPOON" in variations: arrow = "⇀" if arrow == "→" else "↼"
        if "tvVE_UNDER" in variations:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}munder")
            el.set("accentunder", "true")
        else:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}mover")
            el.set("accent", "true")
        _build_slot_mathml(el, slots[0] if slots else [])
        mo = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
        mo.set("stretchy", "true")
        mo.text = arrow
        return

    # ── Hats, tildes, arcs ───────────────────────────
    accent_map = {"tmTILDE": "~", "tmHAT": "^", "tmARC": "⌢"}
    if sel in accent_map:
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mover")
        el.set("accent", "true")
        _build_slot_mathml(el, slots[0] if slots else [])
        mo = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
        mo.set("stretchy", "true")
        mo.text = accent_map[sel]
        return

    # ── Big operators (sum, product, integral, etc.) ─
    big_ops = {"tmSUM": "∑", "tmPROD": "∏", "tmCOPROD": "∐",
               "tmUNION": "⋃", "tmINTER": "⋂", "tmINTEG": "∫",
               "tmINTOP": "∫", "tmSUMOP": "∑"}
    if sel in big_ops:
        op_symbol = big_ops[sel]
        has_upper = "tvBO_UPPER" in variations
        has_lower = "tvBO_LOWER" in variations
        if has_upper and has_lower:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}munderover")
        elif has_lower:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}munder")
        elif has_upper:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}mover")
        else:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}mrow")
        mo = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
        mo.text = op_symbol
        if has_lower and has_upper:
            _build_slot_mathml(el, slots[1] if len(slots) > 1 else [])
            _build_slot_mathml(el, slots[2] if len(slots) > 2 else [])
        elif has_lower:
            _build_slot_mathml(el, slots[1] if len(slots) > 1 else [])
        elif has_upper:
            _build_slot_mathml(el, slots[0] if slots else [])
        return

    # ── Limits ───────────────────────────────────────
    if sel == "tmLIM":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}munder")
        _build_slot_mathml(el, slots[0] if len(slots) >= 1 else [])
        _build_slot_mathml(el, slots[1] if len(slots) >= 2 else [])
        return

    # ── Overstrike (cross-out) ───────────────────────
    if sel == "tmSTRIKE":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}menclose")
        notation = "horizontalstrike" if "tvST_HORIZ" in variations else "updiagonalstrike"
        el.set("notation", notation)
        _build_slot_mathml(el, slots[0] if slots else [])
        return

    # ── Box ──────────────────────────────────────────
    if sel == "tmBOX":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}menclose")
        el.set("notation", "box")
        _build_slot_mathml(el, slots[0] if slots else [])
        return

    # ── Long division ────────────────────────────────
    if sel == "tmLDIV":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}menclose")
        el.set("notation", "longdiv")
        if len(slots) >= 1:
            _build_slot_mathml(el, slots[0])
        return

    # ── Horizontal braces/brackets ───────────────────
    if sel in ("tmHBRACE", "tmHBRACK"):
        is_top = "tvHB_TOP" in variations
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mrow")
        if is_top:
            mo = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
            mo.set("stretchy", "true")
            mo.text = "⏞" if sel == "tmHBRACE" else "⎴"
        _build_slot_mathml(el, slots[0] if slots else [])
        if not is_top:
            mo = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
            mo.set("stretchy", "true")
            mo.text = "⏟" if sel == "tmHBRACE" else "⎵"
        return

    # ── Arrows ───────────────────────────────────────
    if sel == "tmARROW":
        _build_slot_mathml(parent, slots[0] if slots else [])
        mo = etree.SubElement(parent, f"{{{MATHML_NS}}}mo")
        mo.text = "→"
        _build_slot_mathml(parent, slots[1] if len(slots) > 1 else [])
        return

    # ── Dirac bra-ket ────────────────────────────────
    if sel == "tmDIRAC":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mrow")
        left = "tvDI_LEFT" in variations
        right = "tvDI_RIGHT" in variations
        if left:
            mo = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
            mo.text = "⟨"
        _build_slot_mathml(el, slots[0] if slots else [])
        if right:
            mo = etree.SubElement(el, f"{{{MATHML_NS}}}mo")
            mo.text = "|"
        return

    # ── Matrix ───────────────────────────────────────
    if sel == "tmMATRIX":
        rows = []
        current_row = []
        for so in subobjects:
            t = so.get("type", "")
            if t == "line":
                current_row.append(so)
                rows.append(current_row)
                current_row = []
            elif t in ("end",):
                if current_row:
                    rows.append(current_row)
                break
        if rows:
            el = etree.SubElement(parent, f"{{{MATHML_NS}}}mtable")
            for row in rows:
                mtr = etree.SubElement(el, f"{{{MATHML_NS}}}mtr")
                for cell in row:
                    mtd = etree.SubElement(mtr, f"{{{MATHML_NS}}}mtd")
                    _build_objects(mtd, cell.get("objects", []))
        return

    # ── Pile (vertical stack) ────────────────────────
    if sel == "tmPILE":
        el = etree.SubElement(parent, f"{{{MATHML_NS}}}mtable")
        lines = obj.get("lines", [])
        for line in lines:
            mtr = etree.SubElement(el, f"{{{MATHML_NS}}}mtr")
            mtd = etree.SubElement(mtr, f"{{{MATHML_NS}}}mtd")
            for o in line.get("objects", []):
                _build_object(mtd, o)
        return

    # ── Fallback ─────────────────────────────────────
    for slot in slots:
        _build_slot_mathml(parent, slot)


def _build_line_mathml(parent, obj: dict) -> None:
    """Build MathML for a LINE (slot) — wrap in mrow."""
    objs = obj.get("objects", [])
    if len(objs) > 1:
        mrow = etree.SubElement(parent, f"{{{MATHML_NS}}}mrow")
        _build_objects(mrow, objs)
    else:
        _build_objects(parent, objs)


def _build_slot_mathml(parent, slot_objects: list) -> None:
    """Build MathML for a template slot's contents."""
    # Filter out non-content (size/end markers)
    content = []
    for obj in slot_objects:
        t = obj.get("type", "")
        if t in ("end", "full", "sub", "sub2", "sym", "subsym", "size"):
            continue
        if t == "line":
            # Recurse into line's objects
            for o in obj.get("objects", []):
                content.append(o)
        else:
            content.append(obj)

    if len(content) == 0:
        etree.SubElement(parent, f"{{{MATHML_NS}}}mrow")
    elif len(content) == 1 and content[0].get("type") == "char":
        _build_char_mathml(parent, content[0])
    else:
        mrow = etree.SubElement(parent, f"{{{MATHML_NS}}}mrow")
        for o in content:
            _build_object(mrow, o)


def _split_into_slots(subobjects: list) -> list[list]:
    """Split template subobjects into slots at size markers.

    Each contiguous group between size markers (FULL, SUB, etc.)
    forms one slot. Size markers become empty slots.
    """
    slots = []
    current = []

    for obj in subobjects:
        t = obj.get("type", "")
        size_type = obj.get("size_type") if t == "size" else None

        is_size_marker = (t in ("full", "sub", "sub2", "sym", "subsym")
                          or (t == "size" and size_type is not None))

        if is_size_marker:
            if current:
                slots.append(current)
                current = []
            slots.append([obj])
        elif t == "line":
            # Each LINE in a template is its own slot.
            # Non-empty LINEs with content are content slots;
            # NULL LINEs (opts=1) with no objects are empty optional slots.
            if obj.get("objects") or obj.get("options", 0) == 0:
                if current:
                    slots.append(current)
                    current = []
                slots.append([obj])
            # else: NULL LINE with no objects — skip
        elif t == "end":
            if current:
                slots.append(current)
            break
        else:
            current.append(obj)

    if current:
        slots.append(current)

    return slots
