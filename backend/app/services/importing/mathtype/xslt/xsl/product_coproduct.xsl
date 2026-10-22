<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

    <!-- Product and coproduct -->

    <xsl:template match="tmpl[selector='tmPROD']">
        <mstyle displaystyle="true">
            <munderover>
                <mo>&#x220F;</mo>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
                <xsl:apply-templates select="slot[3] | pile[3]"/>
            </munderover>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmPROD' and variation='tvBO_LOWER' and not(variation='tvBO_UPPER')]">
        <mstyle displaystyle="true">
            <munder>
                <mo>&#x220F;</mo>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmPROD' and (not(variation='tvBO_UPPER')  and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mo>&#x220F;</mo> <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmPROD' and not(variation='tvBO_SUM')  and variation='tvBO_LOWER']">
        <mstyle displaystyle="true">
            <msub>
                <mo>&#x220F;</mo>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </msub>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmPROD' and not(variation='tvBO_SUM') ]">
        <mstyle displaystyle="true">
            <msubsup>
                <mo>&#x220F;</mo>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
                <xsl:apply-templates select="slot[3] | pile[3]"/>
            </msubsup>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmCOPROD']">
        <mstyle displaystyle="true">
            <munderover>
                <mo>&#x2210;</mo>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
                <xsl:apply-templates select="slot[3] | pile[3]"/>
            </munderover>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmCOPROD' and not(variation='tvBO_SUM') ]">
        <mstyle displaystyle="true">
            <msubsup>
                <mo>&#x2210;</mo>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
                <xsl:apply-templates select="slot[3] | pile[3]"/>
            </msubsup>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmCOPROD' and (not(variation='tvBO_UPPER')  and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mo>&#x2210;</mo> <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmCOPROD' and variation='tvBO_LOWER' and not(variation='tvBO_UPPER')]">
        <mstyle displaystyle="true">
            <munder>
                <mo>&#x2210;</mo>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmCOPROD' and not(variation='tvBO_SUM')  and variation='tvBO_LOWER' and not(variation='tvBO_UPPER')]">
        <mstyle displaystyle="true">
            <msub>
                <mo>&#x2210;</mo>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </msub>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mstyle>
    </xsl:template>



</xsl:stylesheet>
