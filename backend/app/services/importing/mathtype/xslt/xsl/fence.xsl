<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

    <!-- Fences -->
    <xsl:template match="tmpl[selector='tmPAREN']">
        <mrow>
            <mo>(</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>)</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmPAREN' and variation='tvFENCE_L' and not(variation='tvFENCE_R')]">
        <mrow><mo>(</mo> <xsl:apply-templates select="slot[1] | pile[1]"/></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmPAREN' and variation='tvFENCE_R' and not(variation='tvFENCE_L')]">
        <mrow> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>)</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBRACK']">
        <mrow>
            <mo>[</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>]</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBRACE']">
        <mrow>
            <mo>{</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>}</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmANGLE']">
        <mrow><mo>&#x2329;</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>&#x232A;</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmANGLE' and variation='tvFENCE_L' and not(variation='tvFENCE_R')]">
        <mrow>
            <mo>&#x2329;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmANGLE' and variation='tvFENCE_R' and not(variation='tvFENCE_L')]">
        <mrow>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>&#x232A;</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBAR']">
        <mrow><mo>|</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>|</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBAR' and variation='tvFENCE_L' and not(variation='tvFENCE_R')]">
        <mrow>
            <mo>|</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBAR' and variation='tvFENCE_R' and not(variation='tvFENCE_L')]">
        <mrow>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>|</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmFLOOR']">
        <mrow><mo>&#x230A;</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>&#x230B;</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmCEILING']">
        <mrow><mo>&#x2308;</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>&#x2309;</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTERVAL' and variation='tvINTV_LBLB']">
        <mrow> <mo>[</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>[</mo> </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTERVAL' and variation='tvINTV_RBRB']">
        <mrow><mo>]</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>]</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTERVAL' and variation='tvINTV_RBLB']">
        <mrow><mo>]</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>[</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTERVAL' and variation='tvINTV_LBRP']">
        <mrow><mo>[</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>)</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTERVAL' and variation='tvINTV_LPRB']">
        <mrow><mo>(</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>]</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBRACK' and variation='tvFENCE_L' and not(variation='tvFENCE_R')]">
        <mrow> <mo>[</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBRACK' and variation='tvFENCE_R' and not(variation='tvFENCE_L')]">
        <mrow><xsl:apply-templates select="slot[1] | pile[1]"/> <mo>]</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBRACE' and variation='tvFENCE_L' and not(variation='tvFENCE_R')]">
        <mrow><mo>{</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmBRACE' and variation='tvFENCE_R' and not(variation='tvFENCE_L')]">
        <mrow><xsl:apply-templates select="slot[1] | pile[1]"/> <mo>}</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmDIRAC']">
        <mrow>
            <mo>&#x2329;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>|</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <mo>&#x232A;</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmDIRAC' and variation='tvDI_RIGHT' and not(variation='tvDI_LEFT')]">
        <mrow>
            <mo>|</mo>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <mo>&#x232A;</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmDIRAC' and variation='tvDI_LEFT' and not(variation='tvDI_RIGHT')]">
        <mrow>
            <mo>&#x2329;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>|</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmDBAR']">
        <mrow><mo>&#x2016;</mo> <xsl:apply-templates select="slot[1] | pile[1]"/> <mo>&#x2016;</mo></mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmDBAR' and variation='tvFENCE_L' and not(variation='tvFENCE_R')]">
        <mrow>
            <mo>&#x2016;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmDBAR' and variation='tvFENCE_R' and not(variation='tvFENCE_L')]">
        <mrow>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>&#x2016;</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmOBRACK']">
        <mrow>
            <mo>&#x301A;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>&#x301B;</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmOBRACK' and variation='tvFENCE_L' and not(variation='tvFENCE_R')]">
        <mrow>
            <mo>&#x301A;</mo>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmOBRACK' and variation='tvFENCE_R' and not(variation='tvFENCE_L')]">
        <mrow>
            <xsl:apply-templates select="slot[1] | pile[1]"/>
            <mo>&#x301B;</mo>
        </mrow>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmHBRACE']">
        <munder>
            <munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
                <mo stretchy="true">&#xFE38;</mo>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmHBRACE' and variation='tvHB_TOP']">
        <mover>
            <mover>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
                <mo stretchy="true">&#xFE37;</mo>
            </mover>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </mover>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmHBRACK']">
        <munder>
            <munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
                <mo stretchy="true">&#x23B5;</mo>
            </munder>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </munder>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmHBRACK' and variation='tvHB_TOP']">
        <mover>
            <mover>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
                <mo stretchy="true">&#x23B4;</mo>
            </mover>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </mover>
    </xsl:template>



</xsl:stylesheet>
