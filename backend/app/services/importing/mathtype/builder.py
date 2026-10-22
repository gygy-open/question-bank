"""MTEF XML builder — exact replica of Ruby Mathtype::Converter#process.

Produces XML matching the Nokogiri builder output that the XSLT expects.
The structure mirrors the gem's RECORD_NAMES mapping for both v3 and v5.

V5 RECORD_NAMES:
  0:end 1:slot 2:char 3:tmpl 4:pile 5:matrix 6:embell 7:ruler
  8:font_style_def 9:size 10:full 11:sub 12:sub2 13:sym 14:subsym
  15:color 16:color_def 17:font_def 18:eqn_prefs 19:encoding_def

V3 RECORD_NAMES:
  0:end 1:slot 2:char 3:tmpl 4:pile 5:matrix 6:embell 7:ruler
  8:font 9:size 10:full 11:sub 12:sub2 13:sym 14:subsym
"""

from lxml import etree


def build_mtef_xml(equation_data: dict) -> etree._Element:
    """Build the MTEF XML tree from parsed equation data.

    The output must match the Ruby gem's Nokogiri XML exactly so the
    XSLT transformation produces correct MathML.
    """
    root = etree.Element("root")
    mtef = etree.SubElement(root, "mtef")
    ver = equation_data.get("mtef_version", 5)

    # Stream header fields
    _leaf(mtef, "mtef_version", str(ver))
    _leaf(mtef, "platform", "1")
    _leaf(mtef, "product", "0")
    _leaf(mtef, "product_version", "6")
    _leaf(mtef, "product_subversion", "7")
    _leaf(mtef, "application_key", "DSMT6")
    _leaf(mtef, "equation_options", "block")

    # Encoding definitions (v5 only)
    for enc in equation_data.get("encoding_defs", []):
        el = etree.SubElement(mtef, "encoding_def")
        _leaf(el, "name", enc.get("name", ""))

    # Font definitions (v5) or FONT records (v3)
    for font in equation_data.get("font_defs", []):
        el = etree.SubElement(mtef, "font_def")
        _leaf(el, "enc_def_index", str(font.get("enc_def_index", 0)))
        _leaf(el, "font_name", font.get("font_name", ""))

    # Equation preferences (v5)
    prefs = equation_data.get("eqn_prefs")
    if prefs:
        _build_eqn_prefs(mtef, prefs)

    # Main equation content
    if ver == 3:
        # V3: records are direct children of <mtef>, no FULL/slot wrapper
        for obj in equation_data.get("records", []):
            _build_record(mtef, obj, 3)
    else:
        eq = equation_data.get("equation")
        if eq:
            _build_equation_body(mtef, eq, ver)

    etree.SubElement(mtef, "end")
    return root


def _build_equation_body(parent, eq, ver):
    """Build the equation body: <full/> + <slot>...</slot> + <end/>."""
    objects = eq.get("objects", [])
    if len(objects) == 1 and objects[0].get("type") == "pile":
        _build_record(parent, objects[0], ver)
        return

    etree.SubElement(parent, "full")
    slot = etree.SubElement(parent, "slot")
    _leaf(slot, "options", str(eq.get("options", 0)))

    for obj in objects:
        _build_record(slot, obj, ver)

    etree.SubElement(slot, "end")


