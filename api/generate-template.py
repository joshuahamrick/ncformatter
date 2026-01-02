from http.server import BaseHTTPRequestHandler
import json
import os
import traceback
import re

try:
	import openai
	OPENAI_AVAILABLE = True
except ImportError:
	OPENAI_AVAILABLE = False

# Import normalization (we'll create a Python version)
def normalize_html(html):
	"""Minimal normalization - just clean up, let AI do the formatting"""
	if not html or not isinstance(html, str):
		return ''
	
	normalized = html
	
	# Remove business rule references
	normalized = re.sub(r'<div>\(see\s+["\'].*?Business Rules.*?\)</div>', '', normalized, flags=re.IGNORECASE | re.DOTALL)
	normalized = re.sub(r'<div>\(see\s+["\'].*?BKFS.*?\)</div>', '', normalized, flags=re.IGNORECASE | re.DOTALL)
	
	# Fix nested divs
	normalized = re.sub(r'<div><div>', '<div>', normalized)
	normalized = re.sub(r'</div></div>', '</div>', normalized)
	
	# Normalize line endings
	normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
	
	# Normalize <br> tags
	normalized = re.sub(r'<br\s*/?>', '<br>', normalized, flags=re.IGNORECASE)
	
	return normalized.strip()

def load_system_prompt():
	"""Load the system prompt from file"""
	# Try multiple paths for Vercel serverless environment
	possible_paths = [
		os.path.join(os.path.dirname(__file__), '..', 'ai', 'prompts', 'system-prompt.txt'),
		os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ai', 'prompts', 'system-prompt.txt'),
		'ai/prompts/system-prompt.txt',
		os.path.join(os.getcwd(), 'ai', 'prompts', 'system-prompt.txt')
	]
	
	for prompt_path in possible_paths:
		try:
			if os.path.exists(prompt_path):
				with open(prompt_path, 'r', encoding='utf-8') as f:
					return f.read()
		except Exception as e:
			print(f"Failed to load prompt from {prompt_path}: {e}")
			continue
	
	# Fallback prompt if file not found
	print("WARNING: Using fallback system prompt - file not found")
	return """You are an expert HTML template generator for mortgage servicing documents. 
Generate HTML templates that match the exact formatting style shown in examples.
Use {[TAG]} format for variables, {[plsMatrix.*]} for company variables.
Remove last 2 characters from tag variables ending in digits/letters.
Always use {Compress({[M567]}|{[M583]}|{[M568]})} for property addresses.
Use <div>Dear {[Salutation]},</div> for salutations.
Return ONLY valid HTML, no explanations."""

def load_few_shot_examples():
	"""Load few-shot examples from formatted HTML files"""
	# Try multiple paths for Vercel serverless environment
	possible_dirs = [
		os.path.join(os.path.dirname(__file__), '..', 'formatter examples'),
		os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'formatter examples'),
		'formatter examples',
		os.path.join(os.getcwd(), 'formatter examples')
	]
	
	# Load MORE examples to give AI better context - diverse patterns
	curated = [
		'ES114/ES114-formatted.html',  # Simple PMI termination
		'MI008/MI008-formatted.html',  # PMI Auto Term with bullet points and different header layout
		'CA003/CA003-formatted.html',  # ACH with conditionals
		'GB001/GB001-formatted.html',  # Transfer letter
		'CA005/CA005-formatted.html',  # ACH removal
		'CS101/CS101-formatted.html',  # One-time draft
		'LM401/LM401-formatted.html',  # Complex table + conditionals
		'SI002/SI002-formatted.html'  # Complex document with many state conditionals - shows how to include ALL content
	]
	
	examples = []
	examples_dir = None
	
	# Find the examples directory
	for dir_path in possible_dirs:
		if os.path.exists(dir_path):
			examples_dir = dir_path
			break
	
	if not examples_dir:
		print("WARNING: Examples directory not found, using empty examples")
		return examples
	
	for rel_path in curated:
		full_path = os.path.join(examples_dir, rel_path)
		if os.path.exists(full_path):
			try:
				with open(full_path, 'r', encoding='utf-8') as f:
					html = f.read().strip()
					
					# Limit example size to reduce token usage
					# Large examples like SI002 should be truncated but still show structure
					max_example_chars = 15000  # ~5000 tokens per example
					if len(html) > max_example_chars:
						# For very large examples, take first part and note about truncation
						html = html[:max_example_chars] + "\n\n[... Example truncated - document continues with similar structure ...]"
					
					examples.append({
						'name': os.path.basename(rel_path).replace('-formatted.html', ''),
						'html': html
					})
			except Exception as e:
				print(f"Error loading example {rel_path}: {e}")
		else:
			print(f"Example file not found: {full_path}")
	
	return examples

