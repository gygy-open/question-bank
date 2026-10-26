"""MTEF v5 binary record parser — systematic translation of the mathtype gem.

Every record class matches the Ruby gem's BinData definitions in:
  mathtype-0.0.7.5/lib/records5/*.rb

Structure: NamedRecord = int8 tag → Payload(Choice) → RecordClass

Tag byte = record_type in low 5 bits (0-19 for defined types).
Types 10-14 are compact size markers with no extra fields.
Types >= 100 are future records with mt_uint length prefix.

For records WITH options: LINE, CHAR, TMPL, PILE, MATRIX, EMBELL, EQN_PREFS, COLOR_DEF
For records WITHOUT options: FONT_DEF, ENCODING_DEF, SIZE, COLOR, RULER, FONT_STYLE_DEF
For records with NO DATA: FULL, SUB, SUB2, SYM, SUBSYM, END
"""

from .stream import ByteStream

# ── Record type constants ─────────────────────────────────
END=0; LINE=1; CHAR=2; TMPL=3; PILE=4; MATRIX=5
EMBELL=6; RULER=7; FONT_STYLE_DEF=8; SIZE=9
FULL=10; SUB=11; SUB2=12; SYM=13; SUBSYM=14
COLOR=15; COLOR_DEF=16; FONT_DEF=17; EQN_PREFS=18; ENCODING_DEF=19
MT_COMMENT=102
FUTURE_MIN=100

# ── Option flags (from gem's OPTIONS hash) ────────────────
OPT_NUDGE=0x08; OPT_CHAR_EMBELL=0x01; OPT_CHAR_FUNC=0x02
OPT_CHAR_ENC_8=0x04; OPT_CHAR_ENC_16=0x10; OPT_CHAR_NO_MT=0x20
OPT_LINE_NULL=0x01; OPT_LINE_LSPACE=0x04; OPT_LP_RULER=0x02
OPT_COLOR_CMYK=0x01; OPT_COLOR_NAME=0x04

# ── Embellishment codes ───────────────────────────────────
EMBELL_CODES={2:"emb1DOT",3:"emb2DOT",4:"emb3DOT",5:"emb1PRIME",
6:"emb2PRIME",7:"embBPRIME",8:"embTILDE",9:"embHAT",10:"embNOT",
11:"embRARROW",12:"embLARROW",13:"embBARROW",14:"embR1ARROW",
15:"embL1ARROW",16:"embMBAR",17:"embOBAR",18:"emb3PRIME",
19:"embFROWN",20:"embSMILE",21:"embX_BARS",22:"embUP_BAR",
23:"embDOWN_BAR",24:"emb4DOT",25:"embU_1DOT",26:"embU_2DOT",
27:"embU_3DOT",28:"embU_4DOT",29:"embU_BAR",30:"embU_TILDE",
31:"embU_FROWN",32:"embU_SMILE",33:"embU_RARROW",34:"embU_LARROW",
35:"embU_BARROW",36:"embU_R1ARROW",37:"embU_L1ARROW"}

SELECTORS={0:"tmANGLE",1:"tmPAREN",2:"tmBRACE",3:"tmBRACK",
4:"tmBAR",5:"tmDBAR",6:"tmFLOOR",7:"tmCEILING",8:"tmOBRACK",
9:"tmINTERVAL",10:"tmROOT",11:"tmFRACT",12:"tmUBAR",13:"tmOBAR",
14:"tmARROW",15:"tmINTEG",16:"tmSUM",17:"tmPROD",18:"tmCOPROD",
19:"tmUNION",20:"tmINTER",21:"tmINTOP",22:"tmSUMOP",23:"tmLIM",
24:"tmHBRACE",25:"tmHBRACK",26:"tmLDIV",27:"tmSUB",28:"tmSUP",
29:"tmSUBSUP",30:"tmDIRAC",31:"tmVEC",32:"tmTILDE",33:"tmHAT",
34:"tmARC",35:"tmJSTATUS",36:"tmSTRIKE",37:"tmBOX"}

HALIGN={1:"left",2:"center",3:"right",4:"al",5:"dec"}
VALIGN={0:"top_baseline",1:"center_baseline",2:"bottom_baseline",3:"center",4:"axis"}

