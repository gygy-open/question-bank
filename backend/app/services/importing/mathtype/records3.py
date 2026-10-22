"""MTEF v3 (Equation Editor 3.x) binary record parser.

V3 uses bit-packed tags: bit4 options + bit4 record_type in one byte.
Only types 0-14 are defined. Options are embedded in the tag byte.
Records receive options via mandatory_parameter :_options.

Reference: records3/mtef.rb, records3/line.rb, records3/char.rb,
           records3/tmpl.rb, records3/pile.rb, records3/matrix.rb,
           records3/font.rb, records3/embell.rb
"""

from .stream import ByteStream

# ── Record type constants ─────────────────────────────────
END=0; LINE=1; CHAR=2; TMPL=3; PILE=4; MATRIX=5
EMBELL=6; RULER=7; FONT=8; SIZE=9
FULL=10; SUB=11; SUB2=12; SYM=13; SUBSYM=14

# ── V3 Option flags (from records3/mtef.rb OPTIONS) ──────
# These are in the LOW 4 bits of the tag byte
OPT_NUDGE=0x08   # xfLMOVE
OPT_EMBELL=0x01  # xfLAUTO / xfEMBELL (CHAR record)
OPT_FUNC=0x02    # xfEMBELL (CHAR record)
OPT_LINE_NULL=0x01   # xfNULL
OPT_LINE_RULER=0x02  # xfRULER
OPT_LINE_LSPACE=0x04 # xfLSPACE

# ── V3 Template selectors (from records3/tmpl.rb SELECTORS) ──
SELECTORS = {
    0:"tmANGLE",1:"tmPAREN",2:"tmBRACE",3:"tmBRACK",
    4:"tmBAR",5:"tmDBAR",6:"tmFLOOR",7:"tmCEILING",
    8:"tmINTERVAL",9:"tmINTERVAL",10:"tmINTERVAL",11:"tmINTERVAL",12:"tmINTERVAL",
    13:"tmROOT",14:"tmFRACT",
    15:"tmSCRIPT", # script — variation determines tmSUB/tmSUP/tmSUBSUP
    16:"tmUBAR",17:"tmOBAR",
    18:"tmARROW",19:"tmARROW",20:"tmARROW",
    21:"tmINTEG",22:"tmINTEG",23:"tmINTEG",24:"tmINTEG",25:"tmINTEG",26:"tmINTEG",
    27:"tmHBRACE",28:"tmHBRACE",
    29:"tmSUM",30:"tmSUM",
    31:"tmPROD",32:"tmPROD",
    33:"tmCOPROD",34:"tmCOPROD",
    35:"tmUNION",36:"tmUNION",
    37:"tmINTER",38:"tmINTER",
    39:"tmLIM",
    40:"tmLDIV",
    41:"tmFRACT",
    42:"tmINTOP",43:"tmSUMOP",
    44:"tmSCRIPT", # script — variation determines tmSUB/tmSUP/tmSUBSUP
    45:"tmDIRAC",
    46:"tmVEC",47:"tmVEC",
    48:"tmBOX",
}

# ── V3 Script selectors (selector 15 and 44) ─────────────
SCRIPT_SELECTORS = {
    0:"tmSUP", 1:"tmSUB", 2:"tmSUBSUP"
}