def _build_record(parent, obj, ver):
    """Build a single record element (char, tmpl, slot, etc.)."""
    t = obj.get("type", "")

    if t == "char":
        _build_char(parent, obj)
    elif t == "tmpl":
        _build_tmpl(parent, obj, ver)
    elif t == "line":
        _build_line(parent, obj, ver)
    elif t == "pile":
        _build_pile(parent, obj, ver)
    elif t == "matrix":
        _build_matrix(parent, obj, ver)
    elif t == "embell":
        el = etree.SubElement(parent, "embell")
        _leaf(el, "options", str(obj.get("options", 0)))
        _leaf(el, "embell", obj.get("embell", ""))
    elif t == "ruler":
        _build_ruler(parent, obj)
    elif t == "size":
        _build_size(parent, obj)
    elif t == "color":
        el = etree.SubElement(parent, "color")
        _leaf(el, "color_def_index", str(obj.get("color_def_index", 0)))
    elif t == "color_def":
        _build_color_def(parent, obj)
    elif t == "font_style_def":
        el = etree.SubElement(parent, "font_style_def")
        _leaf(el, "font_def_index", str(obj.get("font_def_index", 0)))
        _leaf(el, "char_style", str(obj.get("font_style", 0)))
    elif t == "font":
        el = etree.SubElement(parent, "font")
        _leaf(el, "typeface", str(obj.get("typeface", 0)))
        _leaf(el, "style", str(obj.get("style", 0)))
        _leaf(el, "name", obj.get("name", ""))
    elif t == "end":
        etree.SubElement(parent, "end")
    elif t in ("full", "sub", "sub2", "sym", "subsym"):
        etree.SubElement(parent, t)
    elif t == "nudge":
        _build_nudge(parent, obj)


def _build_char(parent, obj):
    """<char><typeface>N</typeface><mt_code_value>0xNNNN</mt_code_value>...</char>"""
    el = etree.SubElement(parent, "char")
    if "typeface" in obj:
        _leaf(el, "typeface", str(obj["typeface"]))
    if "mt_code_value" in obj:
        _leaf(el, "mt_code_value", obj["mt_code_value"])
    if "options" in obj:
        _leaf(el, "options", str(obj["options"]))
    if "variation" in obj:
        _leaf(el, "variation", obj["variation"])
    if "nudge" in obj:
        _build_nudge(el, obj["nudge"])
    if "font_position" in obj:
        _leaf(el, "font_position", str(obj["font_position"]))
    for emb in obj.get("embellishment_list", []):
        _build_record(el, emb, 5)


def _build_tmpl(parent, obj, ver):
    """<tmpl><selector>...</selector>...<slot>...</slot>...</tmpl>"""
    el = etree.SubElement(parent, "tmpl")
    if "options" in obj:
        _leaf(el, "options", str(obj["options"]))
    if "nudge" in obj:
        _build_nudge(el, obj["nudge"])
    if "selector" in obj:
        _leaf(el, "selector", obj["selector"])
    if "variation" in obj:
        vars_list = obj["variation"] if isinstance(obj["variation"], list) else [obj["variation"]]
        for v in vars_list:
            if v:
                _leaf(el, "variation", v)
    if "template_specific_options" in obj:
        _leaf(el, "template_specific_options", str(obj["template_specific_options"]))

    # Subobjects: split into slots at size markers
    subobjects = obj.get("subobjects", [])
    _build_template_slots(el, subobjects, ver)


def _build_template_slots(tmpl_el, subobjects, ver):
    """Build <slot> elements from template subobjects.

    Objects between size markers (full/sub/sub2/sym/subsym) form a slot.
    Size markers themselves become direct children (<full/>, <sub/>, etc.).
    The final END marker closes the template.
    """
    current_slot = []
    selector = tmpl_el.findtext("selector") or ""
    variations = {v.text for v in tmpl_el.findall("variation") if v.text}
    direct_pile_seen = False

    # Non-content record types that are direct template children, not slot content
    _META_TYPES = {"color", "color_def", "font_style_def", "font_def",
                   "encoding_def", "eqn_prefs", "ruler", "nudge", "embell"}

    for obj in subobjects:
        t = obj.get("type", "")

        if t == "end":
            if current_slot:
                _flush_slot(tmpl_el, current_slot, ver)
                current_slot = []
            etree.SubElement(tmpl_el, "end")
            return

        if t in ("full", "sub", "sub2", "sym", "subsym") or \
           (t == "size" and obj.get("size_type") in (10, 11, 12, 13, 14)):
            if current_slot:
                _flush_slot(tmpl_el, current_slot, ver)
                current_slot = []
            _build_record(tmpl_el, obj, ver)

        elif t == "size":
            if current_slot:
                _flush_slot(tmpl_el, current_slot, ver)
                current_slot = []
            _build_record(tmpl_el, obj, ver)

        elif t in _META_TYPES:
            # Style/color/definition records are direct children of the template,
            # NOT slot content. Build them inline without affecting slot grouping.
            _build_record(tmpl_el, obj, ver)

        elif _is_trailing_single_fence_char(selector, variations, obj, current_slot, direct_pile_seen):
            continue

        elif t == "pile":
            if current_slot:
                _flush_slot(tmpl_el, current_slot, ver)
                current_slot = []
            _build_record(tmpl_el, obj, ver)
            direct_pile_seen = True

        elif t == "line":
            # LINE in template = slot
            if current_slot:
                _flush_slot(tmpl_el, current_slot, ver)
                current_slot = []
            _flush_slot(tmpl_el, [obj], ver)

        else:
            current_slot.append(obj)

    if current_slot:
        _flush_slot(tmpl_el, current_slot, ver)