def format_ir_for_prompt(ir):
	"""Format IR data into a readable prompt format - extract actual document content"""
	import re
	blocks = ir.get('blocks', [])
	formatted = []
	
	# Patterns to skip - these are metadata/instructions, not actual content
	skip_patterns = [
		'Company Address Line',
		'System Date',
		'New Bill Line',
		'Mailing Street Address',
		'Mailing City, State',
		'Foreign Country Code',
		'Foreign Postal Code',
		'Loan Number – No Dash',
		'New Property Line',
		'Mortgagor Name',
		'Second Mortgagor',
		'Co-borrower',
		'Non-borrower',
		'Additional Mailing Address',
		'New Property Unit Number',
		'Foreign Address Indicator',
		'Letter Library Business Rules',
		'Additional Borrowers',
		'Co-Borrowers',
		'BKFS'
	]
	
	# Patterns that indicate instruction text (not actual content)
	instruction_patterns = [
		r'^If\s+\[',  # "If [TAG]"
		r'^If\s+\[.*\]\s+and\s+\[',  # "If [H567] and [H568] present"
		r'^If\s+\[.*\]\s+present',  # "If [H567] present"
		r'^If\s+\[.*\]\s*=\s*\d+',  # "If [M956] = 1"
		r'^If\s+\[.*\]\s*≥',  # "If [M065] ≥"
		r'^If\s+\[.*\]\s*<',  # "If [M065] <"
		r'\(or if\s+\[',  # "(or if [H581]"
		r'\(see\s+["\']',  # "(see "Additional Borrowers..."
		r'^\[.*\]\s+[A-Z]',  # "[M561] Additional Mailing Address"
	]
	
	for idx, block in enumerate(blocks):
		if block.get('type') == 'paragraph':
			runs = block.get('runs', [])
			text = ''.join([r.get('text', '') for r in runs]).strip()
			
			# Skip empty or very short text
			if not text or len(text) < 10:
				continue
			
			# Skip if it matches instruction patterns
			is_instruction = False
			for pattern in instruction_patterns:
				if re.match(pattern, text, re.IGNORECASE):
					is_instruction = True
					break
			
			if is_instruction:
				continue
			
			# Skip if it's just a variable definition (starts with [TAG] and short)
			if re.match(r'^\[[A-Z0-9]+\]\s+[A-Z]', text) and len(text) < 80:
				continue
			
			# Skip variable definitions like "[M563] [M564] [M565] [M566] (Mailing City), (State), (5-Digit Zip), (4-Digit Zip)"
			if re.search(r'\[M\d+\]\s+\[M\d+\]\s+\[M\d+\]', text):
				continue
			if re.search(r'\(Mailing City\)|\(State\)|\(5-Digit Zip\)|\(4-Digit Zip\)', text):
				continue
			
			# Skip if it contains skip patterns and is short (likely just metadata)
			if any(pattern in text for pattern in skip_patterns):
				if len(text) < 100:  # Short = likely just metadata
					continue
				# If longer, might be actual content with metadata mention - include it
			
			# Skip conditional salutation text
			if re.search(r'\(or if\s+\[.*\]\s+(and/or|present)\)', text, re.IGNORECASE):
				continue
			
			# Skip business rule references
			if re.search(r'\(see\s+["\'].*Business Rules', text, re.IGNORECASE):
				continue
			if re.search(r'Letter Library Business Rules', text, re.IGNORECASE):
				continue
			
			# Skip lines that are just variable lists like "[M563] {[M564]} {[M565]} {[M566]}"
			if re.match(r'^(\[M\d+\]\s*)+', text) and len(text) < 150:
				continue
			
			# This looks like actual content - include it
			# Limit to 500 chars per paragraph to reduce token usage
			formatted.append(f"Paragraph {idx + 1}: {text[:500]}")
		elif block.get('type') == 'table':
			rows = block.get('rows', [])
			# Extract table content - include more detail
			table_text = []
			for row in rows[:10]:  # Increased limit to capture more rows
				cells = row.get('cells', [])
				cell_texts = []
				for c in cells[:5]:  # Increased cell limit
					cell_text = ''.join([r.get('text', '') for r in c.get('runs', [])])
					if cell_text.strip():
						cell_texts.append(cell_text[:200])  # Increased character limit
				if cell_texts:
					row_text = ' | '.join(cell_texts)
					table_text.append(row_text)
			if table_text:
				formatted.append(f"Table {idx + 1} ({len(rows)} rows):")
				for i, row_text in enumerate(table_text):
					formatted.append(f"  Row {i+1}: {row_text}")
	
	# Balance between including content and staying within token limits
	# For very large documents, we need to truncate but still provide enough context
	total_blocks = len(formatted)
	
	# Estimate tokens: roughly 4 chars per token, but be conservative (3 chars per token for text)
	# We need to leave room for system prompt (~2000 tokens), few-shot examples (~5000 tokens), 
	# user message structure (~1000 tokens), and response (~8000 tokens)
	# Total budget: ~30,000 tokens, so we can use ~14,000 tokens for IR content
	max_ir_chars = 40000  # ~13,000 tokens for IR content
	
	if total_blocks > 50:
		# For large documents, include up to 400 blocks initially
		max_blocks = min(400, total_blocks)
		result = '\n'.join(formatted[:max_blocks])
		
		# Check if we're approaching token limit
		result_length = len(result)
		if result_length > max_ir_chars:
			# Truncate to stay within limits
			result = result[:max_ir_chars]
			result += f"\n\n[NOTE: Document truncated at {max_ir_chars} chars due to token limits. Document has {total_blocks} total content blocks. You MUST still include ALL conditional sections, ALL state-specific content patterns, and ALL paragraph structures from the ENTIRE document. Use the patterns shown above to generate the complete template.]"
		elif total_blocks > max_blocks:
			result += f"\n\n[CRITICAL NOTE: Document has {total_blocks} total content blocks (showing first {max_blocks}). You MUST include ALL conditional sections, ALL state-specific content, and ALL paragraphs from the ENTIRE document structure. Do NOT stop early - continue until you reach the closing signature section.]"
		return result
	
	return '\n'.join(formatted)