# ── V3 Template variations (from records3/tmpl.rb VARIATIONS) ──
# key: selector_number → {variation_code: [variation_names]}
VARIATIONS = {
    # Fences 0-5: tvFENCE_L + tvFENCE_R
    0:{0:["tvFENCE_L","tvFENCE_R"],1:["tvFENCE_L"],2:["tvFENCE_R"]},
    1:{0:["tvFENCE_L","tvFENCE_R"],1:["tvFENCE_L"],2:["tvFENCE_R"]},
    2:{0:["tvFENCE_L","tvFENCE_R"],1:["tvFENCE_L"],2:["tvFENCE_R"]},
    3:{0:["tvFENCE_L","tvFENCE_R"],1:["tvFENCE_L"],2:["tvFENCE_R"]},
    4:{0:["tvFENCE_L","tvFENCE_R"],1:["tvFENCE_L"],2:["tvFENCE_R"]},
    5:{0:["tvFENCE_L","tvFENCE_R"],1:["tvFENCE_L"],2:["tvFENCE_R"]},
    6:{0:["tvFENCE_L","tvFENCE_R"]},
    7:{0:["tvFENCE_L","tvFENCE_R"]},
    # Intervals 8-12: tvFENCE_L + tvFENCE_R
    8:{0:["tvFENCE_L","tvFENCE_R"]},
    9:{0:["tvFENCE_L","tvFENCE_R"]},
    10:{0:["tvFENCE_L","tvFENCE_R"]},
    11:{0:["tvFENCE_L","tvFENCE_R"]},
    12:{0:["tvFENCE_L","tvFENCE_R"]},
    # Roots 13
    13:{0:["tvROOT_SQ"],1:["tvROOT_NTH"]},
    # Fractions 14
    14:{0:["tvFR_FULL"],1:["tvFR_SMALL"]},
    # Scripts 15 (variation → script type)
    # Over/Underbars 16-17
    16:{0:["tvBAR_SINGLE"],1:["tvBAR_DOUBLE"]},
    17:{0:["tvBAR_SINGLE"],1:["tvBAR_DOUBLE"]},
    # Arrows 18-20
    18:{0:["tvAR_SINGLE","tvAR_LEFT","tvAR_TOP"],1:["tvAR_SINGLE","tvAR_LEFT","tvAR_BOTTOM"]},
    19:{0:["tvAR_SINGLE","tvAR_RIGHT","tvAR_TOP"],1:["tvAR_SINGLE","tvAR_RIGHT","tvAR_TOP"]},
    20:{0:["tvAR_SINGLE","tvAR_RIGHT","tvAR_LEFT","tvAR_TOP"],1:["tvAR_SINGLE","tvAR_RIGHT","tvAR_LEFT","tvAR_TOP"]},
    # Integrals 21-26
    21:{0:["tvINT_1"],1:["tvINT_1","tvBO_LOWER"],2:["tvINT_1","tvBO_LOWER","tvBO_UPPER"],3:["tvINT_1"],4:["tvINT_1","tvBO_LOWER"]},
    22:{0:["tvINT_2"],1:["tvINT_2","tvBO_LOWER"],2:["tvINT_2","tvBO_LOWER","tvBO_UPPER"],3:["tvINT_2"],4:["tvINT_2","tvBO_LOWER"]},
    23:{0:["tvINT_3"],1:["tvINT_3","tvBO_LOWER"],2:["tvINT_3","tvBO_LOWER","tvBO_UPPER"],3:["tvINT_3"],4:["tvINT_3","tvBO_LOWER"]},
    24:{0:["tvINT_1","tvBO_SUM","tvBO_LOWER","tvBO_UPPER"],1:["tvINT_1","tvBO_SUM","tvBO_LOWER"],2:["tvINT_1","tvBO_SUM","tvBO_LOWER"]},
    25:{0:["tvINT_2","tvBO_SUM","tvBO_LOWER"],1:["tvINT_2","tvBO_SUM","tvBO_LOWER"]},
    26:{0:["tvINT_3","tvBO_SUM","tvBO_LOWER"],1:["tvINT_3","tvBO_SUM","tvBO_LOWER"]},
    # Horizontal braces 27-28
    27:{0:["tvHB_TOP"]},
    28:{0:["tvHB_BOT"]},
    # Sums 29-30
    29:{0:["tvBO_LOWER","tvBO_SUM"],1:["tvBO_LOWER","tvBO_UPPER","tvBO_SUM"],2:["tvBO_SUM"]},
    30:{0:["tvBO_LOWER"],1:["tvBO_LOWER","tvBO_UPPER"]},
    # Products 31-32
    31:{0:["tvBO_LOWER","tvBO_SUM"],1:["tvBO_LOWER","tvBO_UPPER","tvBO_SUM"],2:["tvBO_SUM"]},
    32:{0:["tvBO_LOWER"],1:["tvBO_LOWER","tvBO_UPPER"]},
    # Coproducts 33-34
    33:{0:["tvBO_LOWER","tvBO_SUM"],1:["tvBO_LOWER","tvBO_UPPER","tvBO_SUM"],2:["tvBO_SUM"]},
    34:{0:["tvBO_LOWER"],1:["tvBO_LOWER","tvBO_UPPER"]},
    # Unions 35-36
    35:{0:["tvBO_LOWER","tvBO_SUM"],1:["tvBO_LOWER","tvBO_UPPER","tvBO_SUM"],2:["tvBO_SUM"]},
    36:{0:["tvBO_LOWER"],1:["tvBO_LOWER","tvBO_UPPER"]},
    # Intersections 37-38
    37:{0:["tvBO_LOWER","tvBO_SUM"],1:["tvBO_LOWER","tvBO_UPPER","tvBO_SUM"],2:["tvBO_SUM"]},
    38:{0:["tvBO_LOWER"],1:["tvBO_LOWER","tvBO_UPPER"]},
    # Limits 39
    39:{0:["tvBO_UPPER"],1:["tvBO_LOWER"],2:["tvBO_LOWER","tvBO_UPPER"]},
    # Long division 40
    40:{0:["tvLD_UPPER"]},
    # Frac with slash 41
    41:{0:["tvFR_SLASH"],1:["tvFR_SLASH","tvFR_BASE"],2:["tvFR_SLASH","tvFR_SMALL"]},
    # Big integral-style ops 42
    42:{0:["tvBO_LOWER"],1:["tvBO_UPPER"],2:["tvBO_LOWER","tvBO_UPPER"]},
    # Big sum-style ops 43
    43:{0:["tvBO_SUM","tvBO_LOWER"],1:["tvBO_SUM","tvBO_UPPER"],2:["tvBO_SUM","tvBO_LOWER","tvBO_UPPER"]},
    # Scripts 44 (precedes)
    44:{0:["tvSU_PRECEDES"],1:["tvSU_PRECEDES"],2:["tvSU_PRECEDES"],3:["tvSU_PRECEDES"]},
    # Dirac 45
    45:{0:["tvDI_LEFT","tvDI_RIGHT"],1:["tvDI_LEFT"],2:["tvDI_RIGHT"]},
    # Vectors 46-47
    46:{0:["tvVE_UNDER","tvVE_LEFT"],1:["tvVE_UNDER","tvVE_RIGHT"],2:["tvVE_UNDER","tvVE_LEFT","tvVE_RIGHT"]},
    47:{0:["tvVE_LEFT"],1:["tvVE_RIGHT"],2:["tvVE_LEFT","tvVE_RIGHT"]},
    # Boxes 48
    48:{0:None,1:None,2:None,3:None,4:None},
}


