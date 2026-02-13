from http.server import BaseHTTPRequestHandler
import json
import os
import traceback
import re

try:
	import anthropic
	ANTHROPIC_AVAILABLE = True
except ImportError:
	ANTHROPIC_AVAILABLE = False

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
	
	# Load minimal examples to reduce token usage - only most critical ones
	curated = [
		'MI008/MI008-formatted.html',  # PMI Auto Term with bullet points and different header layout
		'CA003/CA003-formatted.html',  # ACH with conditionals
		'LM401/LM401-formatted.html'  # Complex table + conditionals
		# Removed: ES114, GB001, CA005, CS101, SI002 to aggressively reduce token usage
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
					
					# Claude's 200K context gives us much more room for examples
					max_example_chars = 10000  # ~3300 tokens per example - show full structure
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
	# CRITICAL: Be more conservative - only skip if it's CLEARLY just an instruction line, not actual content
	instruction_patterns = [
		r'^If\s+\[.*\]\s+present\s*$',  # "If [H567] present" (standalone line)
		r'^\(or if\s+\[.*\]\s+present\)\s*$',  # "(or if [H581] present)" (standalone)
		r'^\[.*\]\s+[A-Z][a-z]+\s+[A-Z][a-z]+\s+Line\s+\d+',  # "[M561] Additional Mailing Address Line 1" (variable definitions)
	]
	# REMOVED patterns that were too aggressive:
	# - r'^If\s+\[' - too broad, catches actual conditional content
	# - r'^If\s+\[.*\]\s*=\s*\d+' - could be actual content mentioning conditions
	# - r'\(or if\s+\[' - could be in actual content
	# - r'\(see\s+["\']' - could be actual content references
	
	for idx, block in enumerate(blocks):
		if block.get('type') == 'paragraph':
			runs = block.get('runs', [])
			text = ''.join([r.get('text', '') for r in runs]).strip()
			
			# Skip empty or very short text
			if not text or len(text) < 10:
				continue
			
			# Skip if it matches instruction patterns - but be VERY conservative
			# Only skip if it's clearly just a metadata instruction line, not actual content
			is_instruction = False
			for pattern in instruction_patterns:
				if re.match(pattern, text, re.IGNORECASE):
					# Double-check: if it contains actual sentence content (periods, commas, etc.), it's probably content
					if not re.search(r'[.!?]\s+[A-Z]', text):  # No sentence structure
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
			# CRITICAL: Remove metadata descriptions in parentheses BEFORE including in prompt
			# These are variable descriptions like "(Property Line 1/Street Address)", "(Due Date)", "(Delinquent Balance)", etc.
			# Pattern: (Description text) that appears after variable tags or in variable definitions
			cleaned_text = text
			
			# Remove parenthesis descriptions that are metadata (not actual content)
			# These typically appear after variable tags like {[M567]} (Property Line 1/Street Address)
			# Or in calculations like {[M591]} (Delinquent Balance) + {[M015]} (Accrued Late Charge Balance)
			# Pattern: Look for parentheses containing descriptive metadata
			metadata_patterns = [
				r'\s*\(Property Line \d+/[^)]+\)',  # (Property Line 1/Street Address)
				r'\s*\(New Property [^)]+\)',  # (New Property Unit Number), (New Property Line 2/...)
				r'\s*\(Due Date\)',  # (Due Date)
				r'\s*\(Delinquent Balance\)',  # (Delinquent Balance)
				r'\s*\(Accrued Late Charge Balance\)',  # (Accrued Late Charge Balance)
				r'\s*\(NSF Balance\)',  # (NSF Balance)
				r'\s*\(Mortgagor Recoverable Corporate Advance Balance\)',  # (Mortgagor Recoverable Corporate Advance Balance)
				r'\s*\(Other Fees\)',  # (Other Fees)
				r'\s*\(Suspense Balance\)',  # (Suspense Balance)
				r'\s*\(the Property\)',  # (the Property) - this one should stay, it's actual content
			]
			
			# Remove metadata descriptions but keep "(the Property)" as it's actual content
			for pattern in metadata_patterns:
				if pattern != r'\s*\(the Property\)':  # Don't remove this one
					cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)
			
			# Also remove generic patterns: (Description) that appear after variable tags
			# But be careful - only remove if it looks like metadata, not actual content
			# Pattern: (Capitalized Description) after a variable tag or in a calculation
			cleaned_text = re.sub(r'\s*\([A-Z][^)]*(?:Balance|Date|Address|Number|Line|Code|Indicator|Name)\)', '', cleaned_text)
			
			# Clean up extra spaces
			cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
			
			# For ALL-CAPS text (likely important legal notices), include more characters
			# Check if text is mostly uppercase - if so, include more to preserve complete notices
			is_mostly_uppercase = len([c for c in cleaned_text if c.isupper()]) > len(cleaned_text) * 0.5
			char_limit = 1000 if is_mostly_uppercase else 500  # Claude's 200K context allows full content
			
			# Extract formatting information (bold, underline, font size, alignment)
			has_bold = any(r.get('bold', False) for r in runs)
			has_underline = any(r.get('underline', False) for r in runs)
			font_size = None
			for r in runs:
				if r.get('fontSizePt'):
					font_size = r.get('fontSizePt')
					break
			alignment = block.get('align', 'left')
			
			# Build formatting hints
			formatting_hints = []
			if has_bold:
				formatting_hints.append("BOLD")
			if has_underline:
				formatting_hints.append("UNDERLINE")
			if font_size and font_size != 11.0:  # 11pt is default, only note if different
				formatting_hints.append(f"FONT_SIZE_{int(font_size)}pt")
			if alignment and alignment != 'left':
				formatting_hints.append(f"ALIGN_{alignment.upper()}")
			
			# Include formatting information in the output
			formatting_note = f" [FORMATTING: {', '.join(formatting_hints)}]" if formatting_hints else ""
			formatted.append(f"Paragraph {idx + 1}: {cleaned_text[:char_limit]}{formatting_note}")
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
	
	# Claude has 200K context window - we can be much more generous with content
	# Include ALL blocks for most documents, only sample for extremely large ones
	total_blocks = len(formatted)
	
	# With Claude's 200K context, we have ~150K tokens for input after reserving output
	# That's roughly 450,000 characters of content
	max_ir_chars = 400000  # ~133K tokens - plenty of room in Claude's 200K context
	max_blocks_to_include = 2000  # Include all blocks for even very large documents
	
	if total_blocks > max_blocks_to_include:
		# Only for extremely large documents (2000+ blocks)
		# Smart sampling: take beginning, sample middle, take end
		beginning_count = 500
		end_count = 500
		middle_count = max_blocks_to_include - beginning_count - end_count
		
		sampled = []
		sampled.extend(formatted[:beginning_count])
		
		if total_blocks > beginning_count + end_count:
			middle_start = beginning_count
			middle_end = total_blocks - end_count
			middle_range = middle_end - middle_start
			
			if middle_range > 0 and middle_count > 0:
				step = max(1, middle_range // middle_count)
				for i in range(middle_start, middle_end, step):
					if len(sampled) < max_blocks_to_include - end_count:
						sampled.append(formatted[i])
		
		sampled.extend(formatted[-end_count:])
		sampled = sampled[:max_blocks_to_include]
		
		result = '\n'.join(sampled)
		
		if len(result) > max_ir_chars:
			result = result[:max_ir_chars]
			result += f"\n\n[NOTE: Document truncated at {max_ir_chars} chars. Document has {total_blocks} total content blocks. You MUST still include ALL conditional sections, ALL state-specific content patterns, and ALL paragraph structures from the ENTIRE document.]"
		else:
			result += f"\n\n[NOTE: Document has {total_blocks} total content blocks (sampled {len(sampled)}). You MUST include ALL conditional sections, ALL state-specific content, and ALL paragraphs from the ENTIRE document structure.]"
		return result
	
	return '\n'.join(formatted)

def build_prompt(ir, few_shot_examples, user_instruction=None):
	"""Build the complete prompt for Claude API"""
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
- CRITICAL: REMOVE ALL parenthesis descriptions that are metadata - these are NOT actual content:
  * Remove: "(Property Line 1/Street Address)", "(Due Date)", "(Delinquent Balance)", "(Accrued Late Charge Balance)", "(NSF Balance)", "(Mortgagor Recoverable Corporate Advance Balance)", "(Other Fees)", "(Suspense Balance)"
  * Keep: "(the Property)" - this is actual content, not metadata
  * Pattern: If parentheses contain words like "Balance", "Date", "Address", "Number", "Line", "Code" after a variable tag, it's likely metadata - REMOVE IT
- NEVER include conditional salutation logic - ALWAYS use <div>Dear {[Salutation]},</div>
- ONLY include Loan Number/RE table if Document Content shows EXPLICIT labels ("Loan Number:", "RE:") as separate sections - DO NOT create table just because property address variables appear in content
- ALWAYS format with newlines - each tag on its own line
- CRITICAL: Check Document Content order - subject lines may appear BEFORE or AFTER salutation depending on document - extract them in the order they appear

Document Content:
""" + ir_content + """

"""
	
	if user_instruction:
		user_message += f"Additional Instruction: {user_instruction}\n\n"
	
	user_message += """CRITICAL: You MUST format the HTML with proper newlines. Each HTML element MUST be on its own line.

Generate the HTML template following these EXACT rules:

STEP 0 - CRITICAL: PRESERVE EXACT PARAGRAPH ORDER AND SEQUENCE:
   - CRITICAL: Extract paragraphs in the EXACT order they appear in Document Content
   - CRITICAL: Do NOT reorder paragraphs - maintain the sequence from the source document
   - CRITICAL: Include ALL paragraphs, including:
     * Enclosures sections (e.g., "Enclosures:" followed by bullet points)
     * Bullet point lists at the end of documents
     * Closing paragraphs before signatures
     * All content from start to finish
   - CRITICAL: When you see "Enclosures:" or similar sections, include them AFTER the signature block
   - CRITICAL: When you see bullet points after "Enclosures:" or similar headers, format them as a table (like other bullet points)
   - CRITICAL: Scan the ENTIRE Document Content from beginning to end - do NOT stop early
   - CRITICAL: Count paragraphs in Document Content and verify you've included them all in the correct order
   - CRITICAL: If Document Content shows paragraph A, then paragraph B, then paragraph C, your HTML MUST show them in that exact order: A → B → C
   - WRONG: Reordering paragraphs or skipping paragraphs at the end
   - CORRECT: Including all paragraphs in the exact sequence they appear in Document Content

STEP 1 - SYSTEMATIC CONTENT EXTRACTION AND ANALYSIS:

1. Extract ONLY actual document content - ignore variable definitions, conditional text, and instructions
   - CRITICAL: Remove ALL parenthesis descriptions that are metadata (variable descriptions):
     * These appear after variable tags: {[M567]} (Property Line 1/Street Address) → {[M567]}
     * These appear in calculations: {[M591]} (Delinquent Balance) + {[M015]} (Accrued Late Charge Balance) → {[M591]} + {[M015]}
     * Common patterns: (Property Line X/...), (Due Date), (Delinquent Balance), (Accrued Late Charge Balance), (NSF Balance), (Mortgagor Recoverable Corporate Advance Balance), (Other Fees), (Suspense Balance)
     * REMOVE these - they are NOT actual document content, just metadata descriptions
     * EXCEPTION: Keep "(the Property)" as it's actual content, not metadata
     * CRITICAL: When you see text like "{[M567]} (Property Line 1/Street Address), {[M583]} (New Property Unit Number), {[M568]} (New Property Line 2/City State and Zip Code) (the Property)", remove ALL the parenthesis descriptions EXCEPT "(the Property)"
     * CRITICAL: In math expressions, remove ALL parenthesis descriptions BEFORE converting to Math() function

2. Use exact variable format {[TAG]} and remove last 2 chars from tags ending in E6/E8/etc. (e.g., L001E8 → {[L001]}, M029E6 → {[M029]}, M591E6 → {[M591]}, M015E6 → {[M015]})

3. Use {[plsMatrix.*]} for ALL company variables (CompanyLongName, CompanyShortName, CSPhoneNumber, HoursOfOperation, LossPreventionPhoneNumberTollFree, etc.) - NEVER use variables without plsMatrix prefix for company data
   - CORRECT: {[plsMatrix.LossPreventionPhoneNumberTollFree]}, {[plsMatrix.CSPhoneNumber]}, {[plsMatrix.CompanyLongName]}
   - WRONG: {[LossPreventionPhoneNumberTollFree]}, {[CSPhoneNumber]}, {[CompanyLongName]} ← Missing plsMatrix prefix

4. ALWAYS use <div>Dear {[Salutation]},</div> for salutations - NEVER include conditional salutation logic

5. Convert math expressions properly - CRITICAL SYSTEMATIC CONVERSION:
   - STEP 1: Identify math expressions in Document Content - look for patterns like:
     * Variable tags followed by +, -, *, /, or ÷
     * Multiple variable tags with operators: "[M591] + [M015] + [M497] + [M585] + [C004] - [M013]"
     * Expressions with division: "[Q178E2 ÷ Q177]" or "[Q178 ÷ Q177]"
     * Expressions that span multiple lines or have many variables
     * Expressions wrapped in parentheses: "$([M591E6] + [M015E6] + [M497E6] + [M585E6] + [C004E6] - [M013E6])"
   - STEP 2: CRITICAL - Scan the ENTIRE expression from start to finish:
     * Find the opening parenthesis or start of the expression
     * Scan through ALL variables and operators until you reach the closing parenthesis or end
     * DO NOT stop after the first few variables - capture ALL of them
     * Look for BOTH additions (+) AND subtractions (-) - expressions can have both
     * Count all variables: if you see 6 variables, include all 6; if you see 10, include all 10
   - STEP 3: Convert ALL math expressions to a SINGLE Math() function - NEVER use multiple Money() calls
   - STEP 4: Remove E suffixes from tags BEFORE putting in Math():
     * M591E6 → {[M591]}, M015E6 → {[M015]}, M497E6 → {[M497]}, M585E6 → {[M585]}, C004E6 → {[C004]}, M013E6 → {[M013]}
     * Q178E2 → {[Q178]}
   - STEP 5: Convert operators:
     * ÷ → /
     * Keep +, -, * as-is
   - STEP 6: Wrap entire expression in ONE Math() function with |Money format
   - CORRECT EXAMPLES:
     * "$([M591E6] (Delinquent Balance) + [M015E6] (Accrued Late Charge Balance) + [M497E6] (NSF Balance) + [M585E6] (Mortgagor Recoverable Corporate Advance Balance) + [C004E6] (Other Fees)) - [M013E6] (Suspense Balance))" → {Math({[M591]} + {[M015]} + {[M497]} + {[M585]} + {[C004]} - {[M013]}|Money)}
     * "[M591] + [M015] + [M497] + [M585] + [C004] - [M013]" → {Math({[M591]} + {[M015]} + {[M497]} + {[M585]} + {[C004]} - {[M013]}|Money)}
     * "[Q178E2 ÷ Q177]" → {Math({[Q178]} / {[Q177]}|Money)}
   - WRONG EXAMPLES (DO NOT DO THIS):
     * {Math({[M591]} + {[M015]} + {[M497]} + {[M585]}|Money)} ← WRONG: Missing C004 and M013
     * {Money({[M591]})} + {Money({[M015]})} + {Money({[M497]})} ← WRONG: Multiple Money() calls
     * {Money({[M591]} + {[M015]})} ← WRONG: Money() doesn't do math, use Math()
   - CRITICAL: Scan the ENTIRE expression - do NOT stop after the first few variables
   - CRITICAL: Include ALL variables in the expression - count them and verify you have them all
   - CRITICAL: Look for BOTH additions (+) AND subtractions (-) - expressions often have both
   - CRITICAL: If you see a calculation with multiple variables and operators, it MUST be ONE Math() function with ALL variables
   - CRITICAL: Remove ALL parenthesis descriptions like "(Delinquent Balance)", "(NSF Balance)", "(Other Fees)", "(Suspense Balance)" BEFORE converting to Math()
   - CRITICAL: The Math() function handles the entire calculation - do NOT break it into multiple Money() calls
   - CRITICAL: When you see an expression like "$([M591E6] + [M015E6] + [M497E6] + [M585E6] + [C004E6] - [M013E6])", you MUST include ALL 6 variables (M591, M015, M497, M585, C004, M013) - do NOT stop at 4

6. Convert conditional logic properly: "If [M065] ≥ 'July 29, 1999' then print:" becomes {If('{[M065]}' &gt;= 'July 29, 1999')}...content...{End If}

7. CRITICAL CONDITIONAL SYNTAX - Follow this EXACT format:
   CORRECT: {If('{[M006]}' = 'FHA' AND {[M037]} &gt; 0)}
   WRONG: {If({[M006]} = 'FHA' AND {[M037]} > 0)}  ← Missing quotes around variable, wrong comparison operator
   - Variables in string comparisons need quotes: '{[TAG]}'
   - Variables in numeric comparisons don't need quotes: {[TAG]}
   - Always use &gt; not > for greater than
   - Always use &lt; not < for less than
   - Always use &lt;&gt; not != or <> for not equal
   - CRITICAL: Use {Else If('{[TAG]}' = 'value')} for multiple conditions, NOT nested {Else}{If(...)}{End If}
   - CORRECT: {If('{[M009]}' &lt;&gt; ',')}...{Else If('{[M009]}' = ',')}...{End If}
   - WRONG: {If('{[M009]}' != ',')}...{Else}{If('{[M009]}' = ',')}...{End If}{End If} ← Nested conditionals are wrong

8. When you see text about "For loans closed on or after" or "For loans closed before", wrap it in {If()} conditionals based on [M065]

9. CRITICAL DATE COMPARISONS: For date comparisons in IF functions, dates must be in numeric format (yyyyMMdd) to be evaluated correctly, otherwise they will be compared as strings or interpreted as math. The Date() function's second parameter is for format (uses C# DateTime format strings). 
   - Example: {If((Date({[M065]}|yyyyMMdd) &gt;= 19990729))} - NO QUOTES around the date value, NO DASHES (to avoid subtraction)
   - Date() format examples: {Date({[M035]}|MMMM yyyy)} produces "September 2034", {Date({[TAG]}|MM/dd/yyyy)} produces "05/29/2015"
   - For comparisons, always use numeric format: yyyyMMdd WITHOUT quotes or dashes (e.g., 19990729, not '1999-07-29' or 1999-07-29)

10. SYSTEMATIC FORMATTING ANALYSIS - Perform these steps in order:
    a) Scan ALL paragraphs for [FORMATTING: BOLD] notes
    b) For each paragraph with BOLD, identify what should be bold (see BOLD TEXT ANALYSIS section)
    c) Scan for bullet points (•, -, *, numbered lists)
    d) Format each set of bullet points as a table
    e) Check for Loan Number/RE table requirements (see LOAN NUMBER AND RE: TABLE section)
    f) Verify ALL content is included (count paragraphs)
