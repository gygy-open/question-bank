# fontmaps
Mappings for non-Unicode fonts to Unicode

## What is a fontmap?
A fontmap defines a relation from one encoding to another for each character in the initial font.  
In our case, the characters come from non-unicode-encodings and should be translated to unicode.

Here is an example why a fontmap is needed:  
For the greek character "phi", there exists variations of notation: φ, U+03C6 and ϕ, U+03D5.  
In Mathtype Equation Format, the character can be saved with the MTCode/Unicode U+03D5, but be displayed with a font that makes it look like U+03C6. (Symbol font, font-position 6A, according to http://www.dessci.com/en/support/mathtype/tech/encodings/symbol.htm)  
Since the meaning of both phi could differ, it is necessary that the symbol that looks like U+03C6 really IS the unicode-character U+03C6.  
A fontmap for the font 'Symbol' will take the character with font-position 6A and output the character U+03C6.

## How to get a fontmap?

### Find it somewhere
This  repository contains some fontmaps for common fonts like 'Symbol' or 'Wingdings'.  
If none is available, it must be created (see below), and should be put here for others to use.

### Create it

This is the part taking the longest time.  
Fortunately once finished, fontmaps can be reused for all documents using the font.  
For each character in your font, you repeat these steps:
1. Find a suiting unicode character.
2. Create an entry in the fontmap for your font.

There are 3 cases when initally mapping a character:
 1. The original encoding and unicode-position are identical, nothing needs to be done.
 2. There exists an identical looking unicode-character, you can directly map it.
 3. There is no identical looking unicode-character. In this case, you have to decide which unicode-character would be the best substitute in your situation. (This is the most tricky part)

You can take a look at the docx2hub/fontmaps for sample mappings.

A fontmap consists of an element `<symbols>`.  
The name of the font will be solved in this order until one is matched:
If there is an attribute 'mathtype-name', it is the font-name (Example: "Symbol", name as displayed in the font selector)  
If there is an attribute 'docx-name', it is the font-name.  
Else the font-name is extracted from the file-name(its base-uri()), where _ are replaced by spaces.  
Thus, the file Mathype_MTCode.xml will be recognized as font-name 'Mathtype MTCode' if there are no attributes set in the file.  
The child-elements are named `<symbol>`, each containing only attributes
  * attribute number: the font-position with 4 digits, left-padded with zero's (Example: "006A" for phi)
  * attribute char: the char as a numeric entity (Example: "&amp;#x3c6;")

### What happens when no fontmapping is available for a character?

There are several outcomes when a concrete mapping is missing:  
The character will be likely output with his font-codepoint misinterpreted as unicode.  
It may lead to varying appearance (like in the example with phi), may severely differ from the input or be in a unicode region which is not displayable (unicode private use area).  

### What happens when multiple fontmaps for the same font are loaded?

Custom-font-maps from users have precedence.  When multiple fontmaps for the same font are provided by the custom-font-maps input port, the last of them is used. To override a default fontmap from docx2hub, you can simply provide your custom one.  
There is no way to partially override only a single symbol, when providing a custom font map it is exclusively used.
