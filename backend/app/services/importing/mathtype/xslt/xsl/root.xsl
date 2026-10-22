<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns="http://www.w3.org/1998/Math/MathML"
    exclude-result-prefixes="xs"
    version="1.0">

     <!-- Roots -->

  <xsl:template match="tmpl[selector = 'tmROOT'][variation = 'tvROOT_SQ']">
    <msqrt>
      <xsl:apply-templates select="slot[1] | pile[1]"/>
    </msqrt>
  </xsl:template>
  
  <xsl:template match="tmpl[selector = 'tmROOT'][variation = 'tvROOT_NTH']">
    <mroot>
      <xsl:apply-templates select="slot[1] | pile[1]"/>
      <xsl:apply-templates select="slot[2] | pile[2]"/>
    </mroot>
  </xsl:template>

</xsl:stylesheet>
