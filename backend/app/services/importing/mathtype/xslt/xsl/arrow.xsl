<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

    <!-- Arrows -->
    <xsl:template match="tmpl[selector='tmARROW']">
        <mover>
            <mo>&#x2192;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_LEFT']">
        <mover>
            <mo>&#x2190;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x2192;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_TOPBOTTOM']">
        <munderover>
            <mo>&#x2192;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE']">
        <mover>
            <mo>&#x21C4;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_LEFT' and variation='tvAR_RIGHT' )]">
        <mover>
            <mo>&#x2194;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_LEFT' and variation='tvAR_TOPBOTTOM']">
        <munderover>
            <mo>&#x2190;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_TOPBOTTOM']">
        <munderover>
            <mo>&#x21C4;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_LOS']">
        <mover>
            <munder accentunder="true">
                <mstyle scriptlevel="-1"><mo>&#x2192;</mo></mstyle>
                <mstyle scriptlevel="+1"><mo>&#x2190;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_SOL']">
        <mover>
            <munder accentunder="true">
                <mstyle scriptlevel="+1"><mo>&#x2192;</mo></mstyle>
                <mstyle scriptlevel="-1"><mo>&#x2190;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON']">
        <mover>
            <mo>&#x21CC;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_LEFT' and variation='tvAR_RIGHT' ) and variation='tvAR_TOPBOTTOM']">
        <munderover>
            <mo>&#x2194;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON']">
        <mover>
            <mo>&#x21CC;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_LOS' and variation='tvAR_TOPBOTTOM']">
        <munderover accentunder="true">
            <mstyle scriptlevel="-1"><mo>&#x2192;</mo></mstyle>
            <munder>
                <mstyle scriptlevel="+1"><mo>&#x2190;</mo></mstyle>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_SOL' and variation='tvAR_TOPBOTTOM']">
        <munderover accentunder="true">
            <mstyle scriptlevel="+1"><mo>&#x2192;</mo></mstyle>
            <munder>
                <mstyle scriptlevel="-1"><mo>&#x2190;</mo></mstyle>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_SOL']">
        <mover>
            <munder accentunder="true">
                <mstyle scriptlevel="+1"><mo>&#x21C0;</mo></mstyle>
                <mstyle scriptlevel="-1"><mo>&#x21BD;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_LOS']">
        <mover>
            <munder accentunder="true">
                <mstyle scriptlevel="-1"><mo>&#x21C0;</mo></mstyle>
                <mstyle scriptlevel="+1"><mo>&#x21BD;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_TOPBOTTOM']">
        <munderover>
            <mo>&#x21CC;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_LOS' and variation='tvAR_TOPBOTTOM']">
        <munderover accentunder="true">
            <mstyle scriptlevel="-1"><mo>&#x21C0;</mo></mstyle>
            <munder>
                <mstyle scriptlevel="+1"><mo>&#x21BD;</mo></mstyle>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_SOL' and variation='tvAR_TOPBOTTOM']">
        <munderover accentunder="true">
            <mstyle scriptlevel="+1"><mo>&#x21C0;</mo></mstyle>
            <munder>
                <mstyle scriptlevel="-1"><mo>&#x21BD;</mo></mstyle>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </munderover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_LEFT' and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x2190;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_LEFT' and variation='tvAR_RIGHT' ) and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x2194;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x21C4;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_LOS' and variation='tvAR_BOTTOM']">
        <munder>
            <munder accentunder="true">
                <mstyle scriptlevel="-1"><mo>&#x2192;</mo></mstyle>
                <mstyle scriptlevel="+1"><mo>&#x2190;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_SOL' and variation='tvAR_BOTTOM']">
        <munder>
            <munder accentunder="true">
                <mstyle scriptlevel="+1"><mo>&#x2192;</mo></mstyle>
                <mstyle scriptlevel="-1"><mo>&#x2190;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x21CC;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_LOS' and variation='tvAR_BOTTOM']">
        <munder>
            <munder accentunder="true">
                <mstyle scriptlevel="-1"><mo>&#x21C0;</mo></mstyle>
                <mstyle scriptlevel="+1"><mo>&#x21BD;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_SOL' and variation='tvAR_BOTTOM']">
        <munder>
            <munder accentunder="true">
                <mstyle scriptlevel="+1"><mo>&#x21C0;</mo></mstyle>
                <mstyle scriptlevel="-1"><mo>&#x21BD;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_LEFT' and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x2190;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_LEFT' and variation='tvAR_RIGHT' ) and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x2194;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x21C4;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_LOS' and variation='tvAR_BOTTOM']">
        <munder>
            <munder accentunder="true">
                <mstyle scriptlevel="-1"><mo>&#x2192;</mo></mstyle>
                <mstyle scriptlevel="+1"><mo>&#x2190;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and variation='tvAR_DOUBLE' and variation='tvAR_SOL' and variation='tvAR_BOTTOM']">
        <munder>
            <munder accentunder="true">
                <mstyle scriptlevel="+1"><mo>&#x2192;</mo></mstyle>
                <mstyle scriptlevel="-1"><mo>&#x2190;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_BOTTOM']">
        <munder>
            <mo>&#x21CC;</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_LOS' and variation='tvAR_BOTTOM']">
        <munder>
            <munder accentunder="true">
                <mstyle scriptlevel="-1"><mo>&#x21C0;</mo></mstyle>
                <mstyle scriptlevel="+1"><mo>&#x21BD;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARROW' and (variation='tvAR_DOUBLE' or variation='tvAR_HARPOON') and variation='tvAR_HARPOON' and variation='tvAR_SOL' and variation='tvAR_BOTTOM']">
        <munder>
            <munder accentunder="true">
                <mstyle scriptlevel="+1"><mo>&#x21C0;</mo></mstyle>
                <mstyle scriptlevel="-1"><mo>&#x21BD;</mo></mstyle>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

</xsl:stylesheet>
