<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">
    <xsl:template match="/">
        <xsl:apply-templates select=".//mtef" />
    </xsl:template>

    <xsl:template match="mtef[equation_options = 'inline']">
        <math>
            <xsl:apply-templates select="pile | slot"/>
        </math>
    </xsl:template>

    <xsl:template match="mtef[equation_options = 'block']">
        <math display="block">
            <xsl:apply-templates select="pile | slot"/>
        </math>
    </xsl:template>

    <xsl:template match="slot">
        <mrow>
            <xsl:apply-templates/>
        </mrow>
    </xsl:template>

    <!-- Non-empty text nodes -->
 <xsl:template match="text()[normalize-space()]">
  <mtext><xsl:value-of select="."/></mtext>
</xsl:template>


    <xsl:template match="*" />

    <xsl:include href="xsl/int.xsl" />
    <xsl:include href="xsl/lim.xsl" />
    <xsl:include href="xsl/frac.xsl" />
    <xsl:include href="xsl/pile.xsl" />
    <xsl:include href="xsl/char.xsl" />
    <xsl:include href="xsl/embellishment.xsl" />
    <xsl:include href="xsl/subsup.xsl"/>
    <xsl:include href="xsl/sum.xsl"/>
    <xsl:include href="xsl/product_coproduct.xsl"/>
    <xsl:include href="xsl/union_intersection.xsl"/>
    <xsl:include href="xsl/box.xsl" />
    <xsl:include href="xsl/fence.xsl" />
    <xsl:include href="xsl/arrow.xsl"/>
    <xsl:include href="xsl/matrix.xsl"/>
    <xsl:include href="xsl/long_embellishment.xsl"/>
    <xsl:include href="xsl/long_division.xsl"/>
    <xsl:include href="xsl/root.xsl" />
    <xsl:include href="xsl/map-fonts.xsl" />
</xsl:stylesheet>
