# NcFormatter: Word Document to HTML Formatter

> Automatically converts Microsoft Word documents into production-ready HTML formatted according to New Course Communications' programming standards. Reduces letter template formatting time by **60-80%**.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![JavaScript](https://img.shields.io/badge/JavaScript-ES6+-yellow.svg)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![Vercel](https://img.shields.io/badge/Deployed-Vercel-black.svg)](https://vercel.com/)

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Local Development](#local-development)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)

## 🎯 Overview

NcFormatter is a web application that automatically converts Word documents (`.docx`) and PDFs into standardized HTML with:

- **Placeholder tags** (`{[M594]}`, `{[plsMatrix.CompanyLongName]}`)
- **Helper functions** (`{Math(...)}`, `{DateAdd(...)}`, `{Compress(...)}`)
- **Font and header directives** (`{Font(Calibri|10Pt)}`, `{Header(NMLSID)}`)
- **Proper table structures** and formatting
- **Conditional logic blocks** (`{If(...)}...{End If}`)

The application uses an **Intermediate Representation (IR)** pattern to separate document extraction from HTML rendering, making it maintainable and extensible.

## ✨ Features

- 🎨 **Drag & Drop Interface** - Simple, intuitive file upload
- 👁️ **Real-time Preview** - See formatted output before copying
- 📋 **One-Click Copy** - Copy HTML code to clipboard instantly
- 🔄 **Universal Rules** - Works for any document type (not hardcoded per letter)
- 🏷️ **Smart Placeholder Handling** - Converts old formats (`#TAG#`) to new (`{[TAG]}`)
- 📊 **Intelligent Table Detection** - Automatically formats RE tables, bullet tables, amount summaries
- 🧮 **Math Expression Formatting** - Detects and formats calculations
- 📅 **Date Calculation Support** - Handles DateAdd expressions
- 🌐 **Spanish Translation Support** - Properly formats bilingual content
- ✅ **Conditional Content Blocks** - Wraps optional content in `{If(...)}` blocks

## 🛠️ Tech Stack

### Frontend
- **HTML5/CSS3** - Modern, responsive UI
- **Vanilla JavaScript** - No framework dependencies (`script-new.js`)
- **pdf.js** - Client-side PDF extraction

### Backend
- **Python 3.11** - Serverless functions (Vercel)
- **python-docx** - Word document parsing
- **pdfminer.six** - PDF text extraction (fallback)

### Deployment
- **Vercel** - Serverless hosting with Python runtime

## 🚀 Quick Start

### Prerequisites

- **Node.js** (v14+) - For local development server
- **Python 3.11** - For local API testing (optional)
- **Modern web browser** - Chrome, Firefox, Safari, or Edge

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/joshuahamrick/ncformatter.git
   cd ncformatter
   ```

2. **Install Python dependencies** (for local API testing)
   ```bash
   pip install -r requirements.txt
   ```

3. **Start local development server**
   ```bash
   # Option 1: Using npx serve (recommended)
   npx serve .
   
   # Option 2: Using Python's built-in server
   python -m http.server 8000
   
   # Option 3: Using Node.js http-server
   npx http-server -p 8000
   ```

4. **Open in browser**
   ```
   http://localhost:3000  (if using npx serve)
   http://localhost:8000  (if using Python/Node server)
   ```

5. **Test the formatter**
   - Drag & drop a Word document onto the page
   - View the formatted HTML output
   - Copy the HTML code

## 💻 Local Development

### Setting Up on a New Computer

1. **Install Git** (if not already installed)
   ```bash
   # Windows: Download from https://git-scm.com/
   # Mac: brew install git
   # Linux: sudo apt-get install git
   ```

2. **Install Node.js** (for local server)
   ```bash
   # Download from https://nodejs.org/
   # Or use a version manager:
   # nvm install 18
   # nvm use 18
   ```

3. **Install Python 3.11** (for API testing)
   ```bash
   # Windows: Download from https://www.python.org/downloads/
   # Mac: brew install python@3.11
   # Linux: sudo apt-get install python3.11 python3-pip
   ```

4. **Clone and setup**
   ```bash
   git clone https://github.com/joshuahamrick/ncformatter.git
   cd ncformatter
   pip install -r requirements.txt
   ```

5. **Start development server**
   ```bash
   npx serve .
   ```

### Development Workflow

1. **Make changes** to `script-new.js` or `renderer-node.js`
2. **Test locally** using `npx serve .`
3. **Debug specific documents** using:
   ```bash
   node tools/debug-doc.js "path/to/document.docx"
   # Outputs to tools/debug-output.html
   ```
4. **Run snapshot tests** (see [Testing](#testing))
5. **Commit and push** changes

### Key Files for Development

- **`script-new.js`** - Browser renderer + UI logic
- **`renderer-node.js`** - Node.js renderer (for testing)
- **`api/process-doc.py`** - Word → IR extraction
- **`tools/debug-doc.js`** - Debug single document
- **`tools/snapshot-runner.js`** - Batch testing

## 📁 Project Structure

```
NcFormatter/
├── index.html              # Main UI
├── script-new.js           # Browser renderer + UI logic
├── renderer-node.js        # Node.js renderer (for testing)
├── styles.css              # UI styling
│
├── api/
│   ├── process-doc.py      # Word → IR extraction (Vercel function)
│   ├── process-pdf.py      # PDF → IR extraction (Vercel function)
│   └── health.py           # API health check
│
├── tools/
│   ├── debug-doc.js        # Debug single document
│   ├── snapshot-runner.js  # Batch testing
│   └── transformer-node.js # IR transformation utilities
│
├── tests/
│   └── snapshots/          # Expected vs generated HTML comparison
│       ├── index.html       # Browser-based test harness
│       └── artifacts/      # Test outputs (*.expected.html, *.generated.html)
│
├── formatter examples/     # Sample documents and expected outputs
│   ├── DS016/
│   ├── LM150/
│   ├── BR007/
│   └── ...
│
├── requirements.txt        # Python dependencies
├── vercel.json            # Vercel configuration
└── README.md              # This file
```

## 🔧 How It Works

### Architecture: Intermediate Representation (IR) Pattern

```
Word/PDF Document
    ↓
[Extraction Layer - Python]
    ↓
Intermediate Representation (IR)
    ↓
[Transformation Layer - JavaScript]
    ↓
[HTML Rendering Layer - JavaScript]
    ↓
Formatted HTML
```

### Stage 1: Extraction (Python)

**File**: `api/process-doc.py`

Extracts structured data from Word documents:
- Paragraphs with formatting (bold, italic, underline, font size/family)
- Tables with cell content and structure
- Alignment, indentation, spacing
- List detection (bullets, numbering)
- Header/footer content
- Document metadata

**IR Structure Example:**
```json
{
  "blocks": [
    {
      "type": "paragraph",
      "runs": [
        {"text": "Dear ", "bold": false},
        {"text": "{[Salutation]}", "bold": false}
      ],
      "align": "left",
      "fontSizePt": 11
    }
  ],
  "meta": {
    "headerTexts": ["CompanyReturnAdd1", "CompanyReturnAdd2", "NMLID"]
  }
}
```

### Stage 2: Transformation & Rendering (JavaScript)

**Files**: `script-new.js` (browser), `renderer-node.js` (Node.js)

**Transformation Rules:**
1. Placeholder normalization (`#TAG#` → `{[TAG]}`)
2. Table detection (RE tables, bullet tables, amount summaries)
3. Mailing address consolidation
4. Math expression detection
5. Conditional block wrapping
6. Font/Header detection

**Rendering Process:**
1. Converts IR blocks to HTML elements
2. Applies formatting (styles, alignment, font sizes)
3. Runs cleanup rules to fix common issues
4. Generates final HTML output

## 🧪 Testing

### Snapshot Testing

Compare generated HTML against expected outputs:

1. **Open test harness**
   ```bash
   npx serve .
   # Navigate to http://localhost:3000/tests/snapshots/
   ```

2. **Select a document** from the dropdown
3. **Click "Load Expected HTML"**
4. **Upload the matching Word document**
5. **Compare** the rendered output

### Command-Line Testing

**Test a single document:**
```bash
node tools/debug-doc.js "formatter examples/DS016/DS016_VP_FHA Trial Period Pln Brk Dnl Ltr V1.docx"
# Outputs to tools/debug-output.html
```

**Compare against expected:**
```bash
# Expected: formatter examples/DS016/DS016-formatted.html
# Generated: tools/debug-output.html
```

### Test Documents

Sample documents are located in `formatter examples/`:
- **DS016** - Trial Period Plan Break Denial Letter
- **LM150** - Forbearance Plan Offer
- **BR007** - Final Demand Letter (Texas)
- **BR008** - Final Demand Letter (Iowa)
- **BR010** - Final Demand Letter (Florida)
- And more...

## 🚢 Deployment

### Vercel (Recommended)

1. **Connect repository** to Vercel
2. **Configure build settings**:
   - Framework Preset: Other
   - Build Command: (leave empty)
   - Output Directory: `.`
   - Install Command: `pip install -r requirements.txt`

3. **Deploy**
   - Vercel automatically detects `api/` folder as serverless functions
   - Python runtime is configured in `vercel.json`


### Environment Variables

No environment variables required for basic functionality.

## 📚 Key Algorithms

### Dominant Font Detection
Analyzes all text runs in document to determine most common font/size. Only adds `{Font(...)}` directive if font is NOT Calibri 11pt (default).

### Header Type Detection
Checks document headers for:
- **H003** references → `{Insert(H003 TagHeader)}`
- **NMLID** in headers → `{Header(NMLSID)}`
- Default → `{[tagHeader]}` placeholder

### Table Structure Recognition
- **RE Tables**: Detects "RE: Loan No." patterns, converts to 3-column table
- **Bullet Tables**: Identifies bullet lists, formats with proper `valign`
- **Amount Summary Tables**: Recognizes financial tables, applies indentation

## 🤝 Contributing

### Development Guidelines

1. **Universal Rules**: All formatting rules should work for any document type
2. **No Hardcoding**: Avoid document-specific code
3. **Test Before Committing**: Run snapshot tests to ensure no regressions
4. **Document Changes**: Update relevant documentation

### Code Style

- **JavaScript**: Follow existing code style (no semicolons, 2-space indentation)
- **Python**: Follow PEP 8 style guide
- **Comments**: Add comments for complex logic

### Adding New Features

1. **Create feature branch**
   ```bash
   git checkout -b feature/new-feature
   ```

2. **Make changes** and test locally
3. **Run snapshot tests** to ensure no regressions
4. **Commit and push**
   ```bash
   git commit -m "Add new feature"
   git push origin feature/new-feature
   ```

5. **Create pull request** on GitHub

## 📖 Documentation

- **[APP_EXPLANATION.md](APP_EXPLANATION.md)** - Detailed technical documentation
- **[APP_SUMMARY.md](APP_SUMMARY.md)** - Quick reference guide
- **[SETUP.md](SETUP.md)** - Additional setup instructions

## 🐛 Troubleshooting

### Common Issues

**Issue**: Python function not working locally
- **Solution**: Ensure Python 3.11 is installed and dependencies are installed (`pip install -r requirements.txt`)

**Issue**: CORS errors when testing locally
- **Solution**: Use `npx serve .` or configure your server to allow CORS

**Issue**: Generated HTML doesn't match expected
- **Solution**: Run `node tools/debug-doc.js` to debug specific document and compare outputs

**Issue**: Font/Header directives not appearing
- **Solution**: Check that document headers are being extracted (see `api/process-doc.py`)

## 📄 License

This project is proprietary software for New Course Communications.

## 👤 Author

**Josh Hamrick**
- Programmer, New Course Communications
- Email: josh.hamrick@newcoursecc.com

## 🙏 Acknowledgments

- Built to improve programmer efficiency at New Course Communications
- Reduces letter template formatting time by 60-80%
- Standardizes output and reduces errors

---

**Made with ❤️ for New Course Communications**