8. PRESERVE STYLING from source document - CRITICAL SYSTEMATIC ANALYSIS:
   - STEP 1: Scan EVERY paragraph in Document Content for [FORMATTING: ...] notes
   - STEP 2: If a paragraph has [FORMATTING: BOLD], wrap the appropriate text in <b> tags
   - STEP 3: If a paragraph has [FORMATTING: UNDERLINE], wrap in <u> tags
   - STEP 4: If a paragraph has [FORMATTING: FONT_SIZE_Xpt], add style="font-size: Xpt"
   - STEP 5: If a paragraph has [FORMATTING: ALIGN_CENTER], add style="text-align: center"
   - CRITICAL: Check EVERY paragraph for formatting notes - do NOT skip any
   - CRITICAL: If a paragraph shows [FORMATTING: BOLD], identify which words/phrases should be bold:
     * If the entire paragraph should be bold: <div><b>entire text</b></div>
     * If only part should be bold: <div>regular text <b>bold portion</b> more regular text</div>
     * Common bold patterns: section headers, program names (like "EMAP"), important phrases ("within 60 days"), contact info
   - CRITICAL: Look for patterns where specific words/phrases are bold:
     * Program names: "Emergency Mortgage Assistance Program (EMAP)" → <b>Emergency Mortgage Assistance Program (EMAP)</b>
     * Time-sensitive phrases: "within 60 days" → <b>within 60 days</b>
     * Section headers: "You may be eligible for EMAP assistance if:" → <b>You may be eligible for EMAP assistance if:</b>
     * Contact info: Phone numbers, organization names → <b>Connecticut Housing Finance Authority (CHFA)</b>
   - CRITICAL: When you see [FORMATTING: BOLD] on a paragraph, analyze the content to determine what should be bold:
     * If it's a short phrase or header → entire paragraph bold
     * If it's a longer paragraph → identify the key phrase(s) that should be bold
     * Conditional instruction lines: "If the Mortgage has been modified under...please note that:" → <div><b>If the Mortgage has been modified...</b></div>
   - CRITICAL: Conditional sections (inside {If()} blocks) can also have formatting - check for [FORMATTING: BOLD] notes even inside conditionals
   - CRITICAL: When formatting conditional sections, preserve ALL formatting from the source - if a line is bold in the source, it should be bold in the output even if it's inside a conditional
   - Examples:
     * "Emergency Mortgage Assistance Program (EMAP)" → <b>Emergency Mortgage Assistance Program (EMAP)</b>
     * "You may be eligible for EMAP assistance if:" → <b>You may be eligible for EMAP assistance if:</b>
     * "within 60 days" → <b>within 60 days</b>
     * "Connecticut Housing Finance Authority (CHFA)" → <b>Connecticut Housing Finance Authority (CHFA)</b>
     * Phone numbers: "{[plsMatrix.CSPhoneNumber]}" → <b>{[plsMatrix.CSPhoneNumber]}</b>
   - Centered text: style="text-align: center"
   - Font size: style="font-size: 14pt" (or whatever size is in the document)
   - Bold: <b>...</b>
   - Underlined: <u>...</u>
   - Combined: <div style="text-align: center; font-size: 14pt"><b>...</b></div>
   - Look at the Document Content for [FORMATTING: ...] notes - these tell you EXACTLY what formatting to apply
