<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

     <!-- Long embellishments -->

     <xsl:template match="tmpl[selector='tmTILDE']">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x2DC;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmARC']">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x2322;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmHAT']">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">^</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmJSTATUS']">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#xFE39;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmOBAR']">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#xAF;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmOBAR' and variation='tvBAR_DOUBLE']">
        <mover accent="true">
            <mover accent="true">
                <xsl:apply-templates select="(slot | pile)[1]"/>
                <mo stretchy="true">&#xAF;</mo>
            </mover>
            <mo stretchy="true">&#xAF;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmUBAR']">
        <munder accentunder="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">_</mo>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmUBAR' and variation='tvBAR_DOUBLE']">
        <munder accentunder="true">
            <munder accentunder="true">
                <xsl:apply-templates select="(slot | pile)[1]"/>
                <mo stretchy="true">_</mo>
            </munder>
            <mo stretchy="true">_</mo>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmVEC']">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x2192;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmVEC' and variation='tvVE_LEFT']">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x2190;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmVEC' and (variation='tvVE_LEFT' and variation='tvVE_RIGHT' )]">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x2194;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmVEC' and variation='tvVE_HARPOON']">
        <mover accent="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x21C0;</mo>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmVEC' and variation='tvVE_UNDER']">
        <munder accentunder="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x2192;</mo>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmVEC' and variation='tvVE_UNDER' and variation='tvVE_LEFT']">
        <munder accentunder="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x2190;</mo>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmVEC' and variation='tvVE_UNDER' and (variation='tvVE_LEFT' and variation='tvVE_RIGHT' )]">
        <munder accentunder="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x2194;</mo>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmVEC' and variation='tvVE_UNDER' and variation='tvVE_HARPOON']">
        <munder accentunder="true">
            <xsl:apply-templates select="(slot | pile)[1]"/>
            <mo stretchy="true">&#x21C1;</mo>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmSTRIKE']">
        <menclose notation="updiagonalstrike downdiagonalstrike">
            <xsl:apply-templates select="(slot | pile)[1]"/>
        </menclose>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmSTRIKE' and variation='tvST_HORIZ' and not(variation='tvST_UP' or variation='tvST_DOWN')]">
        <menclose notation="horizontalstrike">
            <xsl:apply-templates select="(slot | pile)[1]"/>
        </menclose>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmSTRIKE' and variation='tvST_UP' and not(variation='tvST_HORIZ' or variation='tvST_DOWN')]">
        <menclose notation="updiagonalstrike">
            <xsl:apply-templates select="(slot | pile)[1]"/>
        </menclose>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmSTRIKE' and variation='tvST_DOWN' and not(variation='tvST_UP' or variation='tvST_HORIZ')]">
        <menclose notation="downdiagonalstrike">
            <xsl:apply-templates select="(slot | pile)[1]"/>
        </menclose>
    </xsl:template>
</xsl:stylesheet>