VARIATIONS={
    frozenset(range(0,9)):[(0x0001,"tvFENCE_L"),(0x0002,"tvFENCE_R")],
    frozenset([10]):[(0,"tvROOT_SQ"),(1,"tvROOT_NTH")],
    frozenset([11]):[(0x0001,"tvFR_SMALL"),(0x0002,"tvFR_SLASH"),(0x0004,"tvFR_BASE")],
    frozenset([12,13]):[(0x0001,"tvBAR_DOUBLE")],
    frozenset([14]):[(0x0000,"tvAR_SINGLE"),(0x0001,"tvAR_DOUBLE"),(0x0002,"tvAR_HARPOON"),
        (0x0004,"tvAR_TOP"),(0x0008,"tvAR_BOTTOM"),(0x0010,"tvAR_LEFT"),(0x0020,"tvAR_RIGHT")],
    frozenset([15]):[(0x0001,"tvINT_1"),(0x0002,"tvINT_2"),(0x0003,"tvINT_3"),
        (0x0004,"tvINT_LOOP"),(0x0008,"tvINT_CW_LOOP"),(0x000C,"tvINT_CCW_LOOP"),(0x0100,"tvINT_EXPAND")],
    frozenset(range(15,24)):[(0x0010,"tvBO_LOWER"),(0x0020,"tvBO_UPPER"),(0x0040,"tvBO_SUM"),(-0x0040,"tvBO_INT")],
    frozenset([23]):[(0,"tvSUBAR"),(1,"tvDUBAR")],
    frozenset([24,25]):[(0x0001,"tvHB_TOP")],
    frozenset([26]):[(0x0001,"tvLD_UPPER")],
    frozenset([27,28,29]):[(0x0001,"tvSU_PRECEDES")],
    frozenset([30]):[(0x0001,"tvDI_LEFT"),(0x0002,"tvDI_RIGHT")],
    frozenset([31]):[(0x0001,"tvVE_LEFT"),(0x0002,"tvVE_RIGHT"),(0x0004,"tvVE_UNDER"),(0x0008,"tvVE_HARPOON")],
    frozenset([36]):[(0x0001,"tvST_HORIZ"),(0x0002,"tvST_UP"),(0x0004,"tvST_DOWN")],
    frozenset([37]):[(0x0001,"tvBX_ROUND"),(0x0002,"tvBX_LEFT"),(0x0004,"tvBX_RIGHT"),(0x0008,"tvBX_TOP"),(0x0010,"tvBX_BOTTOM")],
}

def _resolve_variations(sel_idx,var_code):
    if sel_idx == 14 and (var_code & 0x0004) and (var_code & 0x0008):
        result = ["tvAR_TOPBOTTOM"]
        if (var_code & 0x0002) == 0x0002:
            result.append("tvAR_HARPOON")
        if (var_code & 0x0001) == 0x0001:
            result.append("tvAR_DOUBLE")
        if (var_code & 0x0010) == 0x0010:
            result.append("tvAR_LEFT")
        if (var_code & 0x0020) == 0x0020:
            result.append("tvAR_RIGHT")
        return result
    result=[]
    for sel_range,flags in VARIATIONS.items():
        if sel_idx not in sel_range: continue
        for flag,name in flags:
            if flag<0:
                if not(var_code&(-flag)): result.append(name)
            elif flag==0:
                if var_code==0: result.append(name)
            else:
                if(var_code&flag)==flag: result.append(name)
    return result

# ── Nibble-packed dimension reader (for EQN_PREFS) ──────

def _read_nibble_dim(stream):
    """Read one nibble-packed dimension value (unit + digits + 0xF terminator)."""
    try:
        unit_nib=stream.nibble()
    except IndexError:
        return {"unit_nibble":0,"value":""}
    val=[]
    for _ in range(20):  # max 20 nibbles per value
        try:
            n=stream.nibble()
        except IndexError:
            break
        if n==0xF: break
        if n<=9: val.append(str(n))
        elif n==0xA: val.append(".")
        elif n==0xB: val.append("-")
    return {"unit_nibble":unit_nib,"value":"".join(val)}

# ── Individual record parsers (matching gem's class fields) ──