9. For tables, extract the ACTUAL table structure and content from the document - don't generate placeholder tables with "Column 1, Column 2" etc. - look at the LM401 example to see the correct 3-column table format
10. CRITICAL: If you see table content in the Document Content (look for "Table X" entries), you MUST include that table in your output - NEVER skip tables

STEP 2 - STRUCTURE (MANDATORY - DETECT FROM DOCUMENT):
CRITICAL: You MUST analyze the Document Content to determine the ACTUAL header structure - different documents have different layouts!

1. HEADER DETECTION - Look at the Document Content to determine the correct header type:
   - CRITICAL HEADER LOGIC (in priority order):
     a) If Document Content mentions NMLS or NMLSID → Use: <div>{Header(NMLSID)}</div>
     b) If Document Content shows H003 with a conditional (e.g., "IF {[H003]} = '*' or 'NULL'; then suppress print of line; else produce:") → Use: <div>{Insert(H003 TagHeader)}</div>
     c) If Document Content shows just {[tagHeader]} or tagHeader without H003 conditional → Use: <div>{[tagHeader]}</div>
     d) DEFAULT: Use <div>{Insert(H003 TagHeader)}</div> for most documents
   - IMPORTANT: Check Document Content for header structure - if it shows tagHeader directly without H003 conditional, use {tagHeader}
   - IMPORTANT: If H003 has a conditional (suppress if empty), use {Insert(H003 TagHeader)}
   - Extract the EXACT header structure from the Document Content

