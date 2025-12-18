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
		'CA003/CA003-formatted.html',  # ACH with conditionals
		'GB001/GB001-formatted.html',  # Transfer letter
		'CA005/CA005-formatted.html',  # ACH removal
		'CS101/CS101-formatted.html',  # One-time draft
		'LM401/LM401-formatted.html'  # Complex table + conditionals
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
			# Increase limit to capture more content
			formatted.append(f"Paragraph {idx + 1}: {text[:1000]}")
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
	
	return '\n'.join(formatted[:50])  # Increased limit to capture more content blocks

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
5. Convert conditional logic properly: "If [M065] ≥ 'July 29, 1999' then print:" becomes {If('{[M065]}' &gt;= 'July 29, 1999')}...content...{End If}
6. CRITICAL CONDITIONAL SYNTAX - Follow this EXACT format:
   CORRECT: {If('{[M006]}' = 'FHA' AND {[M037]} &gt; 0)}
   WRONG: {If({[M006]} = 'FHA' AND {[M037]} > 0)}  ← Missing quotes around variable, wrong comparison operator
   - Variables in string comparisons need quotes: '{[TAG]}'
   - Variables in numeric comparisons don't need quotes: {[TAG]}
   - Always use &gt; not > for greater than
   - Always use &lt; not < for less than
7. When you see text about "For loans closed on or after" or "For loans closed before", wrap it in {If()} conditionals based on [M065]
8. PRESERVE STYLING from source document - CRITICAL: if text is centered, bold, underlined, or has specific font sizes, you MUST include those style attributes:
   - Centered text: style="text-align: center"
   - Font size: style="font-size: 14pt" (or whatever size is in the document)
   - Bold: <b>...</b>
   - Underlined: <u>...</u>
   - Combined: <div style="text-align: center; font-size: 14pt"><b>...</b></div>
   - Look at the Document Content for styling hints - if text appears centered or larger, preserve that
9. For tables, extract the ACTUAL table structure and content from the document - don't generate placeholder tables with "Column 1, Column 2" etc. - look at the LM401 example to see the correct 3-column table format
10. CRITICAL: If you see table content in the Document Content (look for "Table X" entries), you MUST include that table in your output - NEVER skip tables

STEP 2 - STRUCTURE (MANDATORY - FOLLOW EXACTLY):
You MUST include this structure in this exact order, WITH EACH ELEMENT ON ITS OWN LINE:
<div>{Insert(H003 TagHeader)}</div>
<br>
<div>{[L001]}</div>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>
<table width="100%"><tbody><tr>
  <td width="20%" valign="top">RE: Loan Number:</td>
  <td>{[M594]}</td>
</tr><tr>
  <td width="20%" valign="top">Property Address:</td>
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table>
[Conditional FHA/RHS sections if present - format as {If('{[M006]}' = 'FHA' AND {[M037]} &gt; 0)}<div>FHA Case Number: {[M037]}</div>{End If}]
<br>
<div>Dear {[Salutation]},</div>
<br>
[Content paragraphs here - match spacing from source document]

CRITICAL: YOU MUST INCLUDE ALL CONTENT FROM THE DOCUMENT:
- Include EVERY paragraph shown in the Document Content above
- Include styled titles (with style attributes like text-align: center, font-size)
- Include ALL sections, tables, and content
- Don't stop after just the title - continue with all paragraphs
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
- Include ALL content until the signature/closing section
- Include closing signature section with proper spacing: <div>Sincerely,</div><br><br><br><div>Department Name</div><div>{[plsMatrix.CompanyLongName]}</div><br><br>{If('{[M007]}' = '48')}<div><b><u>Wisconsin Property Owners</u></b> – Notice: See Reverse Side (or attached) for Important Information</div>{End If}
- Include any conditional sections at the end (like Wisconsin notice)
- If a paragraph starts with text that should be bold (like "This notice is to advise you..."), wrap that portion in <b> tags: <div><b>Bold portion...</b> rest of paragraph</div>