def _parse_font_def(stream):
    """FONT_DEF(17): mt_uint enc_def_index + stringz font_name. No options."""
    enc_idx=stream.mt_uint()
    name_bytes=bytearray()
    while stream.remaining>0:
        b=stream.uint8()
        if b==0: break
        name_bytes.append(b)
    return {"type":"font_def","enc_def_index":enc_idx,"font_name":bytes(name_bytes).decode("utf-8",errors="replace")}

def _parse_encoding_def(stream):
    """ENCODING_DEF(19): stringz name. No options."""
    name_bytes=bytearray()
    while stream.remaining>0:
        b=stream.uint8()
        if b==0: break
        name_bytes.append(b)
    return {"type":"encoding_def","name":bytes(name_bytes).decode("utf-8",errors="replace")}

def _parse_char(stream):
    """CHAR(2): int8 options + optional nudge + int8 typeface + opt mtef16 mt_code + opt font_pos + opt embell_list."""
    opts=stream.uint8()
    rec={"type":"char","options":opts}
    if opts&OPT_NUDGE:
        rec["nudge"]=_parse_nudge(stream)
    _tf=stream.int8()
    rec["typeface"]=_tf+128
    if not(opts&OPT_CHAR_NO_MT):
        rec["mt_code_value"]=f"0x{stream.mtef16():04X}"
    if opts&OPT_CHAR_ENC_8:
        rec["font_position"]=stream.uint8()
    elif opts&OPT_CHAR_ENC_16:
        rec["font_position"]=stream.mtef16()
    tf=rec["typeface"]
    rec["variation"]="textmode" if tf in(1,9,10) else "mathmode"
    if opts&OPT_CHAR_EMBELL:
        rec["embellishment_list"]=_parse_object_list(stream)
    return rec

def _parse_tmpl(stream):
    """TMPL(3): int8 options + opt nudge + int8 selector + variation(1-2 bytes) + int8 template_specific_options + object_list."""
    opts=stream.uint8()
    rec={"type":"tmpl","options":opts}
    if opts&OPT_NUDGE:
        rec["nudge"]=_parse_nudge(stream)
    sel_idx=stream.int8()
    rec["selector"]=SELECTORS.get(sel_idx,f"tmUNKNOWN_{sel_idx}")
    var1=stream.uint8()
    if var1&0x80:
        var2=stream.uint8()
        var_code=(var1&0x7F)|(var2<<8)
    else:
        var_code=var1
    rec["variation_code"]=var_code
    rec["variation"]=_resolve_variations(sel_idx,var_code)
    rec["template_specific_options"]=stream.uint8()
    rec["subobjects"]=_parse_object_list(stream)
    return rec

def _parse_line(stream,is_top=False):
    """LINE(1): int8 options + opt nudge + opt mtef16 line_spacing + opt ruler + opt object_list."""
    opts=stream.uint8()
    rec={"type":"line","options":opts}
    if opts&OPT_NUDGE:
        rec["nudge"]=_parse_nudge(stream)
    if opts&OPT_LINE_LSPACE:
        rec["line_spacing"]=stream.mtef16()
    if opts&OPT_LP_RULER:
        rec["ruler"]=_parse_ruler(stream)
    if not(opts&OPT_LINE_NULL) or is_top:
        rec["objects"]=_parse_object_list(stream)
    return rec

def _parse_pile(stream):
    """PILE(4): int8 options + opt nudge + int8 halign + int8 valign + opt ruler + object_list."""
    opts=stream.uint8()
    rec={"type":"pile","options":opts}
    if opts&OPT_NUDGE:
        rec["nudge"]=_parse_nudge(stream)
    rec["halign"]=HALIGN.get(stream.int8(), "center")
    rec["valign"]=VALIGN.get(stream.int8(), "center_baseline")
    if opts&OPT_LP_RULER:
        rec["ruler"]=_parse_ruler(stream)
    rec["lines"]=_parse_object_list(stream)
    return rec

