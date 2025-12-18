# HTML Template Style Guide for NcFormatter

## Core Formatting Rules

### Document Structure
- Always start with: `<div>{Insert(H003 TagHeader)}</div>` or `<div>{Insert(Flat Branch Header)}</div>`
- Follow with: `<br>`, then date `{[L001]}`, then `{[mailingAddress]}`
- Add spacing: `<br><br><br><br><br>` after mailing address

### Variable Placeholders
- Use `{[TAG]}` format for all variables (e.g., `{[M594]}`, `{[L001]}`)
- Company variables MUST use `plsMatrix` prefix: `{[plsMatrix.CompanyLongName]}`, `{[plsMatrix.CompanyShortName]}`, `{[plsMatrix.CSPhoneNumber]}`, etc.
- Remove last 2 characters from tag variables when they end in digits/letters (e.g., `L001E8` → `{[L001]}`, `M029E6` → `{[M029]}`, `H160E7` → `{[H160]}`)

### Property Address Format
- Always use `{Compress({[M567]}|{[M583]}|{[M568]})}` for property addresses
- Format as table: `<table width="100%"><tbody><tr><td width="20%" valign="top">Property Address:</td><td>{Compress({[M567]}|{[M583]}|{[M568]})}</td></tr></tbody></table>`

### Loan Number Format
- Usually: `<div>Loan Number: {[M594]}</div>` or in a table row
- Sometimes: `<div>{[plsMatrix.CompanyShortName]} Loan Number: {[M594]}</div>`

### Salutation
- Always use: `<div>Dear {[Salutation]},</div>`
- Do NOT use conditional salutation logic unless explicitly shown in examples

### Helper Functions
- `{Money({[TAG]})}` - Format monetary values
- `{Math({[TAG1]} + {[TAG2]} - {[TAG3]}|Money)}` - Math calculations with Money formatting
- `{DateAdd({[TAG]}|+1|MM/dd/yyyy|Month)}` - Date calculations
- `{Compress({[TAG1]}|{[TAG2]}|{[TAG3]})}` - Multi-line address compression
- `{If('{[TAG]}' &gt; 0)}...{End If}` - Conditional blocks (use `&gt;` not `>`)

### Conditional Logic Syntax
- Use: `{If('{[TAG]}' &gt; 0)}` or `{If('{[TAG]}' NOT IN ('', '0', '.00', NULL))}`
- Use: `{Else If('{[TAG]}' = 'value')}`
- Use: `{End If}`
- Always use `&lt;&gt;` for not equal, `&gt;` for greater than

### Tables
- Use `<table width="100%" style="border-collapse: collapse">` for bordered tables
- Use `<table width="100%">` for simple tables
- Column widths: `width="20%"`, `width="50%"`, etc.
- Use `valign="top"` for cells with multi-line content
- Use `colspan="2"` for cells spanning multiple columns
- Bold headers: `<td><b>Header</b></td>` or `<td style="text-align: center"><b>Header</b></td>`

### Paragraphs and Spacing
- Wrap each logical paragraph in `<div>...</div>`
- Use `<br>` for line breaks between paragraphs
- Use `<br><br>` or more for section spacing
- Do NOT use padding-left on address divs unless specified

### Bold Text
- Use `<b>...</b>` for bold text
- Use `<div><b>...</b></div>` for bold paragraphs
- Use `<u>...</u>` for underlined text (often combined with bold)

### Address Blocks
- Use `{Compress(...)}` for multi-line addresses
- For payment addresses, use bold divs: `<div><b>Address Line 1</b></div>`
- For company return addresses, use `{Compress({[plsMatrix.CompanyReturnAddr1]}|{[plsMatrix.CompanyReturnAddr2]}|{[plsMatrix.CompanyReturnAddr3]})}`

### Centered Text
- Use: `<div style="text-align: center"><b>Title</b></div>`
- For large titles: `<div style="text-align: center; font-size: 12pt"><b><u>Title</u></b></div>`

### Font Sizes
- Use inline styles: `style="font-size: 14pt"` for larger text
- Common sizes: `12pt`, `14pt`

### Horizontal Rules
- Use: `<hr>` for section breaks
- Sometimes followed by spacing: `<br><br>`

### Closing Signatures
- Format: `<div>Sincerely,</div><br><div>Department Name</div><div>{[plsMatrix.CompanyLongName]}</div>`
- Add spacing before signature: `<br><br><br>`

## Common Patterns

### Subject Line Pattern
```
<div>Subject: [Subject Text]</div>
<br>
```

### Loan Number + Property Table Pattern
```
<table width="100%"><tbody><tr>
  <td width="20%" valign="top">Loan Number:</td>
  <td>{[M594]}</td>
</tr><tr>
  <td width="20%" valign="top">RE:</td>
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table>
```

### Bullet List Pattern
```
<div><table width="100%" style="border-collapse: collapse; margin-left: 30px"><tbody><tr>
  <td width="3%" valign="top" style="text-align: center">•</td>
  <td>Item text</td>
</tr><tr>
  <td width="3%" valign="top" style="text-align: center">•</td>
  <td>Next item</td>
</tr></tbody></table></div>
```

### Conditional FHA/RHS Pattern
```
{If('{[M006]}' = 'FHA' AND {[M037]} &gt; 0)}
<div>FHA Case Number: {[M037]}</div>
{End If}
{If('{[M006]}' = 'RHS' AND {[M923]} &gt; 0)}
<div>RHS ID #: {[M923]}</div>
{End If}
```

### Wisconsin Disclosure Pattern
```
{If('{[M007]}' = '48')}
<div><b><u>Wisconsin Property Owners</u></b> – Notice: See Reverse Side (or attached) for Important Information</div>
{End If}
```

## Important Notes
- Always preserve exact variable names from the source document
- Remove last 2 characters from tag variables ending in E6, E8, E7, etc.
- Use `plsMatrix` prefix for ALL company-related variables
- Maintain consistent spacing and structure across similar document types
- Tables should have proper borders and alignment
- Conditional blocks should be inline within paragraphs when appropriate