def _is_trailing_single_fence_char(selector, variations, obj, current_slot, direct_pile_seen=False):
    if obj.get("type") != "char":
        return False
    if not direct_pile_seen and not any(item.get("type") in ("line", "pile") for item in current_slot):
        return False
    code = obj.get("mt_code_value")
    left_only = "tvFENCE_L" in variations and "tvFENCE_R" not in variations
    right_only = "tvFENCE_R" in variations and "tvFENCE_L" not in variations
    left_codes = {
        "tmPAREN": "0x0028",
        "tmBRACE": "0x007B",
        "tmBRACK": "0x005B",
    }
    right_codes = {
        "tmPAREN": "0x0029",
        "tmBRACE": "0x007D",
        "tmBRACK": "0x005D",
    }
    return (left_only and code == left_codes.get(selector)) or (
        right_only and code == right_codes.get(selector)
    )


def _flush_slot(tmpl_el, objects, ver):
    """Build a <slot> element from accumulated objects."""
    if not objects:
        # Empty optional slot
        slot = etree.SubElement(tmpl_el, "slot")
        _leaf(slot, "options", "1")
        return

    # If objects is [LINE], use LINE's objects directly
    if len(objects) == 1 and objects[0].get("type") == "line":
        line = objects[0]
        slot = etree.SubElement(tmpl_el, "slot")
        _leaf(slot, "options", str(line.get("options", 0)))
        for o in line.get("objects", []):
            _build_record(slot, o, ver)
        return

    slot = etree.SubElement(tmpl_el, "slot")
    _leaf(slot, "options", "0")
    for obj in objects:
        _build_record(slot, obj, ver)


def _build_line(parent, obj, ver):
    """Build LINE objects directly into parent (no slot wrapper).

    The caller is responsible for creating the <slot> element.
    This function just builds the LINE's children.
    """
    for o in obj.get("objects", []):
        _build_record(parent, o, ver)


def _build_pile(parent, obj, ver):
    """<pile> element — XSLT matches matrix.xsl templates on <pile>."""
    el = etree.SubElement(parent, "pile")
    if "options" in obj:
        _leaf(el, "options", str(obj["options"]))
    if "halign" in obj:
        _leaf(el, "halign", str(obj["halign"]))
    if "valign" in obj:
        _leaf(el, "valign", str(obj["valign"]))
    for line in obj.get("lines", []):
        if line.get("type") == "line":
            slot = etree.SubElement(el, "slot")
            _leaf(slot, "options", str(line.get("options", 0)))
            for child in line.get("objects", []):
                _build_record(slot, child, ver)
        else:
            _build_record(el, line, ver)
    etree.SubElement(el, "end")


def _build_matrix(parent, obj, ver):
    """<matrix> element — XSLT matches matrix.xsl templates on <matrix>."""
    el = etree.SubElement(parent, "matrix")
    if "options" in obj:
        _leaf(el, "options", str(obj["options"]))
    if "valign" in obj:
        _leaf(el, "valign", str(obj.get("valign", 0)))
    if "v_just" in obj:
        _leaf(el, "v_just", str(obj.get("v_just", 0)))
    if "rows" in obj:
        _leaf(el, "rows", str(obj["rows"]))
    if "cols" in obj:
        _leaf(el, "cols", str(obj["cols"]))
    for cell in obj.get("cells", []):
        if cell.get("type") == "line":
            slot = etree.SubElement(el, "slot")
            _leaf(slot, "options", str(cell.get("options", 0)))
            for child in cell.get("objects", []):
                _build_record(slot, child, ver)
        else:
            _build_record(el, cell, ver)
    etree.SubElement(el, "end")