def _parse_matrix(stream):
    """MATRIX(5): int8 options + opt nudge + int8 valign + int8 h_just + int8 v_just
       + int8 rows + int8 cols + row_parts + col_parts + object_list."""
    opts=stream.uint8()
    rec={"type":"matrix","options":opts}
    if opts&OPT_NUDGE:
        rec["nudge"]=_parse_nudge(stream)
    rec["valign"]=VALIGN.get(stream.int8(), "center_baseline")
    rec["h_just"]=HALIGN.get(stream.int8(), "center")
    rec["v_just"]=VALIGN.get(stream.int8(), "center_baseline")
    n_rows=stream.int8()
    n_cols=stream.int8()
    rec["rows"]=max(0,n_rows)
    rec["cols"]=max(0,n_cols)
    # Row/col partition lines: packed 2-bit values, (n+1) entries, rounded up to bytes
    n_row_bytes=(n_rows+4)//4
    n_col_bytes=(n_cols+4)//4
    rec["row_parts"]=[stream.uint8() for _ in range(max(0,n_row_bytes))]
    rec["col_parts"]=[stream.uint8() for _ in range(max(0,n_col_bytes))]
    rec["cells"]=_parse_object_list(stream)
    return rec

def _parse_embell(stream):
    """EMBELL(6): int8 options + uint8 embell_code. (options ignored in gem)"""
    stream.uint8()  # options — not used in gem's snapshot
    code=stream.uint8()
    return {"type":"embell","embell_code":code,"embell":EMBELL_CODES.get(code,f"embUNKNOWN_{code}")}

def _parse_ruler(stream):
    """RULER(7) embedded in LINE/PILE: int8 n_stops + n_stops*(int8 type + mtef16 position)."""
    n_stops=stream.int8()
    if n_stops<0: n_stops=0
    n_stops=min(n_stops,20)  # bound to prevent runaway reads
    stops=[]
    for _ in range(n_stops):
        try:
            stops.append({"tab_stop_type":stream.int8(),"tab_stop":stream.mtef16()})
        except IndexError:
            break
    return {"type":"ruler","n_stops":n_stops,"stops":stops}

def _parse_size(stream):
    """SIZE(9): int8 size_select + conditional point_size/lsize/dsize."""
    sel=stream.int8()
    if sel==101:
        return {"type":"size","size_select":101,"point_size":-stream.mtef16()}
    if sel==100:
        lsize=stream.uint8()
        dsize=stream.mtef16()
        return {"type":"size","size_select":100,"lsize":lsize,"dsize":dsize}
    dsize_raw=stream.uint8()
    return {"type":"size","size_select":sel,"lsize":sel,"dsize":dsize_raw-128}

def _parse_color(stream):
    """COLOR(15): mt_uint color_def_index. No options."""
    return {"type":"color","color_def_index":stream.mt_uint()}

def _parse_color_def(stream):
    """COLOR_DEF(16): int8 options + mtef16 rgb/cmyk + optional stringz name."""
    opts=stream.uint8()
    rec={"type":"color_def","options":opts}
    if opts&OPT_COLOR_CMYK:
        rec["c"]=stream.mtef16(); rec["m"]=stream.mtef16()
        rec["y"]=stream.mtef16(); rec["k"]=stream.mtef16()
    else:
        rec["r"]=stream.mtef16(); rec["g"]=stream.mtef16(); rec["b"]=stream.mtef16()
    if opts&OPT_COLOR_NAME:
        name_bytes=bytearray()
        while stream.remaining>0:
            b=stream.uint8()
            if b==0:
                break
            name_bytes.append(b)
        rec["color_name"]=bytes(name_bytes).decode("utf-8",errors="replace")
    return rec

def _parse_font_style_def(stream):
    """FONT_STYLE_DEF(8): mt_uint font_def_index + int8 char_style. No options."""
    return {"type":"font_style_def","font_def_index":stream.mt_uint(),"font_style":stream.int8()}

def _parse_nudge(stream):
    """Nudge: int8 small_dx + int8 small_dy + optional mtef16 large_dx/large_dy."""
    small_dx=stream.int8()
    small_dy=stream.int8()
    if small_dx==-128 and small_dy==-128:
        dx=stream.mtef16()
        dy=stream.mtef16()
    else:
        dx=small_dx-128
        dy=small_dy-128
    return {"dx":dx,"dy":dy}