def build_prompt(ir, few_shot_examples, user_instruction=None):
	"""Build the complete prompt for OpenAI"""
	system_prompt = load_system_prompt()
	
	# Format IR content
	ir_content = format_ir_for_prompt(ir)
	
	# Build few-shot examples section - show ALL examples with proper formatting
	few_shot_text = "\n## CRITICAL: Example Outputs - Study These Carefully\n\n"
	few_shot_text += "These examples show the EXACT formatting structure you must follow:\n"
	few_shot_text += "- Each element on its own line (with newlines)\n"
	few_shot_text += "- Proper <br> tags for spacing based on source document\n"
	few_shot_text += "- Standard header structure: Header, Date, Mailing Address, Property Address Table, Salutation, Content\n"
	few_shot_text += "- Conditional logic wrapped in {If()}...{End If}\n"
	few_shot_text += "- Property address ALWAYS in a table with Compress()\n\n"
	few_shot_text += "IMPORTANT: Notice how each example has proper newlines - each <div>, <br>, <table> is on its own line!\n\n"
	
	for idx, ex in enumerate(few_shot_examples):  # Show ALL examples
		few_shot_text += f"### Example {idx + 1}: {ex['name']}\n```html\n{ex['html']}\n```\n\n"
	
	# Build user message
	# Note: Using regular string concatenation instead of f-string to avoid issues with {If()} syntax
	user_message = """You are converting a Word document into a formatted HTML template. Your task is to:

1. Extract the actual document content (ignore variable definitions and instructions)
2. Format it as HTML following the EXACT structure and style shown in the examples
3. Use proper newlines - each HTML element on its own line
4. Include ALL required elements: header, date, mailing address, property address table, salutation, content
5. Wrap conditional content in {If()}...{End If} blocks
6. Match spacing from the source document

CRITICAL RULES:
- Extract ONLY the actual document text content
- IGNORE variable definitions like "[H002] Company Address Line 1" - those are metadata
- IGNORE conditional logic text like "(or if [H581] and/or [H582] present)" - do NOT include this
- IGNORE instructions like "If [M065] ≥ 'July 29, 1999' then print:" - convert to proper {If()} syntax
- NEVER include conditional salutation logic - ALWAYS use <div>Dear {[Salutation]},</div>
- ALWAYS include property address table after mailing address
- ALWAYS format with newlines - each tag on its own line

Document Content:
""" + ir_content + """

"""
	
	if user_instruction:
		user_message += f"Additional Instruction: {user_instruction}\n\n"
	
	user_message += """CRITICAL: You MUST format the HTML with proper newlines. Each HTML element MUST be on its own line.

Generate the HTML template following these EXACT rules:

STEP 1 - CONTENT EXTRACTION:
1. Extract ONLY actual document content - ignore variable definitions, conditional text, and instructions
2. Use exact variable format {[TAG]} and remove last 2 chars from tags ending in E6/E8/etc. (e.g., L001E8 → {[L001]}, M029E6 → {[M029]})
3. Use {[plsMatrix.*]} for ALL company variables (CompanyLongName, CompanyShortName, CSPhoneNumber, HoursOfOperation, LossPreventionPhoneNumberTollFree, etc.) - NEVER use variables without plsMatrix prefix for company data
   - CORRECT: {[plsMatrix.LossPreventionPhoneNumberTollFree]}, {[plsMatrix.CSPhoneNumber]}, {[plsMatrix.CompanyLongName]}
   - WRONG: {[LossPreventionPhoneNumberTollFree]}, {[CSPhoneNumber]}, {[CompanyLongName]} ← Missing plsMatrix prefix
4. ALWAYS use <div>Dear {[Salutation]},</div> for salutations - NEVER include conditional salutation logic
5. Convert math expressions properly:
   - If you see "[Q178E2 ÷ Q177]" or "[Q178 ÷ Q177]" → Convert to {Math({[Q178]} / {[Q177]}|Money)}
   - Remove E suffixes from tags (Q178E2 → {[Q178]})
   - Use / for division, + for addition, - for subtraction, * for multiplication
   - Format: {Math({[TAG1]} / {[TAG2]}|Money)} or {Math({[TAG1]} + {[TAG2]} - {[TAG3]}|Money)}
6. Convert conditional logic properly: "If [M065] ≥ 'July 29, 1999' then print:" becomes {If('{[M065]}' &gt;= 'July 29, 1999')}...content...{End If}
7. CRITICAL CONDITIONAL SYNTAX - Follow this EXACT format:
   CORRECT: {If('{[M006]}' = 'FHA' AND {[M037]} &gt; 0)}
   WRONG: {If({[M006]} = 'FHA' AND {[M037]} > 0)}  ← Missing quotes around variable, wrong comparison operator
   - Variables in string comparisons need quotes: '{[TAG]}'
   - Variables in numeric comparisons don't need quotes: {[TAG]}
   - Always use &gt; not > for greater than
   - Always use &lt; not < for less than
7. When you see text about "For loans closed on or after" or "For loans closed before", wrap it in {If()} conditionals based on [M065]
8. CRITICAL DATE COMPARISONS: For date comparisons in IF functions, dates must be in numeric format (yyyyMMdd) to be evaluated correctly, otherwise they will be compared as strings or interpreted as math. The Date() function's second parameter is for format (uses C# DateTime format strings). 
   - Example: {If((Date({[M065]}|yyyyMMdd) &gt;= 19990729))} - NO QUOTES around the date value, NO DASHES (to avoid subtraction)
   - Date() format examples: {Date({[M035]}|MMMM yyyy)} produces "September 2034", {Date({[TAG]}|MM/dd/yyyy)} produces "05/29/2015"
   - For comparisons, always use numeric format: yyyyMMdd WITHOUT quotes or dashes (e.g., 19990729, not '1999-07-29' or 1999-07-29)
8. PRESERVE STYLING from source document - CRITICAL: if text is centered, bold, underlined, or has specific font sizes, you MUST include those style attributes:
   - Centered text: style="text-align: center"
   - Font size: style="font-size: 14pt" (or whatever size is in the document)
   - Bold: <b>...</b>
   - Underlined: <u>...</u>
   - Combined: <div style="text-align: center; font-size: 14pt"><b>...</b></div>
   - Look at the Document Content for styling hints - if text appears centered or larger, preserve that
9. For tables, extract the ACTUAL table structure and content from the document - don't generate placeholder tables with "Column 1, Column 2" etc. - look at the LM401 example to see the correct 3-column table format
10. CRITICAL: If you see table content in the Document Content (look for "Table X" entries), you MUST include that table in your output - NEVER skip tables

STEP 2 - STRUCTURE (MANDATORY - DETECT FROM DOCUMENT):
CRITICAL: You MUST analyze the Document Content to determine the ACTUAL header structure - different documents have different layouts!

1. HEADER DETECTION - Look at the Document Content to determine the correct header type:
   - CRITICAL HEADER LOGIC (in priority order):
     a) If Document Content mentions NMLS or NMLSID → Use: <div>{Header(NMLSID)}</div>
     b) DEFAULT: Use <div>{Insert(H003 TagHeader)}</div> for most documents
     c) Only use <div>{[tagHeader]}</div> if Document Content explicitly shows tagHeader without H003
   - IMPORTANT: The default header format is {Insert(H003 TagHeader)} - use this unless NMLS is mentioned or the document explicitly shows tagHeader
   - Extract the EXACT header structure from the Document Content

2. LOAN NUMBER AND RE: TABLE - CRITICAL: Most letters MUST include a table with Loan Number and RE: (Property Address):
   - ALWAYS include this table after the mailing address and before the salutation
   - Extract the EXACT structure from Document Content - DO NOT combine or modify labels:
     * If Document Content shows "Loan Number: [M594]" → Use EXACTLY "Loan Number:" as the label
     * If Document Content shows "RE: [M567]" → Use EXACTLY "RE:" as the label
     * If Document Content shows "Re: Loan Number: [M594]" → Use EXACTLY "Re: Loan Number:" as the label
     * DO NOT combine "Loan Number:" with "RE:" to create "Re: Loan Number:" if that's not what's in the document
     * DO NOT modify labels - extract them EXACTLY as they appear in the Document Content
   - CRITICAL: Look at the Document Content for the EXACT label text - if it says "Loan Number:" use that, if it says "RE:" use that, if it says "Re: Loan Number:" use that
   - DO NOT create labels that don't exist in the Document Content
   - Format as: <table width="100%"><tbody><tr><td width="20%" valign="top">EXACT_LABEL_FROM_DOCUMENT:</td><td>{[TAG]}</td></tr>...</tbody></table>
   - ONLY skip this table if the Document Content clearly shows NO loan number or property address information

3. STANDARD STRUCTURE (use as base, but ADAPT based on Document Content):
<div>{Insert(H003 TagHeader)}</div>  <!-- DEFAULT: Use {Insert(H003 TagHeader)} unless NMLS is mentioned. Only use {[tagHeader]} if Document Content explicitly shows tagHeader without H003 -->
<br>
<div>{[L001]}</div>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>
<!-- CRITICAL: Most letters MUST include Loan Number and RE: table - extract EXACT labels from Document Content -->
<!-- DO NOT combine or modify labels - use EXACTLY what appears in Document Content -->
<!-- Example: If Document Content shows "Loan Number: [M594]" and "RE: [M567]", use those EXACT labels -->
<table width="100%"><tbody><tr>
  <td width="20%" valign="top">Loan Number:</td>  <!-- Extract EXACT label from Document Content - DO NOT modify -->
  <td>{[M594]}</td>
</tr><tr>
  <td width="20%" valign="top">RE:</td>  <!-- Extract EXACT label from Document Content - DO NOT modify -->
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table>
<br>
[Conditional FHA/RHS sections if present - format as {If('{[M006]}' = 'FHA' AND {[M037]} &gt; 0)}<div>FHA Case Number: {[M037]}</div>{End If}]
<br>
<div>Dear {[Salutation]},</div>
<br>
[Content paragraphs here - match spacing from source document]

CRITICAL: YOU MUST INCLUDE ALL CONTENT FROM THE DOCUMENT - DO NOT STOP EARLY:
- Include EVERY paragraph shown in the Document Content above - COUNT THEM and make sure you include ALL
- For documents with many state conditionals (like SI002), you MUST include ALL state-specific sections
- Include styled titles (with style attributes like text-align: center, font-size)
- Include ALL sections, tables, and content
- Don't stop after just the title or first few paragraphs - continue with ALL paragraphs until the closing
- If the Document Content shows "IF M960 (State Abbreviation) = STATE", you MUST include conditionals for ALL states mentioned
- If you see multiple transfer scenarios (death, divorce, trust, etc.), include ALL of them
- The document may have 100+ or even 800+ paragraphs - you MUST include ALL of them, not just the first 20-30
- PRESERVE ALL STYLING from the source document:
  - If text is centered, use style="text-align: center"
  - If text has a specific font size, include font-size in the style attribute
  - If text is bold, wrap in <b> tags
  - If text is underlined, wrap in <u> tags
  - If text is both bold and underlined, use <b><u>...</u></b>
- For tables, extract the ACTUAL table structure and content from the document - look at the Document Content for table information
- NEVER generate placeholder tables with "Column 1, Column 2" or "Add actual table rows here" - extract the real table content
- If you see table content in the Document Content, extract ALL rows and cells with their actual content
- Tables should have proper structure: headers in first row with <b> tags, data rows below, proper borders and styling
- Look for table content in the Document Content section - if you see "Table X" with rows, extract ALL of those rows into the HTML table structure
- NEVER skip tables - if the document has a table, it MUST appear in the HTML output
- CRITICAL: If you see text like "Payment Supplement Funds Applied" or any table-related header in the Document Content, there MUST be a table following it - look for "Table X" entries in the Document Content and include that complete table structure
- If the Document Content mentions a "chart" or "table" or "accounting" or "chart below", you MUST include the actual table structure with all rows
- If you see text like "The chart below provides an accounting" or "This notice also provides an accounting", there MUST be a table in the Document Content - find it and include it
- NEVER skip tables - if text references a table/chart/accounting, that table MUST appear in your output
- CRITICAL: After text that says "The chart below provides an accounting" or "This notice also provides an accounting", you MUST include a table with the header "Payment Supplement Funds Applied as of {[L001]}" followed by a 3-column table with headers "Date(s)" and "Amount"
- Look in the Document Content for "Table X" entries - if you see table content, extract ALL rows and create the complete table structure
- Include ALL content until the signature/closing section - DO NOT STOP EARLY
- CRITICAL: Count the paragraphs in Document Content. If there are 50+ paragraphs, you MUST include ALL of them
- CRITICAL: If Document Content shows state conditionals like "IF M960 = STATE", include conditionals for EVERY state mentioned
- CRITICAL: If Document Content shows multiple scenarios (e.g., "A transfer by devise...", "A transfer to a relative...", "Transfer to a spouse...", "Transfer into an inter vivos trust"), include ALL scenarios
- Include closing signature section with proper spacing: <div>Sincerely,</div><br><br><br><div>Department Name</div><div>{[plsMatrix.CompanyLongName]}</div><br><br>{If('{[M007]}' = '48')}<div><b><u>Wisconsin Property Owners</u></b> – Notice: See Reverse Side (or attached) for Important Information</div>{End If}
- Include any conditional sections at the end (like Wisconsin notice)
- Include contact information section: <div>Please review the circumstances listed above...</div> with company address lines if present in Document Content
- If a paragraph starts with text that should be bold (like "This notice is to advise you...", "Please note", "IMPORTANT"), wrap that portion in <b> tags: <div><b>Bold portion...</b> rest of paragraph</div>
- CRITICAL: If you see bullet points (•, -, *, or consecutive list items) in the Document Content, format them as a TABLE structure - NEVER skip bullet points
- CRITICAL: After section headers ending with ":" (like "Next Steps:", "Forbearance Plan Terms:", "Important:", etc.), ALWAYS check for bullet points that follow - these MUST be formatted as tables
- CRITICAL: Documents can have MULTIPLE sets of bullet points - you MUST check for and format ALL sets throughout the ENTIRE document, not just the first one
- CRITICAL: If you see multiple consecutive paragraphs after a section header, they are likely bullet points - format them as a table with bullet characters
- CRITICAL: After formatting one set of bullet points, CONTINUE scanning the Document Content for MORE sets - do not stop after the first set
- CRITICAL: Look for ALL paragraphs in the Document Content - count them and make sure you include EVERY SINGLE ONE
- CRITICAL: If the Document Content shows styled text (bold, centered, larger font), you MUST preserve that styling in the HTML output
- CRITICAL: NEVER stop after a section header - always include the bullet points/content that follows section headers
- CRITICAL: Scan the ENTIRE Document Content from beginning to end, checking for ALL bullet point sets - there may be multiple sets scattered throughout the document

CRITICAL BULLET POINTS AND BOLD TEXT:
- If you see bullet points (•, -, *, or numbered lists) in the Document Content, format them as a TABLE with bullet character in first column:
  Example: <table width="100%"><tbody><tr><td width="3%" valign="top" style="text-align: center">•</td><td>Bullet point text here</td></tr></tbody></table>
- CRITICAL: After section headers like "Next Steps:", "Forbearance Plan Terms:", "Important:", etc., look for bullet points that follow - these MUST be formatted as tables
- CRITICAL: If you see consecutive paragraphs that appear to be list items (especially after headers ending with ":"), format them as a bullet point table
- CRITICAL: Look for patterns like multiple paragraphs starting with similar text or appearing as a list - these are likely bullet points that need table formatting
- CRITICAL EXAMPLE: If Document Content shows:
  "Next Steps:
  Paragraph 1 about step 1
  Paragraph 2 about step 2
  Paragraph 3 about step 3"
  Then format as:
  <div><b>Next Steps:</b></div>
  <br>
  <table width="100%"><tbody>
  <tr>
    <td width="3%" valign="top" style="text-align: center">•</td>
    <td>Paragraph 1 about step 1</td>
  </tr>
  <tr>
    <td width="3%" valign="top" style="text-align: center">•</td>
    <td>Paragraph 2 about step 2</td>
  </tr>
  <tr>
    <td width="3%" valign="top" style="text-align: center">•</td>
    <td>Paragraph 3 about step 3</td>
  </tr>
  </tbody></table>
- CRITICAL: Documents can have MULTIPLE sets of bullet points throughout - you MUST check for and format ALL of them:
  * After EVERY section header ending with ":", check for bullet points that follow
  * Look for bullet points in the middle of paragraphs (not just after headers)
  * Look for bullet points near the end of the document
  * If you formatted one set of bullet points, continue scanning the Document Content for MORE sets
  * DO NOT stop after formatting the first set - continue checking the ENTIRE document
  * Count how many section headers end with ":" - each one might have bullet points after it
- If text appears BOLD in the Document Content (or starts with phrases like "This notice is to advise you", "IMPORTANT", "Please note"), wrap it in <b> tags
- If text appears CENTERED and LARGER in the Document Content, it's likely a title - use style="text-align: center; font-size: 14pt" with <b> tags
- PRESERVE ALL STYLING - if the Document Content shows bold, underline, center alignment, or font sizes, you MUST include those in the HTML
- NEVER skip bullet points - if you see a section header followed by multiple related paragraphs, check if they should be formatted as a bullet point table
- ALWAYS check for bullet points after section headers - count the paragraphs after headers ending with ":" and format consecutive related paragraphs as bullet point tables
- CRITICAL: Scan the ENTIRE Document Content from start to finish, checking for ALL bullet point sets - do not stop after finding the first set

CRITICAL NOTES:
- Most letters MUST include a Loan Number and RE: table after mailing address and before salutation
- The table structure VARIES by document - extract the EXACT structure from Document Content (labels may be "Loan Number:", "Re: Loan Number:", "RE: Loan Number:", etc.)
- Header type detection: NMLS (if mentioned) > {Insert(H003 TagHeader)} (default) > {[tagHeader]} (only if explicitly shown)
- DEFAULT header format is {Insert(H003 TagHeader)} - use this unless NMLS is mentioned
- Conditional syntax - STRING comparisons need quotes: '{[TAG]}', NUMERIC comparisons don't: {[TAG]}, always use &gt; not >
- CRITICAL: After section headers (especially those ending with ":"), always check for bullet points that follow - format them as tables

STEP 3 - FORMATTING (MANDATORY - THIS IS CRITICAL):
YOU MUST FORMAT WITH NEWLINES. LOOK AT THE EXAMPLES - THEY ALL HAVE EACH ELEMENT ON ITS OWN LINE.

Example of CORRECT formatting (showing different header layouts):
<div>{Insert(H003 TagHeader)}</div>
<br>
<div>{[L001]}</div>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>
[Example 1 - MI008 style header with "Loan Number:" and "RE:" in separate rows:]
<table width="100%"><tbody><tr>
  <td width="20%" valign="top">Loan Number:</td>
  <td>{[M594]}</td>
</tr><tr>
  <td width="20%" valign="top">RE:</td>
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table>
<br>
<div>Dear {[Salutation]},</div>
<br>
<div style="text-align: center; font-size: 14pt"><b>Notice of Termination of Private Mortgage Insurance (PMI)</b></div>
<br>
<div>Your mortgage loan requires Private Mortgage Insurance ("PMI"). PMI protects lenders and others against financial loss when borrowers default.</div>
<br>
{If((Date({[M065]}|yyyyMMdd) &gt;= 19990729))}
<div>For loans closed on or after 7/29/1999, the earlier of (1) the date that the mortgage balance is first scheduled to reach 78% of the original value of the property, or (2) the first day of the month after the date that is the midpoint of the original amortization period is reached.</div>
{End If}
<br>
[Example of bullet point formatted as table:]
<table width="100%"><tbody><tr>
  <td width="3%" valign="top" style="text-align: center">•</td>
  <td>Your mortgage loan must be current at the time of cancellation.</td>
</tr></tbody></table>
<br>
<div>Sincerely,</div>
<br><br><br>
<div>PMI/MIP Department</div>
<div>{[plsMatrix.CompanyLongName]}</div>
<br>
[Example 2 - Only use this pattern if Document Content shows "RE: Loan Number:" as a SINGLE label:]
If Document Content shows: "RE: Loan Number: [M594]" (as ONE label, not separate "Loan Number:" and "RE:")
Then use: <table width="100%"><tbody><tr>
  <td width="20%" valign="top">RE: Loan Number:</td>  <!-- Only if this EXACT text appears in Document Content -->
  <td>{[M594]}</td>
</tr><tr>
  <td width="20%" valign="top">Property Address:</td>  <!-- Extract EXACT label from Document Content -->
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table>

CRITICAL: If Document Content shows "Loan Number:" and "RE:" as SEPARATE labels, use them separately - DO NOT combine them.
<br>
<div style="text-align: center; font-size: 14pt"><b>IMPORTANT NOTICE:</b></div>
<div style="text-align: center; font-size: 14pt"><b>MORTGAGE PAYMENT INCREASE BEGINS...</b></div>
<br>
<div><b>This notice is to advise you that important information follows.</b> Then continues with regular text.</div>
<br>

Example of WRONG formatting (DO NOT DO THIS):
<div>{Insert(H003 TagHeader)}</div><br><div>{[L001]}</div><div>{[mailingAddress]}</div><br><br><br><br><br>...

RULES:
- Each <div> tag MUST be on its own line
- Each <br> tag MUST be on its own line  
- Each <table>, <tr>, <td> MUST be on its own line
- NEVER output everything on one line
- NEVER nest divs unnecessarily - each paragraph gets ONE <div>
- Look at the examples provided - they show the EXACT formatting you must use

STEP 4 - SPACING:
- Use <br> tags ONLY where the source document has actual line breaks/spacing
- Match spacing from the Word document exactly
- Standard spacing: <br><br><br><br><br> after mailing address

Return ONLY the HTML, formatted with proper newlines like the examples show. Each element on its own line. No explanations, no markdown code blocks."""
	
	return system_prompt, user_message, few_shot_text