2. LOAN NUMBER AND RE: TABLE - CRITICAL SYSTEMATIC DETECTION:
   - STEP 1: Scan Document Content for EXPLICIT labels like "Loan Number:" or "RE:" or "Re:" appearing as standalone text (not just variable tags)
   - STEP 2: Look for patterns where these labels appear as SEPARATE paragraphs or table rows:
     * "Loan Number:" followed by [M594] on the same line or next line
     * "RE:" or "Re:" followed by property address variables on the same line or next line
     * These should appear as DISTINCT labeled sections, not just variables mentioned in content paragraphs
   - STEP 3: CRITICAL DISTINCTION - Do NOT create a table just because property address variables (M567, M583, M568) appear in content:
     * WRONG: If you see "property located at {[M567]}, {[M583]}, {[M568]}" in a paragraph → This is NOT a Loan Number/RE table
     * CORRECT: If you see a separate paragraph/line like "Loan Number: [M594]" or "RE: [M567]" → This IS a Loan Number/RE table
   - STEP 4: Only create the table if you find EXPLICIT labels ("Loan Number:", "RE:", "Re:") appearing as separate labeled sections
   - STEP 5: If labels exist, create table with:
     * First row: Loan Number label (extract EXACT label from Document Content) → {[M594]}
     * Second row: RE: label (extract EXACT label) → {Compress({[M567]}|{[M583]}|{[M568]})}
   - STEP 6: Format labels as bold: <td width="20%" valign="top"><b>Loan Number:</b></td>
   - CRITICAL: ONLY include this table if Document Content shows EXPLICIT labels like "Loan Number:" or "RE:" as separate labeled sections
   - CRITICAL: DO NOT create this table just because property address variables appear in regular content paragraphs
   - CRITICAL: If property address is mentioned inline in content (e.g., "property located at {[M567]}"), that is NOT a Loan Number/RE table - skip it
   - CRITICAL: Extract the EXACT label text from Document Content:
     * If Document Content shows "Loan Number: [M594]" → Use EXACTLY "Loan Number:" as the label
     * If Document Content shows "RE: [M567]" → Use EXACTLY "RE:" as the label
     * If Document Content shows "Re: Loan Number: [M594]" → Use EXACTLY "Re: Loan Number:" as the label
     * DO NOT combine or modify labels - extract them EXACTLY as they appear
   - CRITICAL: Format as: <table width="100%"><tbody><tr><td width="20%" valign="top"><b>EXACT_LABEL:</b></td><td>{[TAG]}</td></tr><tr><td width="20%" valign="top"><b>RE:</b></td><td>{Compress({[M567]}|{[M583]}|{[M568]})}</td></tr></tbody></table>
   - ONLY skip this table if Document Content does NOT show explicit "Loan Number:" or "RE:" labels as separate sections