def _resolve_v3_selector(sel_idx, var_code):
    """Resolve V3 selector and variation.

    V3 uses different selector numbers than V5 for the same templates.
    Selectors 15 and 44 are special "script" selectors where the
    variation determines which script type (tmSUB/tmSUP/tmSUBSUP).
    """
    if sel_idx in (15, 44):
        return SCRIPT_SELECTORS.get(var_code, "tmSUB")
    return SELECTORS.get(sel_idx, f"tmUNKNOWN_{sel_idx}")


def _resolve_v3_variations(sel_idx, var_code):
    """Resolve V3 variation code to variation name list."""
    var_map = VARIATIONS.get(sel_idx, {})
    result = var_map.get(var_code)
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return [result] if result else []


# ── Record parsers (V3 uses options from tag byte) ────────

def _parse_font(stream, opts):
    """FONT(8): int8 typeface + int8 style + stringz name."""
    tf = stream.int8()
    style = stream.int8()
    name_bytes = bytearray()
    while stream.remaining > 0:
        b = stream.uint8()
        if b == 0:
            break
        name_bytes.append(b)
    return {
        "type": "font",
        "options": opts,
        "typeface": tf + 128,
        "style": style,
        "name": bytes(name_bytes).decode("utf-8", errors="replace"),
    }


def _parse_char(stream, opts):
    """CHAR(2): opt nudge + int8 typeface + mtef16 mt_code + opt embell_list."""
    from .records5 import _parse_nudge

    rec = {"type": "char", "options": opts}
    if opts & OPT_NUDGE:
        rec["nudge"] = _parse_nudge(stream)
    _tf = stream.int8()
    rec["typeface"] = _tf + 128
    rec["mt_code_value"] = f"0x{stream.mtef16():04X}"
    if opts & OPT_EMBELL:
        rec["embellishment_list"] = _parse_object_list(stream)
    return rec


def _parse_tmpl(stream, opts):
    """TMPL(3): opt nudge + int8 selector + int8 variation + int8 tmpl_options + subobjects."""
    from .records5 import _parse_nudge

    rec = {"type": "tmpl", "options": opts}
    if opts & OPT_NUDGE:
        rec["nudge"] = _parse_nudge(stream)

    sel_idx = stream.int8()
    var_code = stream.uint8()
    rec["selector"] = _resolve_v3_selector(sel_idx, var_code)
    rec["variation"] = _resolve_v3_variations(sel_idx, var_code)
    rec["template_specific_options"] = stream.uint8()
    rec["subobjects"] = _parse_object_list(stream)
    return rec


def _parse_line(stream, opts):
    """LINE(1): opt nudge + opt mtef16 line_spacing + opt ruler + opt object_list."""
    from .records5 import _parse_nudge, _parse_ruler

    rec = {"type": "line", "options": opts}
    if opts & OPT_NUDGE:
        rec["nudge"] = _parse_nudge(stream)
    if opts & OPT_LINE_LSPACE:
        rec["line_spacing"] = stream.mtef16()
    if opts & OPT_LINE_RULER:
        rec["ruler"] = _parse_ruler(stream)
    if not (opts & OPT_LINE_NULL):
        rec["objects"] = _parse_object_list(stream)
    return rec


