# AI Development Context

## Project Overview
Word Document Formatter (NcFormatter) - A web application that converts Word documents to formatted HTML with company-specific formatting rules.

## Key Features Implemented
- Drag & drop Word document processing
- Company-specific variable handling: `{[TAG]}`, `Money()`, `Math()`, `Compress()`
- Custom formatting for legal documents (breach notices, etc.)
- HTML generation with proper table formatting and spacing

## Document Processing Rules
1. **Paragraph Formatting**: Each logical paragraph wrapped in `<div>...</div>`
2. **Variable Syntax**: 
   - `{[TAG]}` for basic variables
   - `{[plsMatrix.CompanyName]}` for company variables
   - `{Money({[TAG]})}` for monetary values
   - `{Math({[TAG1]} + {[TAG2]} - {[TAG3]}|Money)}` for calculations
3. **Table Formatting**: Full-width tables with proper cell alignment
4. **Address Compression**: `Compress({[TAG1]}|{[TAG2]})` for multiline addresses

## Sample Documents
- `LM060.txt`: 327-line legal document with complex formatting
- `SD002.txt`: Breach notice template
- Various .docx files for testing

## Development Notes
- Uses vanilla JavaScript (no external dependencies)
- Implements security measures (HTML escaping, XSS prevention)
- Ready for integration with mammoth.js for real Word document processing
- All formatting rules tested and working

## Next Steps
1. Integrate mammoth.js for actual Word document parsing
2. Test with real .docx files
3. Add any additional company-specific formatting rules
