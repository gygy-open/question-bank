<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

    <!-- The translation of a pile using this form of translation string is performed with the following steps:

    The <start> part of the translation string is output;
    The first line is translated;
    The <repeat> part of the translation string is output;
    The next line is translated;
    If there are any more lines, go back to Step 3. Otherwise, continue with the next step;
    The <end> part of the translation string is output.
    -->
    <xsl:template match="pile">
        <mtable>
            <xsl:apply-templates select="slot" mode="wrap"/>
        </mtable>
    </xsl:template>

    <xsl:template match="pile[halign='left']">
        <mtable columnalign="left">
            <xsl:apply-templates select="slot" mode="wrap"/>
        </mtable>
    </xsl:template>

    <xsl:template match="pile/slot" mode="wrap">
        <mtr>
            <mtd>
                <xsl:apply-templates select="."/>
            </mtd>
        </mtr>
    </xsl:template>

    <xsl:template match="pile[halign='right']">
        <mtable columnalign="right">
            <xsl:apply-templates select="slot" mode="wrap"/>
        </mtable>
    </xsl:template>

    <xsl:template match="pile[halign='dec']">
        <mtable groupalign="decimalpoint">
            <xsl:apply-templates select="slot" mode="wrap"/>
        </mtable>
    </xsl:template>

    <xsl:template match="pile[halign='al']">
        <mtable>
            <xsl:apply-templates select="slot" mode="wrap"/>
        </mtable>
    </xsl:template>

</xsl:stylesheet>
