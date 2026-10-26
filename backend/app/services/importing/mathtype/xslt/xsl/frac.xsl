<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

     <!-- Fractions -->

     <xsl:template match="tmpl[selector='tmFRACT']">
        <mfrac>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </mfrac>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmFRACT' and variation='tvFR_SLASH']">
        <mfrac bevelled="true">
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </mfrac>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmFRACT' and variation='tvFR_SMALL']">
        <mstyle scriptlevel="+1">
            <mfrac>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </mfrac>
        </mstyle>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmFRACT' and variation='tvFR_SLASH' and variation='tvFR_BASE']">
        <mrow><xsl:apply-templates select="slot[1] | pile[1]"/><mo>/</mo><xsl:apply-templates select="slot[2] | pile[2]"/></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmFRACT' and variation='tvFR_SLASH' and variation='tvFR_SMALL']">
        <mstyle scriptlevel="+1">
            <mfrac bevelled="true">
                <xsl:apply-templates select="slot[1] | pile[1]"/>
                <xsl:apply-templates select="slot[2] | pile[2]"/>
            </mfrac>
        </mstyle>
    </xsl:template>

</xsl:stylesheet>