3. STANDARD STRUCTURE (use as base, but ADAPT based on Document Content):
<div>{Insert(H003 TagHeader)}</div>  <!-- DEFAULT: Use {Insert(H003 TagHeader)} unless NMLS is mentioned. Only use {[tagHeader]} if Document Content explicitly shows tagHeader without H003 -->
<br>
<div>{[L001]}</div>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>
<!-- CRITICAL: Loan Number and RE: table - ONLY include if Document Content shows EXPLICIT labels like "Loan Number:" or "RE:" as separate labeled sections -->
<!-- DO NOT create this table just because property address variables (M567, M583, M568) appear in content paragraphs -->
<!-- ONLY create if you see explicit labels like "Loan Number: [M594]" or "RE: [M567]" as separate sections -->
[Loan Number/RE table ONLY if explicit labels exist - format as:
<table width="100%"><tbody><tr>
  <td width="20%" valign="top"><b>EXACT_LABEL_FROM_DOC:</b></td>  <!-- Extract EXACT label from Document Content - DO NOT modify, make label bold -->
  <td>{[M594]}</td>
</tr><tr>
  <td width="20%" valign="top"><b>RE:</b></td>  <!-- Extract EXACT label from Document Content - DO NOT modify, make label bold -->
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table>
<br>
]
[Conditional FHA/RHS sections if present - format as {If('{[M006]}' = 'FHA' AND {[M037]} &gt; 0)}<div>FHA Case Number: {[M037]}</div>{End If}]
<br>
<!-- CRITICAL: Check Document Content order - subject line may come BEFORE or AFTER salutation -->
[Subject line if present - check Document Content order, format as <div><b>Subject: ...</b></div>]
<br>
<div>Dear {[Salutation]},</div>
<br>
[Content paragraphs here - match spacing from source document]

