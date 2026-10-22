<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet 
    version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:tr="http://transpect.io">

  <!-- 
      XSLT 1.0 does not support custom functions.
      So we emulate tr:symbol-map-base-uri-to-name() as a named template.
      The calling code must use:
      
      <xsl:call-template name="tr:symbol-map-base-uri-to-name">
         <xsl:with-param name="symbols" select="..."/>
      </xsl:call-template>
  -->

  <xsl:template name="tr:symbol-map-base-uri-to-name">
    <xsl:param name="symbols"/>

    <!-- 1️⃣ Nếu file có attribute mathtype-name → dùng cái đó -->
    <xsl:variable name="mtname" select="$symbols/symbols/@mathtype-name"/>

    <xsl:choose>

      <xsl:when test="string-length($mtname) &gt; 0">
        <xsl:value-of select="$mtname"/>
      </xsl:when>

      <!-- 2️⃣ Lấy tên file từ base-uri() bằng XSLT 1.0 -->
      <xsl:otherwise>
        <xsl:variable name="uri" select="base-uri($symbols/symbols)"/>

        <!-- Lấy phần sau dấu "/" cuối -->
        <xsl:variable name="afterPath">
          <xsl:choose>
            <xsl:when test="contains($uri, '/')">
              <xsl:value-of select="substring-after($uri, substring-before($uri,';'))"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="$uri"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:variable>

        <!-- Cắt .xml -->
        <xsl:variable name="filename">
          <xsl:choose>
            <xsl:when test="contains($afterPath, '.xml')">
              <xsl:value-of select="substring-before($afterPath, '.xml')"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="$afterPath"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:variable>

        <!-- Replace '_' bằng space (XSLT1 version) -->
        <xsl:variable name="clean">
          <xsl:value-of 
            select="translate($filename, '_', ' ')"/>
        </xsl:variable>

        <xsl:value-of select="$clean"/>
      </xsl:otherwise>

    </xsl:choose>

  </xsl:template>

</xsl:stylesheet>
