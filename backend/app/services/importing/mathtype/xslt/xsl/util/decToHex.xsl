<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:xs="http://www.w3.org/2001/XMLSchema"
                xmlns:tr="http://transpect.io"
                exclude-result-prefixes="xs"
                version="2.0">
  <xsl:function name="tr:decToHex" as="xs:string">
    <xsl:param name="dec" as="xs:decimal"/>
    <xsl:variable name="mod" select="1 + ($dec mod 16)"/>
    <xsl:variable name="char" select="substring('0123456789ABCDEF', $mod, 1)"/>
    <xsl:value-of
      select="
        concat(if ($dec - 16 gt 0) then
          tr:decToHex(floor($dec div 16))
        else
          if ($dec = 16) then
            1
          else
            '', $char)"
    />
    
  </xsl:function>

</xsl:stylesheet>
