<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
					 xmlns:xs="http://www.w3.org/2001/XMLSchema"
                xmlns:tr="http://transpect.io"
					 exclude-result-prefixes="xs"
					 version="2.0">
  <xsl:function name="tr:hexToDec">
    <xsl:param name="hex"/>
    <xsl:variable name="dec"
						select="string-length(substring-before('0123456789ABCDEF', substring($hex,1,1)))"/>
    <xsl:choose>
      <xsl:when test="matches($hex, '([0-9]*|[A-F]*)')">
        <xsl:value-of
				select="if ($hex = '') then 0
						  else $dec * tr:power(16, string-length($hex) - 1) + tr:hexToDec(substring($hex,2))"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:message>Provided value is not hexadecimal...</xsl:message>
        <xsl:value-of select="$hex"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:function>

  <xsl:function name="tr:power">
    <xsl:param name="base"/>
    <xsl:param name="exp"/>
    <xsl:sequence
        select="if ($exp lt 0) then tr:power(1.0 div $base, -$exp)
                else if ($exp eq 0)
                then 1e0
                else $base * tr:power($base, $exp - 1)"
		  />
  </xsl:function>
</xsl:stylesheet>