CRITICAL: YOU MUST INCLUDE ALL CONTENT FROM THE DOCUMENT IN THE EXACT ORDER IT APPEARS - DO NOT STOP EARLY OR REORDER:
- Include EVERY paragraph shown in the Document Content above - COUNT THEM and make sure you include ALL
- CRITICAL: Preserve the EXACT order of paragraphs as they appear in Document Content - do NOT reorder them
- CRITICAL: If Document Content shows paragraph A, then B, then C, your HTML MUST show A → B → C in that exact order
- CRITICAL: Include ALL content at the END of documents, including:
  * Enclosures sections (e.g., "Enclosures:" followed by bullet points)
  * Bullet point lists after "Enclosures:" or similar headers - format these as tables
  * Closing paragraphs before signatures
  * All final content sections
  * Paragraphs that appear AFTER conditional blocks (e.g., "If you have any questions" after {End If})
- CRITICAL: When you see "Enclosures:" or similar headers, include them AFTER the signature block
- CRITICAL: When you see bullet points after "Enclosures:", format them as a table (like other bullet points)
- CRITICAL: Paragraphs that appear after conditional {End If} blocks should be OUTSIDE the conditional - check Document Content order carefully
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
- CRITICAL: Documents can have MULTIPLE conditionals throughout - you MUST include ALL conditionals, not just the first one
- CRITICAL: After formatting one conditional block ({If()}...{End If}), continue scanning the Document Content for MORE conditionals - include ALL of them
- CRITICAL: If you see conditional logic patterns like "If [TAG] = VALUE" or "If [TAG] NOT IN (...)" multiple times in the Document Content, format EACH occurrence as a separate {If()}...{End If} block
- CRITICAL: Do NOT stop after formatting the first conditional - continue reading and include ALL conditionals throughout the ENTIRE document
- Include closing signature section with proper spacing: <div>Sincerely,</div><br><br><br><div>Department Name</div><div>{[plsMatrix.CompanyLongName]}</div><br><br>{If('{[M007]}' = '48')}<div><b><u>Wisconsin Property Owners</u></b> – Notice: See Reverse Side (or attached) for Important Information</div>{End If}
- Include any conditional sections at the end (like Wisconsin notice)
- Include contact information section: <div>Please review the circumstances listed above...</div> with company address lines if present in Document Content
- If a paragraph starts with text that should be bold (like "This notice is to advise you...", "Please note", "IMPORTANT"), wrap that portion in <b> tags: <div><b>Bold portion...</b> rest of paragraph</div>
- CRITICAL: Only format as bullet point tables when the Document Content ACTUALLY shows bullet points (•, -, *, or numbered lists like 1., 2., 3.)
- CRITICAL: Do NOT format regular consecutive paragraphs as bullet points unless they are ACTUALLY bullet points in the Document Content
- CRITICAL: After section headers ending with ":" (like "Next Steps:", "Forbearance Plan Terms:", "Important:", etc.), check if the following paragraphs are ACTUALLY bullet points (look for •, -, *, or numbered lists) - only then format them as tables
- CRITICAL: If consecutive paragraphs after a section header are just regular text paragraphs (not bullet points), format them as regular <div> tags, NOT as a bullet point table
- CRITICAL: Documents can have MULTIPLE sets of bullet points - you MUST check for and format ALL sets throughout the ENTIRE document, not just the first one
- CRITICAL: Only format as bullet point tables when you see actual bullet characters (•, -, *) or numbered lists (1., 2., 3.) in the Document Content - do NOT assume consecutive paragraphs are bullet points
- CRITICAL: After formatting one set of bullet points, CONTINUE scanning the Document Content for MORE sets - do not stop after the first set
- CRITICAL: If you formatted bullet points as a table, IMMEDIATELY continue reading - if the next paragraphs also look like list items, format THOSE as a table too
- CRITICAL: Do NOT format just the first set of bullet points and then leave subsequent sets as regular divs - ALL bullet point sets must be formatted as tables
- CRITICAL: Even if you've already formatted one bullet point table, continue reading the Document Content - if you encounter another section header followed by consecutive paragraphs that look like list items, format THOSE as a table as well
- CRITICAL: Look for patterns throughout the ENTIRE document: section header → consecutive paragraphs → these should be bullet point tables. This pattern can occur MULTIPLE times in one document.
- CRITICAL: Look for ALL paragraphs in the Document Content - count them and make sure you include EVERY SINGLE ONE
- CRITICAL: If the Document Content shows styled text (bold, centered, larger font), you MUST preserve that styling in the HTML output
- CRITICAL: NEVER stop after a section header - always include the bullet points/content that follows section headers
- CRITICAL: Scan the ENTIRE Document Content from beginning to end, checking for ALL bullet point sets - there may be multiple sets scattered throughout the document
- CRITICAL: When you encounter consecutive paragraphs that are ACTUALLY bullet points (with •, -, *, or numbered lists) in the Document Content, format them as a table - do this for EVERY occurrence, not just the first one
- CRITICAL: After formatting one bullet point table, IMMEDIATELY check the next paragraphs - if they are ALSO actual bullet points (with •, -, *, or numbered lists), format THOSE as a table too
- CRITICAL: Do NOT format just the first bullet point set and then stop - continue checking and formatting ALL bullet point sets throughout the ENTIRE document
- CRITICAL: If you see a section header followed by ACTUAL bullet points (•, -, *, or numbered lists), format them as a table. Then continue reading - if you see ANOTHER section header followed by MORE actual bullet points, format THOSE as a table too. Repeat this process for ALL section headers and ALL bullet point sets in the document.
- CRITICAL: Do NOT format regular paragraphs as bullet points - only format when you see actual bullet characters (•, -, *) or numbered lists (1., 2., 3.) in the Document Content
- CRITICAL: NEVER truncate or omit content when converting bullet points to tables - include the COMPLETE text from each bullet point paragraph, including all sentences, clauses, and conditional statements
- CRITICAL: If a bullet point paragraph contains multiple sentences separated by periods, include ALL sentences in the table cell - do not stop after the first sentence
- CRITICAL: Preserve ALL content - if the Document Content shows a bullet point with text like "Sentence 1. Sentence 2. Sentence 3.", include ALL three sentences in the <td> tag
- CRITICAL: For ALL-CAPS text (like legal notices, warnings, or important statements), preserve the COMPLETE text - do not truncate ALL-CAPS paragraphs
- CRITICAL: If Document Content shows ALL-CAPS text with multiple sentences (e.g., "FIRST SENTENCE. SECOND SENTENCE. THIRD SENTENCE."), include ALL sentences - these are often important legal notices that must be complete
- CRITICAL: When you see ALL-CAPS text in Document Content, it's likely an important legal notice - preserve it COMPLETELY, including all sentences and clauses

