<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet 
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:mml="http://www.w3.org/1998/Math/MathML"
    xmlns:tr="http://transpect.io"
    version="1.0">

  <!-- 🔥 IMPORT PHẢI ĐỨNG ĐÂY -->
  <xsl:import href="identity.xsl"/>
  <xsl:import href="util/symbol-map-base-uri-to-name.xsl"/>

  <!-- Load fontmaps -->
<!-- Load all fontmap XML files manually (XSLT 1.0 compatible) -->
<xsl:variable name="font-maps">
  <xsl:copy-of select="document('fontmaps/xmlcatalog/catalog.xml')"/>
  <xsl:copy-of select="document('fontmaps/Test.xml')"/>
  <xsl:copy-of select="document('fontmaps/ArialMT+1.xml')"/>
  <xsl:copy-of select="document('fontmaps/Euclid_Extra.xml')"/>
  <xsl:copy-of select="document('fontmaps/Euclid_Fraktur.xml')"/>
  <xsl:copy-of select="document('fontmaps/Euclid_Math_One.xml')"/>
  <xsl:copy-of select="document('fontmaps/Euclid_Math_Two.xml')"/>
  <xsl:copy-of select="document('fontmaps/Euclid_Symbol.xml')"/>
  <xsl:copy-of select="document('fontmaps/Lucida_Bright_Math_Extension.xml')"/>
  <xsl:copy-of select="document('fontmaps/Lucida_Bright_Math_Italic.xml')"/>
  <xsl:copy-of select="document('fontmaps/Lucida_Bright_Math_Symbol.xml')"/>
  <xsl:copy-of select="document('fontmaps/Marlett.xml')"/>
  <xsl:copy-of select="document('fontmaps/Math1.xml')"/>
  <xsl:copy-of select="document('fontmaps/MathType_MTCode.xml')"/>
  <xsl:copy-of select="document('fontmaps/Monotype_Sorts.xml')"/>
  <xsl:copy-of select="document('fontmaps/MT_Extra.xml')"/>
  <xsl:copy-of select="document('fontmaps/MT_Symbol.xml')"/>
  <xsl:copy-of select="document('fontmaps/Origin.xml')"/>
  <xsl:copy-of select="document('fontmaps/Symbol.xml')"/>
  <xsl:copy-of select="document('fontmaps/TimesNewRomanPSMT+1.xml')"/>
  <xsl:copy-of select="document('fontmaps/UniversalMath1_BT.xml')"/>
  <xsl:copy-of select="document('fontmaps/VDESONDE.xml')"/>
  <xsl:copy-of select="document('fontmaps/Webdings.xml')"/>
  <xsl:copy-of select="document('fontmaps/Wingdings.xml')"/>
  <xsl:copy-of select="document('fontmaps/Wingdings_2.xml')"/>
  <xsl:copy-of select="document('fontmaps/Wingdings_3.xml')"/>
  <xsl:copy-of select="document('fontmaps/WP_Greek_Century.xml')"/>
  <xsl:copy-of select="document('fontmaps/WP_Greek_Courier.xml')"/>
  <xsl:copy-of select="document('fontmaps/WP_Greek_Helve.xml')"/>
  <xsl:copy-of select="document('fontmaps/WP_IconicSymbolsA.xml')"/>
  <xsl:copy-of select="document('fontmaps/WP_MathA.xml')"/>
  <xsl:copy-of select="document('fontmaps/ZWAdobeF.xml')"/>
</xsl:variable>

  <!-- Key -->
  <xsl:key name="symbol-by-number" match="symbol" use="translate(@number,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>

  <!-- Text char list -->
  <xsl:variable name="text-chars">
    <char>ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ</char>
  </xsl:variable>

  <!-- Main -->
  <xsl:template match="mml:*[text()]" mode="map-fonts">

    <xsl:variable name="font-pos" select="translate(@font-position,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
    <xsl:variable name="fontfamily" select="@fontfamily"/>

    <!-- lookup -->
    <xsl:variable name="symbol">
      <xsl:choose>
        <xsl:when test="$fontfamily">
          <xsl:variable name="map" select="$font-maps/*[tr:symbol-map-base-uri-to-name(.) = $fontfamily][1]"/>
          <xsl:value-of select="key('symbol-by-number', $font-pos, $map)/@char"/>
        </xsl:when>
        <xsl:otherwise/>
      </xsl:choose>
    </xsl:variable>

    <!-- is text? -->
    <xsl:variable name="is-text">
      <xsl:choose>
        <xsl:when test="contains($text-chars, substring(text(),1,1))">true</xsl:when>
        <xsl:otherwise>false</xsl:otherwise>
      </xsl:choose>
    </xsl:variable>

    <!-- output -->
    <xsl:element name="{ 
        substring-before(
            concat('mtext:', name()),
            ':'[not($is-text='true')]
        ) 
    }" namespace="http://www.w3.org/1998/Math/MathML">

      <!-- copy attributes except font-position -->
      <xsl:for-each select="@*">
        <xsl:if test="name()!='font-position'">
          <xsl:attribute name="{name()}"><xsl:value-of select="."/></xsl:attribute>
        </xsl:if>
      </xsl:for-each>

      <!-- mathvariant -->
      <xsl:if test="$is-text='true'">
        <xsl:attribute name="mathvariant">
          <xsl:choose>
            <xsl:when test="@mathvariant"><xsl:value-of select="@mathvariant"/></xsl:when>
            <xsl:when test="self::mml:mi and string-length(text())=1">italic</xsl:when>
            <xsl:otherwise>normal</xsl:otherwise>
          </xsl:choose>
        </xsl:attribute>
      </xsl:if>

      <!-- character output -->
      <xsl:choose>
        <xsl:when test="string-length($symbol)&gt;0">
          <xsl:value-of select="$symbol"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="."/>
        </xsl:otherwise>
      </xsl:choose>

    </xsl:element>
  </xsl:template>

  <!-- Ignore default font families -->
  <xsl:template match="@fontfamily[
        .='Times New Roman'
        or .='Symbol'
        or .='Courier New'
        or .='MT Extra'
      ]" mode="map-fonts"/>

  <xsl:template match="mml:*[@default-font]/@fontfamily | @default-font" mode="map-fonts"/>
  
</xsl:stylesheet>