def _parse_eqn_prefs(stream):
    """EQN_PREFS(18): int8 options + nibble-packed sizes + spaces + byte-aligned styles."""
    opts=stream.uint8()
    rec={"type":"eqn_prefs","options":opts,"sizes":[],"spaces":[],"styles":[]}

    # Bound sizes_count to avoid consuming the entire stream
    sizes_count=min(stream.uint8(), 30)
    for _ in range(sizes_count):
        try:
            rec["sizes"].append(_read_nibble_dim(stream))
        except IndexError:
            break
    stream.align_byte()

    try:
        spaces_count=min(stream.uint8(), 50)
    except IndexError:
        return rec
    for _ in range(spaces_count):
        try:
            rec["spaces"].append(_read_nibble_dim(stream))
        except IndexError:
            break
    stream.align_byte()

    try:
        styles_count=min(stream.uint8(), 20)
    except IndexError:
        return rec
    for _ in range(styles_count):
        try:
            fd=stream.uint8()
            if fd!=0:
                cs=stream.uint8()
                rec["styles"].append({"font_def":fd,"font_style":cs})
            else:
                rec["styles"].append({"font_def":0,"font_style":0})
        except IndexError:
            break
    return rec

def _parse_future(stream):
    """FUTURE(>=100): mt_uint length + skip."""
    length=stream.mt_uint()
    stream.bytes(length)
    return None

def _parse_mt_comment(stream):
    """MT_COMMENT(102): mt_uint byte length + comment strings."""
    length=stream.mt_uint()
    stream.bytes(length)
    return None

def _record_type(tag):
    """MTEF v5 record types are full byte values, not low-bit tags."""
    return tag

# ── Object list (equivalent to NamedRecord + Payload dispatch) ──

def _parse_object_list(stream):
    """Parse sequence of named_record entries until element.record_type == 0 (END)."""
    objects=[]
    while stream.remaining>0:
        try:
            tag=stream.uint8()
        except IndexError:
            break
        rt=_record_type(tag)
        if rt==END:
            break
        obj=_dispatch(stream,rt)
        if obj is not None:
            objects.append(obj)
    return objects

def _dispatch(stream,rt):
    """Dispatch record type to the correct parser (equivalent to Payload Choice)."""
    if rt==CHAR: return _parse_char(stream)
    if rt==TMPL: return _parse_tmpl(stream)
    if rt==LINE: return _parse_line(stream)
    if rt==PILE: return _parse_pile(stream)
    if rt==MATRIX: return _parse_matrix(stream)
    if rt==EMBELL: return _parse_embell(stream)
    if rt==RULER: return _parse_ruler(stream)
    if rt==FONT_STYLE_DEF: return _parse_font_style_def(stream)
    if rt==SIZE: return _parse_size(stream)
    if rt in(FULL,SUB,SUB2,SYM,SUBSYM): return {"type":"size","size_type":rt}
    if rt==COLOR: return _parse_color(stream)
    if rt==COLOR_DEF: return _parse_color_def(stream)
    if rt==FONT_DEF: return _parse_font_def(stream)
    if rt==ENCODING_DEF: return _parse_encoding_def(stream)
    if rt==EQN_PREFS: return _parse_eqn_prefs(stream)
    if rt==MT_COMMENT: return _parse_mt_comment(stream)
    if rt>=20: return _parse_future(stream)
    return None

# ── Top-level equation parser ────────────────────────────

def parse_equation(stream):
    """Parse complete MTEF v5 equation after stream header is skipped."""
    result={"type":"mtef","mtef_version":5,"font_defs":[],"encoding_defs":[],"eqn_prefs":None,"equation":None}

    while stream.remaining>0:
        tag=stream.uint8()
        rt=_record_type(tag)
        if rt==END:
            return result

        # Definition/comment records: consume and continue
        if rt==MT_COMMENT:
            _parse_mt_comment(stream)
            continue
        if rt>=20:
            _parse_future(stream)
            continue
        if rt==FONT_DEF:
            result["font_defs"].append(_parse_font_def(stream))
            continue
        if rt==ENCODING_DEF:
            result["encoding_defs"].append(_parse_encoding_def(stream))
            continue
        if rt==EQN_PREFS:
            prefs_pos=stream.position-1
            result["eqn_prefs"]=_parse_eqn_prefs(stream)
            # Safety: if nibble parsing consumed everything, rescan for equation body
            if stream.remaining==0:
                stream._pos=prefs_pos+1  # back to just after EQN_PREFS tag
                _rescan_for_equation_body(stream)
            continue

        # Equation body: any non-definition record starts the equation
        stream.unread_byte()

        while stream.remaining>0:
            tag=stream.uint8(); rt=_record_type(tag)
            if rt==END: continue
            if rt==LINE:
                eq_line=_parse_line(stream,is_top=True)
                if any(o.get("type") in("char","tmpl","pile","matrix") for o in eq_line.get("objects",[])):
                    result["equation"]=eq_line; return result
                continue
            if rt in(CHAR,TMPL,PILE,MATRIX):
                obj=_dispatch(stream,rt)
                if obj: result["equation"]={"type":"line","options":0,"objects":[obj]}
                return result
            _dispatch(stream,rt)

    return result