CRITICAL SYSTEMATIC ANALYSIS FOR BULLET POINTS AND BOLD TEXT:

BOLD TEXT ANALYSIS (MUST PERFORM FOR EVERY PARAGRAPH):
- STEP 1: Read through Document Content paragraph by paragraph
- STEP 2: For each paragraph, check if it has [FORMATTING: BOLD] note
- STEP 3: If [FORMATTING: BOLD] is present, identify what should be bold:
  * Scan the paragraph text for key phrases that are commonly bold:
    - Program names: "EMAP", "Emergency Mortgage Assistance Program", "CHFA", "Connecticut Housing Finance Authority"
    - Time-sensitive phrases: "within 60 days", "within X days"
    - Section headers ending with ":": "You may be eligible for EMAP assistance if:", "Subject:"
    - Important contact info: Phone numbers, organization names
    - Important legal phrases: "THIS DOCUMENT IS AN ATTEMPT TO COLLECT A DEBT"
  * If entire paragraph is a header/short phrase → wrap entire paragraph: <div><b>entire text</b></div>
  * If only part is bold → wrap specific phrase: <div>regular text <b>bold phrase</b> more text</div>
- STEP 4: Apply bold formatting consistently throughout the document
- STEP 5: Double-check that ALL [FORMATTING: BOLD] notes have been addressed

BULLET POINTS ANALYSIS (MUST PERFORM SYSTEMATICALLY):
- STEP 1: Scan Document Content for actual bullet characters (•, -, *, or numbered lists like 1., 2., 3.)
- STEP 2: When you find bullet points, identify where they start and end
- STEP 3: Format ALL consecutive bullet points as a single table:
  Example: <table width="100%"><tbody><tr><td width="3%" valign="top" style="text-align: center">•</td><td>Bullet point text here</td></tr><tr><td width="3%" valign="top" style="text-align: center">•</td><td>Next bullet point</td></tr></tbody></table>
- STEP 4: Continue scanning after formatting one set - look for MORE bullet point sets
- STEP 5: Format EACH set of bullet points as a separate table
- CRITICAL: When converting bullet points to tables, you MUST include the COMPLETE text from each bullet point - NEVER truncate or omit any part of the content
- CRITICAL: If a bullet point has multiple sentences or clauses, include ALL of them in the table cell - do not stop after the first sentence
- CRITICAL: Preserve ALL content from bullet points - if the Document Content shows a long bullet point with multiple sentences, include ALL sentences in the <td> tag
- CRITICAL: After section headers like "Next Steps:", "Forbearance Plan Terms:", "Important:", etc., check if the following paragraphs are ACTUALLY bullet points (with •, -, *, or numbered lists) - only then format them as tables
- CRITICAL: If you see consecutive paragraphs that are ACTUALLY bullet points (with •, -, *, or numbered lists), format them as a bullet point table
- CRITICAL: Do NOT format regular consecutive paragraphs as bullet points - only format when you see actual bullet characters (•, -, *) or numbered lists (1., 2., 3.) in the Document Content
- CRITICAL EXAMPLE: Only format as bullet point table if Document Content ACTUALLY shows bullet characters:
  If Document Content shows:
  "Next Steps:
  • Paragraph 1 about step 1
  • Paragraph 2 about step 2
  • Paragraph 3 about step 3"
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
  
  If Document Content shows (NO bullet characters):
  "Next Steps:
  Paragraph 1 about step 1
  Paragraph 2 about step 2"
  Then format as regular divs (NOT a bullet point table):
  <div><b>Next Steps:</b></div>
  <br>
  <div>Paragraph 1 about step 1</div>
  <div>Paragraph 2 about step 2</div>
  