def _parse_pile(stream, opts):
    """PILE(4): opt nudge + int8 halign + int8 valign + opt ruler + object_list."""
    from .records5 import _parse_nudge, _parse_ruler

    rec = {"type": "pile", "options": opts}
    if opts & OPT_NUDGE:
        rec["nudge"] = _parse_nudge(stream)
    rec["halign"] = stream.int8()
    rec["valign"] = stream.int8()
    if opts & OPT_LINE_RULER:
        rec["ruler"] = _parse_ruler(stream)
    rec["lines"] = _parse_object_list(stream)
    return rec


def _parse_matrix(stream, opts):
    """MATRIX(5): opt nudge + valign + h_just + v_just + rows + cols + row_parts + col_parts + object_list.

    V3 matrix uses bit-level packing for row/col partition lines (bit nbits:2),
    unlike V5 which uses byte-packed 2-bit values.
    """
    from .records5 import _parse_nudge

    rec = {"type": "matrix", "options": opts}
    if opts & OPT_NUDGE:
        rec["nudge"] = _parse_nudge(stream)

    rec["valign"] = stream.int8()
    rec["h_just"] = stream.int8()
    rec["v_just"] = stream.int8()
    n_rows = stream.int8()
    n_cols = stream.int8()
    rec["rows"] = max(0, n_rows)
    rec["cols"] = max(0, n_cols)

    # Row parts: (rows+1) entries of 2 bits each, then realign
    row_parts = []
    for _ in range(n_rows + 1):
        row_parts.append(stream.nibble() & 0x3)  # 2 bits per part
    # Realign to byte boundary
    offset = (((n_rows + 1) * 2) % 8)
    if offset != 0:
        stream.align_byte()
    rec["row_parts"] = row_parts

    # Col parts: (cols+1) entries of 2 bits each, then realign
    col_parts = []
    for _ in range(n_cols + 1):
        col_parts.append(stream.nibble() & 0x3)
    offset = (((n_cols + 1) * 2) % 8)
    if offset != 0:
        stream.align_byte()
    rec["col_parts"] = col_parts

    rec["cells"] = _parse_object_list(stream)
    return rec


def _parse_embell(stream, opts):
    """EMBELL(6): uint8 code."""
    code = stream.uint8()
    from .records5 import EMBELL_CODES
    return {"type": "embell", "options": opts, "embell_code": code,
            "embell": EMBELL_CODES.get(code, f"embUNKNOWN_{code}")}


def _parse_ruler(stream, opts):
    """RULER(7): int8 n_stops + n_stops*(int8 type + mtef16 position)."""
    from .records5 import _parse_ruler as _r5
    return _r5(stream)


def _parse_size(stream, opts):
    """SIZE(9): same as v5."""
    from .records5 import _parse_size as _r5
    return _r5(stream)


def _parse_future(stream, opts):
    """FUTURE skip."""
    from .records5 import _parse_future as _r5
    return _r5(stream)


# ── Dispatch table (Payload Choice equivalent) ────────────

_V3_DISPATCH = {
    CHAR: _parse_char,
    TMPL: _parse_tmpl,
    LINE: _parse_line,
    PILE: _parse_pile,
    MATRIX: _parse_matrix,
    EMBELL: _parse_embell,
    RULER: _parse_ruler,
    FONT: _parse_font,
    SIZE: _parse_size,
}


def _dispatch(stream, rt, opts):
    """Dispatch V3 record type to parser."""
    if rt in _V3_DISPATCH:
        return _V3_DISPATCH[rt](stream, opts)
    if rt in (FULL, SUB, SUB2, SYM, SUBSYM):
        return {"type": "size", "size_type": rt}
    if rt >= 15:  # Future fallback
        return _parse_future(stream, opts)
    return None


def _parse_object_list(stream):
    """Parse records until END(0). V3 tag = bit4 options + bit4 type in one byte."""
    objects = []
    while stream.remaining > 0:
        tag = stream.uint8()
        rt = tag & 0x0F         # low 4 bits: record type
        opts = (tag >> 4) & 0x0F  # high 4 bits: options
        if rt == END:
            break
        obj = _dispatch(stream, rt, opts)
        if obj is not None:
            objects.append(obj)
    return objects


# ── Top-level equation parser ────────────────────────────

def parse_equation_v3(stream):
    """Parse complete MTEF v3 equation.

    V3 stream layout (after 28-byte OLE header):
      version(1) platform(1) product(1) product_version(1)
      product_subversion(1)
    Then: array of named_record until END.
    No app_key, no equation_options.

    Unlike V5, V3 equations don't have a top-level LINE wrapper.
    Records (fonts, chars, templates) appear directly under <mtef>.
    """
    result = {"type": "mtef", "mtef_version": 3, "equation": None, "records": []}

    while stream.remaining > 0:
        tag = stream.uint8()
        rt = tag & 0x0F
        opts = (tag >> 4) & 0x0F

        if rt == END:
            return result

        obj = _dispatch(stream, rt, opts)
        if obj is not None:
            result["records"].append(obj)

    return result