NOTE: The property address table should have TWO rows: "RE: Loan Number:" and "Property Address:" - NOT just one row
NOTE: Conditional syntax - STRING comparisons need quotes: '{[TAG]}', NUMERIC comparisons don't: {[TAG]}, always use &gt; not >

STEP 3 - FORMATTING (MANDATORY - THIS IS CRITICAL):
YOU MUST FORMAT WITH NEWLINES. LOOK AT THE EXAMPLES - THEY ALL HAVE EACH ELEMENT ON ITS OWN LINE.

Example of CORRECT formatting:
<div>{Insert(H003 TagHeader)}</div>
<br>
<div>{[L001]}</div>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>
<table width="100%"><tbody><tr>
  <td width="20%" valign="top">RE: Loan Number:</td>
  <td>{[M594]}</td>
</tr><tr>
  <td width="20%" valign="top">Property Address:</td>
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table>
<br>
<div>Dear {[Salutation]},</div>
<br>
<div style="text-align: center; font-size: 12pt"><b><u>Document Title</u></b></div>
<br>
<div style="text-align: center; font-size: 14pt"><b>IMPORTANT NOTICE:</b></div>
<div style="text-align: center; font-size: 14pt"><b>MORTGAGE PAYMENT INCREASE BEGINS...</b></div>
<br>
<div><b>This notice is to advise you that important information follows.</b> Then continues with regular text.</div>
<br>
<div style="font-size: 14pt"><b>Section Heading</b></div>
<div>Section content here.</div>
<br>
<div><b>Table Title</b></div>
<table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="30%" style="border: 1px solid rgba(0, 0, 0, 1)"><b>Header 1</b></td>
  <td width="30%" style="border: 1px solid rgba(0, 0, 0, 1); text-align: center"><b>Header 2</b></td>
  <td width="20%" style="border: 1px solid rgba(0, 0, 0, 1); text-align: center"><b>Header 3</b></td>
</tr><tr>
  <td style="border: 1px solid rgba(0, 0, 0, 1)">Row 1 Col 1</td>
  <td style="border: 1px solid rgba(0, 0, 0, 1)">Row 1 Col 2</td>
  <td style="border: 1px solid rgba(0, 0, 0, 1)">{Money({[M029]})}</td>
</tr></tbody></table>
<br>
<div>Contact us at {[plsMatrix.CSPhoneNumber]} or {[plsMatrix.LossPreventionPhoneNumberTollFree]}</div>
<br>
<div>Sincerely,</div>
<br><br><br>
<div>Department Name</div>
<div>{[plsMatrix.CompanyLongName]}</div>
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
				response = client.chat.completions.create(
					model=model_name,
					messages=[
						{"role": "system", "content": full_system_prompt},
						{"role": "user", "content": user_message}
					],
					temperature=0,  # Deterministic
					max_tokens=8000  # Increased to handle longer documents
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
			# Return a user-friendly error message
			try:
				err = {
					'success': False,
					'error': f"{error_type}: {error_msg}",
					'trace': error_trace if 'VERCEL' not in os.environ else None
				}
				return self._send(500, err)
			except Exception as send_error:
				print(f"Failed to send error response: {send_error}")
				# Last resort - try to send a simple error
				try:
					self.send_response(500)
					self.send_header('Content-type', 'application/json')
					self.end_headers()
					self.wfile.write(json.dumps({'success': False, 'error': error_msg}).encode('utf-8'))
				except:
					pass
	
	def do_OPTIONS(self):
		self.send_response(200)
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Headers', 'Content-Type')
		self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
		self.end_headers()
	
	def _send(self, status, payload):
		try:
			self.send_response(status)
			self.send_header('Content-type', 'application/json')
			self.send_header('Access-Control-Allow-Origin', '*')
			self.send_header('Access-Control-Allow-Headers', 'Content-Type')
			self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
			self.end_headers()
			response_body = json.dumps(payload).encode('utf-8')
			self.wfile.write(response_body)
			print(f"Sent response: status={status}, body_length={len(response_body)}")
		except Exception as e:
			print(f"Error in _send: {e}")
			traceback.print_exc()

