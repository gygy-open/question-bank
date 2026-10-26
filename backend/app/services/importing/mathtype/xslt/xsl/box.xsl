<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

     <!-- Boxes -->

    <xsl:template match="tmpl[selector='tmBOX' and (variation='tvBX_TOP' and variation='tvBX_LEFT')]">
        <menclose notation="top left">
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </menclose>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmBOX' and (variation='tvBX_TOP' and variation='tvBX_RIGHT')]">
        <menclose notation="actuarial">
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </menclose>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmBOX' and (variation='tvBX_BOTTOM' and variation='tvBX_LEFT')]">
        <menclose notation="bottom left">
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </menclose>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmBOX' and (variation='tvBX_BOTTOM' and variation='tvBX_RIGHT')]">
        <menclose notation="bottom right">
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </menclose>
    </xsl:template>

     <xsl:template match="tmpl[selector='tmBOX' and variation='tvBX_TOP' and variation='tvBX_BOTTOM' and variation='tvBX_LEFT' and variation='tvBX_RIGHT']">
        <menclose notation="box">
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </menclose>
    </xsl:template>

</xsl:stylesheet>