def _skip_over_eqn_prefs(stream):
    """Skip EQN_PREFS by scanning raw bytes for the equation body start.

    The EQN_PREFS nibble-packed data is 80-120 bytes typically.
    We scan forward for a distinctive equation body pattern:
    FULL(10) followed immediately by LINE(1) with reasonable opts,
    or LINE(1) followed within a few bytes by CHAR(2) or TMPL(3).
    """
    data = stream._data
    pos = stream._pos
    end = len(data)

    # Scan for FULL(10) + LINE(1) pattern (most common)
    for i in range(pos, min(end - 3, pos + 150)):
        if (data[i] & 0x1F) == FULL:
            next_rt = data[i + 1] & 0x1F if i + 1 < end else -1
            if next_rt == LINE:
                opts = data[i + 2] if i + 2 < end else -1
                if opts <= 0x0F:
                    # Found FULL+LINE — position at the LINE tag
                    stream._pos = i + 1  # at the LINE (skip FULL)
                    return

    # Fallback: scan for LINE with CHAR/TMPL after it
    for i in range(pos, min(end - 3, pos + 150)):
        if (data[i] & 0x1F) == LINE:
            opts = data[i + 1] if i + 1 < end else -1
            if not (opts & 0x01) and opts <= 0x08:
                for j in range(i + 2, min(end, i + 20)):
                    rt_j = data[j] & 0x1F
                    if rt_j in (CHAR, TMPL):
                        stream._pos = i + 1
                        return
                    if rt_j == END:
                        break

    # Last resort: advance to near the end
    stream._pos = max(pos, end - 80)


def _rescan_for_equation_body(stream):
    """Called when EQN_PREFS nibble parsing consumed all remaining bytes.
    Rescan raw data from current position to find the equation body start.
    """
    data=stream._data; end=len(data); pos=stream._pos
    for i in range(pos, min(end-3, pos+150)):
        if (data[i]&0x1F)==FULL:
            next_rt=data[i+1]&0x1F if i+1<end else -1
            if next_rt in(LINE,TMPL):
                stream._pos=i+1; stream._nibble=None; return
    stream._pos=max(pos,end-50); stream._nibble=None


def _skip_eqn_prefs_to_body(stream):
    """Skip EQN_PREFS nibble data by scanning for equation body start.

    The equation body starts with FULL(10)+LINE(1) or FULL(10)+TMPL(3).
    We skip a zone of ~80 bytes (typical nibble data size) to avoid
    false positives in styles data, then find the FIRST FULL+LINE/TMPL.
    """
    data = stream._data
    end = len(data)
    pos = stream._pos
    # Skip typical nibble zone (sizes+spaces nibbles ~60 bytes + styles ~24 bytes)
    skip_zone = min(pos + 80, end - 10)
    # Find the FIRST FULL+LINE or FULL+TMPL after the skip zone
    for i in range(skip_zone, end - 2):
        if (data[i] & 0x1F) == FULL:
            next_rt = data[i + 1] & 0x1F if i + 1 < end else -1
            if next_rt in (LINE, TMPL):
                stream._pos = i + 1
                stream._nibble = None
                return
    # Fallback: advance near the end
    stream._pos = max(pos, end - 30)
    stream._nibble = None


