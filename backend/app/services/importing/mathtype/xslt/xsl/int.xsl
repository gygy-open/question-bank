<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="1.0">

    <!-- Integral operators -->
    <!-- The order is important because it would be very messy to address all
         conditions for each template, and so we rely on the fact that the
         last matching rule has precedence -->

    <xsl:template match="tmpl[selector='tmINTOP']">
        <msubsup>
            <mstyle mathsize="140%" displaystyle="true"><xsl:apply-templates select="slot[4] | pile[4]"/></mstyle>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
            <xsl:apply-templates select="slot[3] | pile[3]"/>
        </msubsup>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTOP' and variation='tvBO_UPPER']">
        <msup>
            <mstyle mathsize="140%" displaystyle="true"><xsl:apply-templates select="slot[4] | pile[4] | pile[4]"/></mstyle>
            <xsl:apply-templates select="slot[3] | pile[3]"/>
        </msup>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTOP' and variation='tvBO_LOWER' and not(variation='tvBO_UPPER')]">
        <msub>
            <mstyle mathsize="140%" displaystyle="true"><xsl:apply-templates select="slot[4] | pile[4]"/></mstyle>
            <xsl:apply-templates select="slot[2] | pile[2]"/>
        </msub>
    </xsl:template>

    <!-- Integrals -->

    <xsl:template match="tmpl[selector='tmINTEG']">
        <mstyle displaystyle="true">
            <mrow>
                <msubsup>
                    <mo>&#x222B;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                    <xsl:apply-templates select="slot[3] | pile[3]"/>
                </msubsup>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow><mo>&#x222B;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munderover>
                    <mo>&#x222B;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                    <xsl:apply-templates select="slot[3] | pile[3]"/>
                </munderover>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND']">
        <mstyle displaystyle="true">
            <mrow>
                <msubsup>
                    <mo stretchy="true">&#x222B;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                    <xsl:apply-templates select="slot[3] | pile[3]"/>
                </msubsup>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_1' and variation='tvBO_LOWER' and not(variation='tvBO_UPPER')]">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo>&#x222B;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo>&#x222C;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo>&#x222C;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo>&#x222D;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo>&#x222E;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_CW_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo>&#x2232;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_CCW_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo>&#x2233;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo>&#x222E;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvBO_SUM' and variation='tvBO_LOWER' and not(variation='tvBO_UPPER')]">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo>&#x222B;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munderover>
                    <mo stretchy="true">&#x222B;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                    <xsl:apply-templates select="slot[3] | pile[3]"/>
                </munderover>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo>&#x222C;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo>&#x222F;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_EXPAND']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo stretchy="true">&#x222C;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>

        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_EXPAND' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo stretchy="true">&#x222C;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo>&#x222E;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_CW_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo>&#x2232;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_CCW_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo>&#x2233;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo>&#x222D;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo>&#x2230;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_EXPAND']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo stretchy="true">&#x222D;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_CW_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo stretchy="true">&#x2232;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_CCW_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo stretchy="true">&#x2233;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo stretchy="true">&#x222E;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo>&#x222F;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_EXPAND' and variation='tvINT_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo stretchy="true">&#x222F;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo>&#x222F;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo>&#x222D;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_EXPAND' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo stretchy="true">&#x222D;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo>&#x2230;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_EXPAND' and variation='tvINT_LOOP']">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo stretchy="true">&#x2230;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_CW_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo>&#x2232;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_CCW_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo>&#x2233;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvBO_LOWER' and not(variation='tvBO_UPPER')]">
        <mstyle displaystyle="true">
            <mrow>
                <msub>
                    <mo stretchy="true">&#x222B;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </msub>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo stretchy="true">&#x222E;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_CCW_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo stretchy="true">&#x2233;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_CW_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo stretchy="true">&#x2232;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo stretchy="true">&#x222B;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_EXPAND' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo stretchy="true">&#x222C;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_EXPAND' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo stretchy="true">&#x222D;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvBO_SUM' and variation='tvBO_LOWER' and not(variation='tvBO_UPPER')]">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo stretchy="true">&#x222B;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo>&#x2230;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_EXPAND' and variation='tvINT_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo stretchy="true">&#x2230;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_CCW_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo stretchy="true">&#x2233;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo stretchy="true">&#x222E;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_EXPAND' and variation='tvINT_LOOP' and variation='tvBO_SUM']">
        <mstyle displaystyle="true">
            <mrow>
                <munder>
                    <mo stretchy="true">&#x222F;</mo>
                    <xsl:apply-templates select="slot[2] | pile[2]"/>
                </munder>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_EXPAND' and variation='tvINT_CW_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo stretchy="true">&#x2232;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>


    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_2' and variation='tvINT_EXPAND' and variation='tvINT_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo stretchy="true">&#x222F;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>

    <xsl:template match="tmpl[selector='tmINTEG' and variation='tvINT_3' and variation='tvINT_EXPAND' and variation='tvINT_LOOP' and (not(variation='tvBO_UPPER') and not(variation='tvBO_LOWER'))]">
        <mstyle displaystyle="true">
            <mrow>
                <mo stretchy="true">&#x2230;</mo>
                <xsl:apply-templates select="slot[1] | pile[1]"/>
            </mrow>
        </mstyle>
    </xsl:template>
</xsl:stylesheet>
