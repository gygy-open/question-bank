<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">


    <!--
    edot        = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x02D9;</(ns)mo>$-$n</(ns)mover>$n";
    edot/2      = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x00A8;</(ns)mo>$-$n</(ns)mover>$n";
    edot/3      = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x20DB;</(ns)mo>$-$n</(ns)mover>$n";
    edot/4      = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x20DC;</(ns)mo>$-$n</(ns)mover>$n";

    2 => "emb1DOT", # over single dot
    3 => "emb2DOT", # over double dot
    4 => "emb3DOT", # over triple dot
    24 => "emb4DOT", # over quad dot
    -->
    <!-- Dots -->

    <xsl:template match="embell[embell='emb1DOT']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2D9;</mo>
        </mover>
    </xsl:template>


    <xsl:template match="embell[embell='emb2DOT']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#xA8;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="embell[embell='emb3DOT']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x20DB;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="embell[embell='emb4DOT']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x20DC;</mo>
        </mover>
    </xsl:template>

    <!--
    edot/u      = "<(ns)munder>$+$n#$n<(ns)mo>&$#x02D9;</(ns)mo>$-$n</(ns)munder>$n";
    edot/u/2    = "<(ns)munder>$+$n#$n<(ns)mo>&$#x00A8;</(ns)mo>$-$n</(ns)munder>$n";
    edot/u/3    = "<(ns)munder>$+$n#$n<(ns)mo>&$#x20DB;</(ns)mo>$-$n</(ns)munder>$n";
    edot/u/4    = "<(ns)munder>$+$n#$n<(ns)mo>&$#x20DC;</(ns)mo>$-$n</(ns)munder>$n";

    25 => "embU_1DOT", # under single dot
    26 => "embU_2DOT", # under double dot
    27 => "embU_3DOT", # under triple dot
    28 => "embU_4DOT", # under quad dot
    -->
    <!-- Under-dots -->

    <xsl:template match="embell[embell='embU_1DOT']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2D9;</mo>
        </munder>
    </xsl:template>


    <xsl:template match="embell[embell='embU_2DOT']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#xA8;</mo>
        </munder>
    </xsl:template>


    <xsl:template match="embell[embell='embU_3DOT']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x20DB;</mo>
        </munder>
    </xsl:template>


    <xsl:template match="embell[embell='embU_4DOT']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x20DC;</mo>
        </munder>
    </xsl:template>

    <!--
    eprime      = "<(ns)msup>$+$n#$n<(ns)mo>&$#x2032;</(ns)mo>$-$n</(ns)msup>$n";
    eprime/2    = "<(ns)msup>$+$n#$n<(ns)mo>&$#x2033;</(ns)mo>$-$n</(ns)msup>$n";
    eprime/3    = "<(ns)msup>$+$n#$n<(ns)mo>&$#x2034;</(ns)mo>$-$n</(ns)msup>$n";
    eprime/b    = "<(ns)mmultiscripts>$+$n#$n<(ns)mprescripts/>$n<(ns)none/>$n<(ns)mo>&$#x2035;</(ns)mo>$-$n</(ns)mmultiscripts>$n";

    5 => "emb1PRIME", # single prime
    6 => "emb2PRIME", # double prime
    7 => "embBPRIME", # backwards prime (left of character)
    18 => "emb3PRIME", # triple prime
     -->
    <!-- Primes -->

    <xsl:template match="embell[embell='emb1PRIME']">
        <msup>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2032;</mo>
        </msup>
    </xsl:template>


    <xsl:template match="embell[embell='emb2PRIME']">
        <msup>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2033;</mo>
        </msup>
    </xsl:template>


    <xsl:template match="embell[embell='emb3PRIME']">
        <msup>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2034;</mo>
        </msup>
    </xsl:template>


    <xsl:template match="embell[embell='embBPRIME']">
        <mmultiscripts>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mprescripts/><none/>
            <mo>&#x2035;</mo>
        </mmultiscripts>
    </xsl:template>

    <!--
    etilde      = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x02DC;</(ns)mo>$-$n</(ns)mover>$n";
    etilde/u    = "<(ns)munder accentunder='true'>$+$n#$n<(ns)mo>&$#x02DC;</(ns)mo>$-$n</(ns)munder>$n";

    8 => "embTILDE", #  tilde
    30 => "embU_TILDE", #  under tilde (~)
    -->
    <!-- Tilde -->

    <xsl:template match="embell[embell='embTILDE']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2DC;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="embell[embell='embU_TILDE']">
        <munder accentunder="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2DC;</mo>
        </munder>
    </xsl:template>

    <!--
    ehat        = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x005E;</(ns)mo>$-$n</(ns)mover>$n";
    9 => "embHAT", #  hat (circumflex)
    -->
    <!-- Hat -->

    <xsl:template match="embell[embell='embHAT']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>^</mo>
        </mover>
    </xsl:template>
    <!--
    evec        = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x2192;</(ns)mo>$-$n</(ns)mover>$n";
    evec/l      = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x2190;</(ns)mo>$-$n</(ns)mover>$n";
    evec/lr     = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x2194;</(ns)mo>$-$n</(ns)mover>$n";
    evec/h      = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x21C0;</(ns)mo>$-$n</(ns)mover>$n";
    evec/h/l    = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x21BC;</(ns)mo>$-$n</(ns)mover>$n";
    evec/u      = "<(ns)munder>$+$n#$n<(ns)mo>&$#x2192;</(ns)mo>$-$n</(ns)munder>$n";
    evec/u/l    = "<(ns)munder>$+$n#$n<(ns)mo>&$#x2190;</(ns)mo>$-$n</(ns)munder>$n";
    evec/u/lr   = "<(ns)munder>$+$n#$n<(ns)mo>&$#x2194;</(ns)mo>$-$n</(ns)munder>$n";
    evec/u/h    = "<(ns)munder>$+$n#$n<(ns)mo>&$#x21C1;</(ns)mo>$-$n</(ns)munder>$n";
    evec/u/h/l  = "<(ns)munder>$+$n#$n<(ns)mo>&$#x21BD;</(ns)mo>$-$n</(ns)munder>$n";

    11 => "embRARROW", # over right arrow
    12 => "embLARROW", # over left arrow
    13 => "embBARROW", # over both arrow (left and right)
    14 => "embR1ARROW", #  over right single-barbed arrow
    15 => "embL1ARROW", #  over left single-barbed arrow
    33 => "embU_RARROW", # under right arrow
    34 => "embU_LARROW", # under left arrow
    35 => "embU_BARROW", # under both arrow (left and right)
    36 => "embU_R1ARROW", #  under right arrow (1 barb)
    37 => "embU_L1ARROW", #  under left arrow (1 barb)

    -->
    <!-- Arrows -->

    <xsl:template match="embell[embell='embRARROW']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2192;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="embell[embell='embLARROW']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2190;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="embell[embell='embBARROW']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2194;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="embell[embell='embR1ARROW']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x21C0;</mo>
        </mover>
    </xsl:template>


    <xsl:template match="embell[embell='embL1ARROW']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x21BC;</mo>
        </mover>
    </xsl:template>


    <xsl:template match="embell[embell='embU_RARROW']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2192;</mo>
        </munder>
    </xsl:template>


    <xsl:template match="embell[embell='embU_LARROW']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2190;</mo>
        </munder>
    </xsl:template>


    <xsl:template match="embell[embell='embU_BARROW']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2194;</mo>
        </munder>
    </xsl:template>


    <xsl:template match="embell[embell='embU_R1ARROW']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x21C1;</mo>
        </munder>
    </xsl:template>


    <xsl:template match="embell[embell='embU_L1ARROW']">
        <munder>
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x21BD;</mo>
        </munder>
    </xsl:template>

    <!--
    eobar       = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x00AF;</(ns)mo>$-$n</(ns)mover>$n";
    eubar       = "<(ns)munder accentunder='true'>$+$n#$n<(ns)mo>_</(ns)mo>$-$n</(ns)munder>$n";

    17 => "embOBAR", # over-bar
    29 => "embU_BAR", #  under bar
     -->
    <!-- Bars -->

    <xsl:template match="embell[embell='embOBAR']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#xAF;</mo>
        </mover>
    </xsl:template>


    <xsl:template match="embell[embell='embU_BAR']">
        <munder accentunder="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>_</mo>
        </munder>
    </xsl:template>

    <!--
    earc        = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x2322;</(ns)mo>$-$n</(ns)mover>$n";
    earc/u      = "<(ns)munder accentunder='true'>$+$n#$n<(ns)mo>&$#x2322;</(ns)mo>$-$n</(ns)munder>$n";
    earc/s      = "<(ns)mover accent='true'>$+$n#$n<(ns)mo>&$#x2323;</(ns)mo>$-$n</(ns)mover>$n";
    earc/u/s    = "<(ns)munder accentunder='true'>$+$n#$n<(ns)mo>&$#x2323;</(ns)mo>$-$n</(ns)munder>$n";
    19 => "embFROWN", #  over-arc, concave downward
    20 => "embSMILE", #  over-arc, concave upward
    31 => "embU_FROWN", #  under arc (ends point down)
    32 => "embU_SMILE", #  under arc (ends point up)
    -->
    <!-- Arcs -->

    <xsl:template match="embell[embell='embFROWN']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2322;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="embell[embell='embSMILE']">
        <mover accent="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2323;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="embell[embell='embU_FROWN']">
        <munder accentunder="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2322;</mo>
        </munder>
    </xsl:template>

    <xsl:template match="embell[embell='embU_SMILE']">
        <munder accentunder="true">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
            <mo>&#x2323;</mo>
        </munder>
    </xsl:template>

    <!--
    enot = "<(ns)menclose notation='updiagonalstrike'>$+$n#$-$n</(ns)menclose>$n";
    estrike = "<(ns)menclose notation='updiagonalstrike downdiagonalstrike'>$+$n#$-$n</(ns)menclose>$n";
    estrike/m = "<(ns)menclose notation='horizontalstrike'>$+$n#$-$n</(ns)menclose>$n";
    estrike/up = "<(ns)menclose notation='updiagonalstrike'>$+$n#$-$n</(ns)menclose>$n";
    estrike/dn = "<(ns)menclose notation='downdiagonalstrike'>$+$n#$-$n</(ns)menclose>$n";

    10 => "embNOT", #  diagonal slash through character
    21 => "embX_BARS", # double diagonal bars
    16 => "embMBAR", # mid-height horizontal bar
    22 => "embUP_BAR", # bottom-left to top-right diagonal bar
    23 => "embDOWN_BAR", # top-left to bottom-right diagonal bar
    -->
    <!-- Strikes -->

    <xsl:template match="embell[embell='embNOT']">
        <menclose notation="updiagonalstrike">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
        </menclose>
    </xsl:template>


    <xsl:template match="embell[embell='embX_BARS']">
        <menclose notation="updiagonalstrike downdiagonalstrike">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
        </menclose>
    </xsl:template>


    <xsl:template match="embell[embell='embMBAR']">
        <menclose notation="horizontalstrike">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
        </menclose>
    </xsl:template>


    <xsl:template match="embell[embell='embUP_BAR']">
        <menclose notation="updiagonalstrike">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
        </menclose>
    </xsl:template>


    <xsl:template match="embell[embell='embDOWN_BAR']">
        <menclose notation="downdiagonalstrike">
            <xsl:apply-templates select="(char | mn | mo | mtext | mi)[1]"/>
        </menclose>
    </xsl:template>

</xsl:stylesheet>