def _reposition_to_equation_body(stream, eqn_prefs_pos):
    """Reposition the stream to the equation body start.

    The EQN_PREFS nibble parsing may have consumed all remaining bytes.
    We scan raw data from eqn_prefs_pos forward looking for the actual
    equation body start: the LAST occurrence of a FULL(10)+LINE(1) or
    FULL(10)+TMPL(3) pattern before the end of data.
    """
    data = stream._data
    end = len(data)
    start = eqn_prefs_pos if eqn_prefs_pos else 0

    # Scan for FULL(10) followed by LINE(1) or TMPL(3) - take the FIRST match
    # after skipping the initial EQN_PREFS nibble data area
    best = None
    skip_zone = min(start + 50, end)  # Skip first 50 bytes of nibble zone
    for i in range(skip_zone, end - 2):
        if (data[i] & 0x1F) == FULL:
            next_rt = data[i + 1] & 0x1F if i + 1 < end else -1
            if next_rt in (LINE, TMPL):
                best = i + 1  # Position at LINE/TMPL tag
                break

    if best is not None:
        stream._pos = best
        stream._nibble = None
        return

    # Fallback: scan for the last LINE or TMPL in the data
    for i in range(end - 1, start, -1):
        rt = data[i] & 0x1F
        if rt in (LINE, TMPL):
            stream._pos = i
            stream._nibble = None
            return

    # Last resort
    stream._pos = max(start, end - 50)
    stream._nibble = None


def _skip_to_equation_body(stream):
    """Skip raw bytes from current position to find the equation body start.

    After EQN_PREFS, there may be nibble-packed data followed by the
    equation body. We scan forward for a FULL(10)+LINE(1) pattern that
    marks the start of real equation content.
    """
    data = stream._data
    pos = stream._pos
    end = len(data)

    # Scan for FULL(10) followed by LINE(1) with opts that make sense
    for i in range(pos, min(end - 3, pos + 200)):
        if (data[i] & 0x1F) == FULL:
            # Check if next byte is a LINE with reasonable opts
            next_rt = data[i + 1] & 0x1F if i + 1 < end else -1
            if next_rt == LINE:
                opts = data[i + 2] if i + 2 < end else -1
                if opts <= 0x0F:  # Reasonable LINE options
                    # Look ahead a few bytes for CHAR/TMPL content
                    for j in range(i + 3, min(end, i + 30)):
                        rt_j = data[j] & 0x1F
                        if rt_j in (CHAR, TMPL):
                            stream._pos = i + 1  # Position at the LINE tag
                            return
                        if rt_j == END:
                            break  # This FULL+LINE is empty, keep looking

    # Fallback: advance to near end
    stream._pos = max(pos, end - 80)


def _find_equation_body_raw(stream, start_pos=None):
    """Last-resort: scan raw bytes for the real equation body.

    Used when EQN_PREFS nibble parsing consumed the equation body bytes.
    Scans raw MTEF data for LINE(1) or TMPL(3) records that have the
    most math content (highest count of char/tmpl objects).
    """
    data = stream._data
    end = len(data)
    scan_start = start_pos if (start_pos and start_pos > 0) else stream._pos
    if scan_start <= 0 or scan_start >= end - 10:
        scan_start = max(0, end - 200)

    best_pos = None
    best_count = 0
    best_is_line = True

    # Try LINE candidates (TMPL candidates scan in styles data = too many false positives)
    for i in range(scan_start, end - 3):
        rt = data[i] & 0x1F
        if rt != LINE:
            continue
        opts = data[i + 1] if i + 1 < end else 0xFF
        if (opts & 0x01) or opts > 0x08:  # NULL or suspicious
            continue

        clone = ByteStream(data)
        clone._pos = i + 1  # Skip LINE tag byte
        clone._nibble = None
        try:
            eq_line = _parse_line(clone, is_top=True)
            objs = eq_line.get("objects", [])
            math_count = sum(1 for o in objs if o.get("type") in ("char","tmpl","pile","matrix"))
            if math_count > best_count:
                best_count = math_count
                best_pos = i
                best_is_line = True
        except Exception:
            pass

    if best_pos is not None:
        stream._pos = best_pos + 1
        stream._nibble = None
        return _parse_line(stream, is_top=True)

    return None


def _merge_equation(result, obj):
    """Merge a record into the equation body."""
    if result["equation"] is None:
        result["equation"]={"type":"line","options":0,"objects":[]}
    result["equation"]["objects"].append(obj)