def _build_ruler(parent, obj):
    """<ruler><n_stops>N</n_stops><stops>..."""
    el = etree.SubElement(parent, "ruler")
    _leaf(el, "n_stops", str(obj.get("n_stops", 0)))
    for stop in obj.get("stops", []):
        s = etree.SubElement(el, "stop")
        _leaf(s, "tab_stop_type", str(stop.get("tab_stop_type", 0)))
        _leaf(s, "tab_stop", str(stop.get("tab_stop", 0)))


def _build_size(parent, obj):
    """<size> or <full/> etc."""
    size_type = obj.get("size_type")
    if size_type is not None:
        names = {10: "full", 11: "sub", 12: "sub2", 13: "sym", 14: "subsym"}
        etree.SubElement(parent, names.get(size_type, "full"))
    else:
        etree.SubElement(parent, "size")


def _build_color_def(parent, obj):
    """<color_def><options>...</options><rgb>..."""
    el = etree.SubElement(parent, "color_def")
    _leaf(el, "options", str(obj.get("options", 0)))
    rgb = etree.SubElement(el, "rgb")
    _leaf(rgb, "r", str(obj.get("r", 0)))
    _leaf(rgb, "g", str(obj.get("g", 0)))
    _leaf(rgb, "b", str(obj.get("b", 0)))


def _build_nudge(parent, obj):
    """<nudge><dx>N</dx><dy>N</dy></nudge>"""
    el = etree.SubElement(parent, "nudge")
    _leaf(el, "dx", str(obj.get("dx", 0)))
    _leaf(el, "dy", str(obj.get("dy", 0)))


def _build_eqn_prefs(parent, prefs):
    """Build <eqn_prefs> with nibble-packed sizes/spaces/styles."""
    el = etree.SubElement(parent, "eqn_prefs")
    _leaf(el, "options", str(prefs.get("options", 0)))

    sizes = prefs.get("sizes", [])
    _leaf(el, "sizes_count", str(len(sizes)))
    for s in sizes:
        sz = etree.SubElement(el, "sizes")
        _leaf(sz, "unit", str(s.get("unit_nibble", 0)))
        # Value nibbles
        val = s.get("value", "")
        for ch in val:
            if ch == '.':
                _leaf(sz, "nibbles", "10")  # 0xA = decimal point
            elif ch == '-':
                _leaf(sz, "nibbles", "11")  # 0xB = minus
            else:
                _leaf(sz, "nibbles", ch)
        _leaf(sz, "nibbles", "15")  # 0xF terminator

    spaces = prefs.get("spaces", [])
    _leaf(el, "spaces_count", str(len(spaces)))
    for sp in spaces:
        sp_el = etree.SubElement(el, "spaces")
        _leaf(sp_el, "unit", str(sp.get("unit_nibble", 0)))
        val = sp.get("value", "")
        for ch in val:
            if ch == '.':
                _leaf(sp_el, "nibbles", "10")
            elif ch == '-':
                _leaf(sp_el, "nibbles", "11")
            else:
                _leaf(sp_el, "nibbles", ch)
        _leaf(sp_el, "nibbles", "15")

    styles = prefs.get("styles", [])
    _leaf(el, "styles_count", str(len(styles)))
    for st in styles:
        st_el = etree.SubElement(el, "styles")
        _leaf(st_el, "font_def", str(st.get("font_def", 0)))
        _leaf(st_el, "font_style", str(st.get("font_style", 0)))


def _leaf(parent, name, text):
    """Create a leaf element with text content."""
    el = etree.SubElement(parent, name)
    el.text = str(text) if text is not None else ""