class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', '0'))
			post_data = self.rfile.read(content_length)
			
			data = json.loads(post_data.decode('utf-8') or '{}')
			ir = data.get('ir')
			doc_meta = data.get('docMeta', {})
			user_instruction = data.get('userInstruction')
			chat_history = data.get('chatHistory', [])
			
			if not ir:
				return self._send(400, {'success': False, 'error': 'No IR data provided'})
			
			if not OPENAI_AVAILABLE:
				import_error = "OpenAI library not available. Install with: pip install openai. Make sure requirements.txt includes 'openai>=1.0.0'"
				print(f"ERROR: {import_error}")
				return self._send(500, {'success': False, 'error': import_error})
			
			# Get OpenAI API key from environment
			api_key = os.environ.get('OPENAI_API_KEY')
			if not api_key:
				key_error = 'OPENAI_API_KEY environment variable not set. Please set it in Vercel project settings → Environment Variables → Add OPENAI_API_KEY'
				print(f"ERROR: {key_error}")
				print(f"Available env vars: {list(os.environ.keys())[:10]}...")  # Debug: show first 10 env vars
				return self._send(500, {'success': False, 'error': key_error})
			
			print(f"OpenAI API key found: {api_key[:10]}... (length: {len(api_key)})")
			
			# Initialize OpenAI client
			client = openai.OpenAI(api_key=api_key)
			
			# Load few-shot examples
			try:
				few_shot_examples = load_few_shot_examples()
				print(f"Loaded {len(few_shot_examples)} few-shot examples")
			except Exception as e:
				print(f"Warning: Failed to load few-shot examples: {e}")
				few_shot_examples = []
			
			# Build prompt
			try:
				system_prompt, user_message, few_shot_text = build_prompt(ir, few_shot_examples, user_instruction)
				print("Prompt built successfully")
			except Exception as e:
				error_msg = f"Failed to build prompt: {str(e)}"
				print(f"ERROR: {error_msg}")
				return self._send(500, {'success': False, 'error': error_msg})
			
			# Combine system prompt with few-shot examples
			full_system_prompt = system_prompt + "\n\n" + few_shot_text
			
			# Call OpenAI
			try:
				# Use gpt-4o for better quality - it understands formatting and structure better
				model_name = "gpt-4o"
				print(f"Calling OpenAI API with model: {model_name}")
				print(f"System prompt length: {len(full_system_prompt)}")
				print(f"User message length: {len(user_message)}")
				
				# Estimate token count and set max_tokens accordingly
				# Rate limit: 30,000 TPM (tokens per minute)
				total_input_chars = len(full_system_prompt) + len(user_message)
				estimated_input_tokens = total_input_chars // 3  # Conservative estimate
				
				# Reserve tokens for output: 30,000 - estimated_input_tokens
				# But cap at reasonable limits
				available_output_tokens = 30000 - estimated_input_tokens
				if estimated_input_tokens > 22000:
					# Too large - reject before API call
					return self._send(400, {
						'success': False,
						'error': f'Document is too large (~{estimated_input_tokens} input tokens, limit ~22,000). Please use a smaller document or contact support.'
					})
				
				# Set max_tokens based on available budget, but cap at reasonable limits
				max_tokens = min(8000, max(4000, available_output_tokens - 1000))  # Leave 1000 token buffer
				
				ir_blocks = len(ir.get('blocks', []))
				print(f"Document has {ir_blocks} blocks, estimated input tokens: ~{estimated_input_tokens}, using max_tokens={max_tokens}")
				
				response = client.chat.completions.create(
					model=model_name,
					messages=[
						{"role": "system", "content": full_system_prompt},
						{"role": "user", "content": user_message}
					],
					temperature=0,  # Deterministic
					max_tokens=max_tokens
				)
				
				html = response.choices[0].message.content.strip()
				print(f"OpenAI API call successful, HTML length: {len(html)}")
			except Exception as api_error:
				error_msg = f"OpenAI API error: {str(api_error)}"
				print(f"ERROR: {error_msg}")
				print(f"API Error type: {type(api_error).__name__}")
				return self._send(500, {'success': False, 'error': error_msg})
			
			# Remove markdown code blocks if present
			if html.startswith('```html'):
				html = html.replace('```html', '').replace('```', '').strip()
			elif html.startswith('```'):
				html = html.replace('```', '').strip()
			
			# Normalize HTML
			html = normalize_html(html)
			
			# Extract notes if any (look for patterns like "Note:" or "Uncertain:")
			notes = []
			if 'Note:' in html or 'Uncertain:' in html:
				# Try to extract notes (this is a simple heuristic)
				pass
			
			return self._send(200, {
				'success': True,
				'html': html,
				'notes': notes
			})
			
		except Exception as e:
			error_trace = traceback.format_exc()
			error_msg = str(e)
			error_type = type(e).__name__
			print(f"ERROR in generate-template: {error_type}: {error_msg}")
			print(f"Traceback: {error_trace}")
			# Return a user-friendly error message - ALWAYS include the error message
			try:
				# Build a helpful error message
				user_error_msg = f"{error_type}: {error_msg}"
				
				# Add more context for common errors
				if 'API' in error_type or 'openai' in error_msg.lower():
					user_error_msg = f"OpenAI API Error: {error_msg}. Please check that OPENAI_API_KEY is set correctly."
				elif 'token' in error_msg.lower() or 'limit' in error_msg.lower():
					user_error_msg = f"Token Limit Error: {error_msg}. The document may be too large to process."
				elif 'JSON' in error_type:
					user_error_msg = f"Invalid Request: {error_msg}. Please check the request format."
				elif 'ImportError' in error_type or 'ModuleNotFoundError' in error_type:
					user_error_msg = f"Missing Dependency: {error_msg}. Please install required packages."
				
				err = {
					'success': False,
					'error': user_error_msg,
					'trace': error_trace if 'VERCEL' not in os.environ else None
				}
				return self._send(500, err)
			except Exception as send_error:
				print(f"Failed to send error response: {send_error}")
				traceback.print_exc()
				# Last resort - try to send a simple error
				try:
					self.send_response(500)
					self.send_header('Content-type', 'application/json')
					self.send_header('Access-Control-Allow-Origin', '*')
					self.end_headers()
					self.wfile.write(json.dumps({'success': False, 'error': error_msg}).encode('utf-8'))
				except Exception as final_error:
					print(f"Final error send failed: {final_error}")
					traceback.print_exc()
	
	def do_OPTIONS(self):
		self.send_response(200)
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Headers', 'Content-Type')
		self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
		self.end_headers()
	
	def _send(self, status, payload):
		try:
			# Ensure payload has 'error' field if it's an error response
			if status >= 400 and 'error' not in payload:
				payload['error'] = payload.get('error', 'Unknown error occurred')
			
			self.send_response(status)
			self.send_header('Content-type', 'application/json')
			self.send_header('Access-Control-Allow-Origin', '*')
			self.send_header('Access-Control-Allow-Headers', 'Content-Type')
			self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
			self.end_headers()
			
			# Ensure payload can be serialized
			try:
				response_body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
			except Exception as json_error:
				print(f"JSON serialization error: {json_error}")
				# Fallback to a simple error message
				response_body = json.dumps({
					'success': False,
					'error': f'Failed to serialize response: {str(json_error)}'
				}).encode('utf-8')
			
			self.wfile.write(response_body)
			print(f"Sent response: status={status}, body_length={len(response_body)}")
		except Exception as e:
			print(f"Error in _send: {e}")
			traceback.print_exc()
			# Try to send a basic error response
			try:
				# Only send if headers haven't been sent yet
				if not hasattr(self, '_headers_sent') or not self._headers_sent:
					self.send_response(500)
					self.send_header('Content-type', 'application/json')
					self.send_header('Access-Control-Allow-Origin', '*')
					self.end_headers()
					error_payload = {'success': False, 'error': f'Failed to send response: {str(e)}'}
					self.wfile.write(json.dumps(error_payload).encode('utf-8'))
			except Exception as final_error:
				print(f"Final error send failed: {final_error}")
				traceback.print_exc()

