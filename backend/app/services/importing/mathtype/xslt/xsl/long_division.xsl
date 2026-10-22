<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

     <!-- Long division -->

     <xsl:template match="tmpl[selector='tmLDIV']">
        <mtable>
            <mtr>
                <mtd columnalign="right">
                    <xsl:apply-templates select="(slot | pile)[2]"/>
                </mtd>
            </mtr>
            <mtr>
                <mtd columnalign="right">
                    <menclose notation="longdiv">
                        <xsl:apply-templates select="(slot | pile)[1]"/>
                    </menclose>
                </mtd>
            </mtr>
        </mtable>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmLDIV' and not(variation='tvLD_UPPER')]">
        <menclose notation="longdiv">
            <xsl:apply-templates select="(slot | pile)[1]"/>
        </menclose>
    </xsl:template>

</xsl:stylesheet>
