<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

     <!-- Limits -->

    <xsl:template match="tmpl[selector='tmLIM']">
        <munder>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmLIM' and variation='tvBO_UPPER']">
        <mover>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <xsl:apply-templates select="slot[3] | pile[3]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmLIM' and (variation='tvBO_UPPER' and variation='tvBO_LOWER')]">
        <munderover>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <xsl:apply-templates select="slot[3] | pile[3]"/>
        </munderover>
    </xsl:template>

</xsl:stylesheet>
