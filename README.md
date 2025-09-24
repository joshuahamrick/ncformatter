# Word Document Formatter

A modern web application that converts Word documents (.doc/.docx) to formatted HTML with a beautiful drag-and-drop interface.

## Features

- **Drag & Drop Interface**: Simply drag your Word document onto the upload area
- **Real-time Preview**: See the formatted output in a clean preview pane
- **HTML Code View**: Switch between preview and raw HTML code
- **One-Click Copy**: Copy the formatted HTML to clipboard with a single click
- **Responsive Design**: Works perfectly on desktop and mobile devices
- **Error Handling**: Clear error messages and retry functionality

## Getting Started

1. Open `index.html` in your web browser
2. Drag and drop a Word document (.doc or .docx) onto the upload area
3. Wait for processing (currently shows sample content)
4. View the formatted output and copy the HTML code

## Project Structure

```
NcFormatter/
├── index.html          # Main HTML file with UI structure
├── styles.css          # Modern CSS styling with responsive design
├── script.js           # JavaScript functionality and document processing
└── README.md           # This file
```

## Current Status

The application currently includes:
- ✅ Complete UI with drag-and-drop functionality
- ✅ File validation for Word documents
- ✅ Processing status indicators
- ✅ Preview and HTML code tabs
- ✅ Functional copy button
- ✅ Error handling and user feedback
- ✅ Responsive design
- ✅ **Company-specific formatting rules implemented:**

### Implemented Formatting Rules:

1. **Paragraph & Line Formatting**
   - Each logical paragraph wrapped in `<div>...</div>`
   - `<br>` after each div for separation
   - Continuous text within divs (no extra line breaks)

2. **Inline Variable Rules**
   - `{[TAG]}` syntax support
   - `plsMatrix.` prefix for company/contact variables
   - `{Money({[TAG]})}` for money values
   - `{Math({[TAG1]} + {[TAG2]} - {[TAG3]}|Money)}` for calculations
   - `Compress({[TAG1]}|{[TAG2]})` for compressed multiline addresses

3. **Table Formatting**
   - Full-width tables with `border-collapse:collapse`
   - Bullet lists as tables with 3% bullet column and 97% content column
   - Payment details as 70%/30% two-column tables
   - Proper `vertical-align:top` on all table cells

4. **Text Formatting**
   - Bold (`<b>`) only for section headers and emphasis
   - No inline bold elsewhere

5. **Spacing & Alignment**
   - Standard spacing with `<br>` after `<div>`
   - Centered addresses with `text-align:center`
   - Proper table cell alignment

## Next Steps

The formatting engine is ready! Next you can:
1. **Real Document Processing**: Integrate with [mammoth.js](https://github.com/mwilliamson/mammoth.js) for actual Word document parsing
2. **Additional Rules**: Add any specific formatting rules for your company
3. **Advanced Features**: Batch processing, different output formats, etc.

## Browser Compatibility

- Chrome/Edge (recommended)
- Firefox
- Safari
- Mobile browsers

## Dependencies

Currently uses only vanilla JavaScript with no external dependencies. The styling uses Google Fonts (Inter) which is loaded from CDN.

## Development Notes

The current implementation shows sample formatted content for demonstration. To process real Word documents, you'll need to:

1. Add mammoth.js library for document parsing
2. Replace the `parseWordDocument` method with actual document processing
3. Implement your company-specific formatting rules in the `DocumentProcessor` class

The code is structured to make these additions straightforward.