- CRITICAL EXAMPLE OF MULTIPLE BULLET POINT SETS IN ONE DOCUMENT:
  Only format as bullet point tables if Document Content ACTUALLY shows bullet characters (•, -, *, or numbered lists):
  If Document Content shows:
  "Next Steps:
  • Step 1 text
  • Step 2 text
  
  Additional Information:
  • Info item 1
  • Info item 2
  
  Important Notes:
  • Note 1
  • Note 2"
  
  Then format ALL THREE sets as separate tables (NOT just the first one):
  <div><b>Next Steps:</b></div>
  <br>
  <table width="100%"><tbody>
  <tr><td width="3%" valign="top" style="text-align: center">•</td><td>Step 1 text</td></tr>
  <tr><td width="3%" valign="top" style="text-align: center">•</td><td>Step 2 text</td></tr>
  </tbody></table>
  <br>
  <div><b>Additional Information:</b></div>
  <br>
  <table width="100%"><tbody>
  <tr><td width="3%" valign="top" style="text-align: center">•</td><td>Info item 1</td></tr>
  <tr><td width="3%" valign="top" style="text-align: center">•</td><td>Info item 2</td></tr>
  </tbody></table>
  <br>
  <div><b>Important Notes:</b></div>
  <br>
  <table width="100%"><tbody>
  <tr><td width="3%" valign="top" style="text-align: center">•</td><td>Note 1</td></tr>
  <tr><td width="3%" valign="top" style="text-align: center">•</td><td>Note 2</td></tr>
  </tbody></table>
  
  WRONG: Do NOT format just the first set and leave the rest as regular divs like this:
  <div><b>Next Steps:</b></div>
  <br>
  <table>...</table>  <!-- First set formatted correctly -->
  <br>
  <div><b>Additional Information:</b></div>
  <br>
  <div>Info item 1</div>  <!-- WRONG - should be a table -->
  <div>Info item 2</div>  <!-- WRONG - should be a table -->
  
  ALSO WRONG: Do NOT format regular paragraphs as bullet points:
  If Document Content shows:
  "Next Steps:
  Paragraph 1 text (no bullet character)
  Paragraph 2 text (no bullet character)"
  Then format as regular divs:
  <div><b>Next Steps:</b></div>
  <br>
  <div>Paragraph 1 text</div>
  <div>Paragraph 2 text</div>
  NOT as a bullet point table (because there are no actual bullet characters)
  
- CRITICAL: Documents can have MULTIPLE sets of bullet points throughout - you MUST check for and format ALL of them:
  * After EVERY section header ending with ":", check for bullet points that follow
  * Look for bullet points in the middle of paragraphs (not just after headers)
  * Look for bullet points near the end of the document
  * If you formatted one set of bullet points, continue scanning the Document Content for MORE sets
  * DO NOT stop after formatting the first set - continue checking the ENTIRE document
  * Count how many section headers end with ":" - each one might have bullet points after it
  * CRITICAL: After formatting bullet points as a table, continue reading the Document Content - if you see MORE consecutive paragraphs that look like list items, format THOSE as a table too
  * CRITICAL: Do NOT convert just the first set of bullet points and then leave the rest as regular divs - ALL bullet point sets must be formatted as tables
  * CRITICAL: Scan through the ENTIRE Document Content from start to finish, identifying ALL sets of consecutive paragraphs that should be bullet points, and format EACH set as its own table
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
			
			if not ANTHROPIC_AVAILABLE:
				import_error = "Anthropic library not available. Install with: pip install anthropic. Make sure requirements.txt includes 'anthropic>=0.40.0'"
				print(f"ERROR: {import_error}")
				return self._send(500, {'success': False, 'error': import_error})
			
			# Get Anthropic API key from environment
			api_key = os.environ.get('ANTHROPIC_API_KEY')
			if not api_key:
				key_error = 'ANTHROPIC_API_KEY environment variable not set. Please set it in Vercel project settings → Environment Variables → Add ANTHROPIC_API_KEY'
				print(f"ERROR: {key_error}")
				print(f"Available env vars: {list(os.environ.keys())[:10]}...")  # Debug: show first 10 env vars
				return self._send(500, {'success': False, 'error': key_error})
			
			print(f"Anthropic API key found: {api_key[:10]}... (length: {len(api_key)})")
			
			# Initialize Anthropic client
			client = anthropic.Anthropic(api_key=api_key)
			
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
			
			# Call Anthropic Claude API
			try:
				model_name = "claude-sonnet-4-20250514"
				print(f"Calling Anthropic API with model: {model_name}")
				print(f"System prompt length: {len(full_system_prompt)}")
				print(f"User message length: {len(user_message)}")
				
				# Estimate token count - Claude has 200K context window
				total_input_chars = len(full_system_prompt) + len(user_message)
				estimated_input_tokens = total_input_chars // 3  # Conservative estimate
				
				# Claude's 200K context gives us plenty of room
				# Reserve generous output budget based on document size
				if estimated_input_tokens > 180000:
					return self._send(400, {
						'success': False,
						'error': f'Document is too large (~{estimated_input_tokens} input tokens, limit ~180,000). Please try a smaller document.'
					})
				
				# Scale output tokens based on document complexity
				ir_blocks = len(ir.get('blocks', []))
				if ir_blocks > 500:
					max_tokens = 16000  # Very large documents need more output
				elif ir_blocks > 100:
					max_tokens = 12000  # Large documents
				else:
					max_tokens = 8000   # Standard documents
				
				print(f"Document has {ir_blocks} blocks, estimated input tokens: ~{estimated_input_tokens}, using max_tokens={max_tokens}")
				
				response = client.messages.create(
					model=model_name,
					max_tokens=max_tokens,
					system=full_system_prompt,
					messages=[
						{"role": "user", "content": user_message}
					],
					temperature=0  # Deterministic
				)
				
				html = response.content[0].text.strip()
				print(f"Anthropic API call successful, HTML length: {len(html)}")
			except Exception as api_error:
				error_msg = f"Anthropic API error: {str(api_error)}"
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
				if 'API' in error_type or 'anthropic' in error_msg.lower():
					user_error_msg = f"Anthropic API Error: {error_msg}. Please check that ANTHROPIC_API_KEY is set correctly."
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

