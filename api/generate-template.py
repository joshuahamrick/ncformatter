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

try:
	from api.anthropic_retry import messages_create_with_retries
except ImportError:
	try:
		from anthropic_retry import messages_create_with_retries
	except ImportError:
		messages_create_with_retries = None  # type: ignore

try:
	from api.pii_scanner import scan_ir_for_pii, build_error_response, log_audit_event
except ImportError:
	try:
		from pii_scanner import scan_ir_for_pii, build_error_response, log_audit_event
	except ImportError:
		scan_ir_for_pii = None
		build_error_response = None
		log_audit_event = None

# Import normalization (we'll create a Python version)
def normalize_html(html):
	"""Minimal normalization - just clean up, let AI do the formatting"""
	if not html or not isinstance(html, str):
		return ''
	
	normalized = html
	
	# Remove business rule references
	normalized = re.sub(r'<div>\(see\s+["\'].*?Business Rules.*?\)</div>', '', normalized, flags=re.IGNORECASE | re.DOTALL)
	normalized = re.sub(r'<div>\(see\s+["\'].*?BKFS.*?\)</div>', '', normalized, flags=re.IGNORECASE | re.DOTALL)
	
	# Fix UNSTYLED nested divs (plain <div><div> with no attributes) but NOT styled nested divs
	# IMPORTANT: Do NOT collapse <div style="..."><div style="..."> — these are intentional nested structures
	# like the centered title box: <div style="text-align:center"><div style="display:inline-block;...">
	normalized = re.sub(r'<div><div>', '<div>', normalized)
	# Do NOT collapse </div></div> — intentional double close for nested divs like centered title box
	
	# Normalize line endings
	normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
	
	# Normalize <br> tags
	normalized = re.sub(r'<br\s*/?>', '<br>', normalized, flags=re.IGNORECASE)
	
	# NOTE: We do NOT collapse consecutive <br> tags here because intentional multi-break
	# spacing (e.g. <br><br> after language sections, <br><br><br><br> for signature gaps)
	# must be preserved. Claude is instructed to put multiple <br> on one line when intentional.
	
	# NOTE: Do NOT force <br> after Sincerely — spacing should match the source document.
	# The IR now preserves actual blank-line spacing from the docx.
	
	# Fix bare ampersands in HTML text content (outside template variables)
	# Process in segments: split on {template} blocks and fix & in non-template parts
	fixed_parts = []
	# Split on template variable/function blocks (including nested braces)
	i = 0
	while i < len(normalized):
		if normalized[i] == '{':
			# Find matching closing brace (handle nested braces)
			depth = 0
			j = i
			while j < len(normalized):
				if normalized[j] == '{':
					depth += 1
				elif normalized[j] == '}':
					depth -= 1
					if depth == 0:
						break
				j += 1
			fixed_parts.append(normalized[i:j+1])  # template block, unchanged
			i = j + 1
		else:
			# Find next { or end
			j = normalized.find('{', i)
			if j == -1:
				j = len(normalized)
			text_chunk = normalized[i:j]
		# Fix bare & that's not already an HTML entity (&amp; &lt; &gt; &quot; &#... &nbsp; etc.)
		text_chunk = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|nbsp;|#)', '&amp;', text_chunk)
			fixed_parts.append(text_chunk)
			i = j
	normalized = ''.join(fixed_parts)

	# Final cleanup: fix any &amp;nbsp; that ended up before {Font()} directives
	# This must run AFTER the bare-amp loop (which might re-encode &nbsp;)
	normalized = re.sub(r'&amp;nbsp;(\{Font\()', r'&nbsp;\1', normalized)
	
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
Generate HTML templates that match the exact formatting and content of the source document.
Use {[TAG]} format for variables, {[plsMatrix.*]} for company variables.
Remove last 2 characters from tag variables ending in digits/letters (e.g. L001E8 → L001).
Derive ALL structure, labels, and formatting from the source document — never assume or hardcode.
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
	
	# Few-shot training examples — curated to cover the widest range of formatting patterns.
	# ─────────────────────────────────────────────────────────────────────────────────────
	# FOUNDATIONAL EXAMPLES
	# These cover core patterns: conditionals, tables, lists, RE/loan number layouts,
	# centered headers, partial bold, Compress(), Math(), date functions, etc.
	foundational = [
		'MI001/MI001-formatted.html',       # PMI: numbered lists, partial bold, Money/Math calculations
		'CA003/CA003-formatted.html',        # ACH: conditionals, simple table layout
		'CA030/CA030-formatted.html',        # Initial contact: RE/Loan Number table, bullet list
		'LM401/LM401-formatted.html',        # Complex bordered table, conditional logic
		'WL009/WL009-formatted.html',        # HELOC Welcome: centered title, FAQ bold headers, contact block
		'FL103/FL103-formatted.html',        # Insurance notice: bold heading, Compress RE, mortgagee clause
	]

	# RECENTLY TRAINED EXAMPLES
	# These reflect the latest refinements to formatting rules.
	# Add new approved examples here as documents are trained and validated.
	recently_trained = [
		'CL008/CL008-formatted.html',       # Loss mit: 3-col RE table, numbered+bullet lists, soft-return splitting, &amp; encoding
		'IA004/IA004-formatted.html',        # FHA coverage term: colspan=2 loan row, bordered comparison table, Math() addition
		'FC001/FC001-formatted.html',        # Foreclosure notice: separate bullet tables, <br> within bullets, numbered lists, Compress address, OR separator, partial underline
		'LM300/LM300-formatted.html',       # HUD Pre-Foreclosure Sale: 2-col RE table with custom labels, 2-part Compress (no M583), margin-left bullets, no <br> after Sincerely
		'CL028/CL028-formatted.html',       # Illinois Affidavit of Defense: 60/40 IMPORTANT NOTICE header, bordered lender/consumer table, grid home table, border-bottom writing lines, dual 50/50 signature tables
		'ES014/ES014-formatted.html',       # Escrow Cancellation Request: Font() declaration, <hr> divider, Compress title box, account/borrower table, 80%-wide 40/1/20 signature tables, address section table, nested-table double-border warning box, plain TaxEmail at bottom
	]

	curated = foundational + recently_trained
	
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

	max_n = int(os.environ.get("FEW_SHOT_MAX_EXAMPLES", "0") or "0")
	if max_n > 0 and len(examples) > max_n:
		print(f"FEW_SHOT_MAX_EXAMPLES={max_n}: using first {max_n} of {len(examples)} few-shot examples")
		examples = examples[:max_n]

	return examples

def format_ir_for_prompt(ir):
	"""Format IR data into a readable prompt format - extract actual document content"""
	import re
	blocks = ir.get('blocks', [])
	formatted = []
	
	# Patterns to skip - these are metadata/instructions, not actual content
	# IMPORTANT: These should match EXACT metadata phrases, not parts of actual content
	skip_patterns = [
		'System Date',
		'New Bill Line',
		'Mailing Street Address',
		'Mailing City, State',
		'Foreign Country Code',
		'Foreign Postal Code',
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
	# REMOVED: 'Loan Number – No Dash' - was filtering out "Loan Number:" labels
	# REMOVED: 'Company Address Line' - was filtering out actual company address content
	
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
	
	para_counter = 0  # Sequential numbering - no gaps from skipped blanks
	for idx, block in enumerate(blocks):
		if block.get('type') == 'paragraph':
			runs = block.get('runs', [])
			text = ''.join([r.get('text', '') for r in runs]).strip()
			
			# Skip empty paragraphs — spacing is handled by template conventions, not blank lines
			# Exception: preserve empty list items (empty bullet/numbered items are intentional placeholders)
			# Exception: preserve blank paragraphs between list items (they indicate separate list groups)
			if not text or len(text) < 3:
				if block.get('isListItem') and (not text or len(text) < 3):
					# Empty list item — include it as an explicit empty placeholder
					list_level = block.get('listLevel', 0) or 0
					para_counter += 1
					formatted.append(f"Paragraph {para_counter}: [EMPTY_LIST_ITEM_LEVEL_{list_level}]")
				else:
					# Check if this blank paragraph falls between two list items
					# If so, it signals they should be in SEPARATE list tables
					prev_is_list = False
					next_is_list = False
					for prev_idx in range(idx - 1, max(0, idx - 3), -1):
						if blocks[prev_idx].get('type') == 'paragraph':
							prev_runs = blocks[prev_idx].get('runs', [])
							prev_text = ''.join([r.get('text', '') for r in prev_runs]).strip()
							if prev_text:
								prev_is_list = blocks[prev_idx].get('isListItem', False)
								break
					for next_idx in range(idx + 1, min(len(blocks), idx + 3)):
						if blocks[next_idx].get('type') == 'paragraph':
							next_runs = blocks[next_idx].get('runs', [])
							next_text = ''.join([r.get('text', '') for r in next_runs]).strip()
							if next_text:
								next_is_list = blocks[next_idx].get('isListItem', False)
								break
					if prev_is_list and next_is_list:
						para_counter += 1
						formatted.append(f"Paragraph {para_counter}: [LIST_SEPARATOR: blank line between list items — these are SEPARATE list groups, output as SEPARATE <div><table> blocks with <br> between them]")
				continue
			
			# Allow short text if it looks like a label or contains template markers
			is_label = (text.strip().endswith(':') or 
			           re.match(r'^(RE|Loan Number|Property Address|Subject):', text, re.IGNORECASE) or
			           '{{' in text or '[[' in text)  # Template variable markers
			
			# Check if this is a template structure line (has variable markers like [[M594]])
			has_template_vars = bool(re.search(r'\[\[?[A-Z]\w*\]\]?', text))
			
			# CRITICAL: Don't skip lines that contain template variables - these are actual content
			if has_template_vars:
				# This is template content, not just metadata
				pass  # Continue processing
			
			# Skip if it matches instruction patterns - but be VERY conservative
			# Only skip if it's clearly just a metadata instruction line, not actual content
			# CRITICAL: Never skip if line contains template variables like [[M594]] or {{CompanyLongName}}
			is_instruction = False
			if not has_template_vars:  # Only check instruction patterns if no template vars
				for pattern in instruction_patterns:
					if re.match(pattern, text, re.IGNORECASE):
						# Double-check: if it contains actual sentence content (periods, commas, etc.), it's probably content
						if not re.search(r'[.!?]\s+[A-Z]', text):  # No sentence structure
							is_instruction = True
							break
			
			if is_instruction:
				continue
			
			# Skip if it's just a variable definition (starts with [TAG] and short)
			# But don't skip if it's a label (like "Loan Number: [M594]" or "RE: [M567]")
			if not is_label and re.match(r'^\[[A-Z0-9]+\]\s+[A-Z]', text) and len(text) < 80:
				continue
			
			# Skip variable definitions like "[M563] [M564] [M565] [M566] (Mailing City), (State), (5-Digit Zip), (4-Digit Zip)"
			if re.search(r'\[M\d+\]\s+\[M\d+\]\s+\[M\d+\]', text):
				continue
			if re.search(r'\(Mailing City\)|\(State\)|\(5-Digit Zip\)|\(4-Digit Zip\)', text):
				continue
			
			# Skip if it contains skip patterns and is short (likely just metadata)
			# But don't skip labels or ALL-CAPS text (legal notices)
			if not is_label and any(pattern in text for pattern in skip_patterns):
				is_mostly_caps = len([c for c in text if c.isupper()]) > len(text) * 0.5
				if len(text) < 100 and not is_mostly_caps:  # Short = likely just metadata (unless ALL-CAPS)
					continue
				# If longer or ALL-CAPS, might be actual content - include it
			
			# Skip conditional salutation text
			if re.search(r'\(or if\s+\[.*\]\s+(and/or|present)\)', text, re.IGNORECASE):
				continue
			
			# Skip production conditional lines like "({[M838]} PLS-CLIENT-ID = <PLSID> Produce)"
			if re.match(r'^\(', text) and re.search(r'PLS-CLIENT-ID|PLS-CLIENT|Produce\s*\)\s*$', text, re.IGNORECASE):
				continue
			
			# Skip mailing/production instruction lines like "Letter to be sent via Certified Mail to the Mailing Address."
			if re.match(r'^Letter to be sent via\b', text, re.IGNORECASE):
				continue
			if re.match(r'^(This letter|Notice) (to be|is) sent via\b', text, re.IGNORECASE):
				continue
			
			# Skip business rule references
			if re.search(r'\(see\s+["\'].*Business Rules', text, re.IGNORECASE):
				continue
			if re.search(r'Letter Library Business Rules', text, re.IGNORECASE):
				continue
			
			# Skip lines that are just variable lists like "[M563] {[M564]} {[M565]} {[M566]}"
			if re.match(r'^(\[M\d+\]\s*)+', text) and len(text) < 150:
				continue
			
			# Detect line breaks within list items / paragraphs based on formatting transitions
			# In Word, soft returns within a single paragraph show as runs with distinct formatting shifts
			# (e.g., non-bold description → bold phone number → bold+underline URL)
			# We detect these transitions and insert [BR] markers for the AI
			if block.get('isListItem') and len(runs) > 1:
				content_runs = [r for r in runs if r.get('text', '').strip()]
				if len(content_runs) > 1:
					segments = []
					current_segment = []
					prev_bold = content_runs[0].get('bold', False)
					prev_underline = content_runs[0].get('underline', False)
					for r in content_runs:
						r_bold = r.get('bold', False)
						r_underline = r.get('underline', False)
						# Detect formatting transition that likely indicates a new visual line
						# Only trigger on bold change or underline appearing (not every minor run split)
						if (r_bold != prev_bold or (r_underline and not prev_underline)) and current_segment:
							seg_text = ''.join(s.get('text', '') for s in current_segment).strip()
							if seg_text:
								# Check if previous segment ends with ':' — common intro line before phone/URL
								if seg_text.endswith(':') or seg_text.endswith('Commission:'):
									segments.append(seg_text)
								else:
									segments.append(seg_text)
							current_segment = []
						current_segment.append(r)
						prev_bold = r_bold
						prev_underline = r_underline
					if current_segment:
						seg_text = ''.join(s.get('text', '') for s in current_segment).strip()
						if seg_text:
							segments.append(seg_text)
					# If we found multiple segments, mark them
					if len(segments) > 1:
						# Rebuild text with [BR] markers between segments
						text = ' [BR] '.join(segments)

			# This looks like actual content - include it
			# CRITICAL: Remove metadata descriptions in parentheses BEFORE including in prompt
			# These are variable descriptions like "(Property Line 1/Street Address)", "(Due Date)", "(Delinquent Balance)", etc.
			# Pattern: (Description text) that appears after variable tags or in variable definitions
			cleaned_text = text
			
			# CRITICAL: Extract template variables from markup
			# The source document may have variables in formats like:
			# - {[M594]} (our standard format)
			# - [[M594]] or {{M594}} (markup format)
			# - {[CompanyLongName]} or [[CompanyLongName]] (company variables)
			# Convert all to our standard {[TAG]} format
			
			# Remove markup instructions that wrap actual content
			# Examples from CA030:
			# - "(IF [[H003]] = '*' or 'NULL'; then suppress print of line; else produce:)"
			# - "(see "Additional Borrowers/Co-Borrowers" on Letter Library Business Rules...)"
			# Keep the content after these instructions
			
			# Remove conditional instruction prefixes like "IF [[TAG]] = value; then suppress..."
			cleaned_text = re.sub(r'^\(IF\s+\[\[?\w+\]\]?\s*[^;]+;\s*then\s+[^:]+:\s*\)', '', cleaned_text, flags=re.IGNORECASE).strip()
			
			# Remove "(see ...)" references
			cleaned_text = re.sub(r'\(see\s+["\'][^"\']+["\']\s+on\s+[^)]+\)', '', cleaned_text, flags=re.IGNORECASE).strip()
			
			# CRITICAL: Convert markup variable formats to standard format
			# Convert [[TAG]] to {[TAG]}
			cleaned_text = re.sub(r'\[\[([A-Z]\w+)\]\]', r'{[\1]}', cleaned_text)
			# Convert {{TAG}} to {[TAG]}
			cleaned_text = re.sub(r'\{\{([A-Z]\w+)\}\}', r'{[\1]}', cleaned_text)
			
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
			cleaned_text = re.sub(r'\s*\([A-Z][^)]*(?:Balance|Date|Address|Number|Line|Code|Indicator|Name)[^)]*\)', '', cleaned_text)
			
			# Strip known date offset annotations inline: "[L010E8] Today Plus 15 Days" → "[L010E8]"
			cleaned_text = re.sub(
				r'(\[(?:[A-Z]\d{3}[A-Za-z0-9]*)\])\s+(?:Today|System\s+Date|Current\s+Date)\s+(?:Plus|Minus|Less|More)\s+\d+\s+(?:Days?|Months?|Years?)',
				r'\1',
				cleaned_text,
				flags=re.IGNORECASE
			)
			# Strip other short annotation phrases after bracket variables: "[M594] Loan Number" etc.
			# Only strip if the phrase ends at a word boundary (space, period, or end of string)
			cleaned_text = re.sub(
				r'(\[(?:[A-Z]\d{3}[A-Za-z0-9]*)\])\s+(?:[A-Z][A-Za-z\-–]+(?:\s+[A-Z][A-Za-z\-–]+){0,4})(?=\s|,|\.|$)',
				r'\1',
				cleaned_text
			)
			# Convert METADATA annotations to clear directives instead of stripping
			# e.g. "*METADATA -ONLY PRODUCE LAST 4 DIGITS OF LOAN NUMBER*" → "[USE: {[loanNumberLast4]}]"
			def _convert_metadata(m):
				content = m.group(0).upper()
				if 'LAST 4 DIGITS' in content or 'LAST FOUR DIGITS' in content:
					return ' [USE: {[loanNumberLast4]}]'
				return ''  # strip unknown METADATA annotations
			cleaned_text = re.sub(r'\*METADATA[^*]*\*', _convert_metadata, cleaned_text)

			# Clean up extra spaces
			cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
			
			# For ALL-CAPS text (likely important legal notices), include more characters
			# Check if text is mostly uppercase - if so, include more to preserve complete notices
			is_mostly_uppercase = len([c for c in cleaned_text if c.isupper()]) > len(cleaned_text) * 0.5
			char_limit = 5000 if is_mostly_uppercase else 2000  # Increased: Claude has 200K context, we can include complete paragraphs
			
			# Extract formatting information (bold, underline, font size, alignment)
			has_bold = any(r.get('bold', False) for r in runs)
			has_underline = any(r.get('underline', False) for r in runs)
			
			# Check if PARTIAL bold (some runs bold, some not)
			bold_runs = [r for r in runs if r.get('bold', False) and r.get('text', '').strip()]
			non_bold_runs = [r for r in runs if not r.get('bold', False) and r.get('text', '').strip()]
			is_partial_bold = len(bold_runs) > 0 and len(non_bold_runs) > 0
			
			font_size = None
			for r in runs:
				if r.get('fontSizePt'):
					font_size = r.get('fontSizePt')
					break
			alignment = block.get('align', 'left')
			
			# Build formatting hints
			formatting_hints = []
			if has_bold:
				# Check if bold is ONLY on variable tags (client marks tags bold for visibility)
				import re as _re
				tag_pattern = _re.compile(r'^[\s\{\[\]]*[A-Z]\d{2,4}[A-Z]?\d*[\s\{\[\]]*$|^\s*\{?\[?[A-Z]\w+\]?\}?\s*$')
				bold_only_tags = all(
					tag_pattern.match(r.get('text', '').strip()) or _re.search(r'\{\[[\w\.]+\]\}', r.get('text', ''))
					for r in bold_runs
				) if bold_runs else False
				
				if is_partial_bold:
					if bold_only_tags:
						# Bold is only on tags - note this so Claude doesn't apply bold
						formatting_hints.append("BOLD_TAGS_ONLY")
					else:
						# Show which parts are bold
						bold_texts = [r.get('text', '').strip()[:50] for r in bold_runs[:3]]  # First 3 bold parts
						formatting_hints.append(f"PARTIAL_BOLD({'; '.join(bold_texts)})")
				else:
					if bold_only_tags and len(cleaned_text.strip()) < 20:
						formatting_hints.append("BOLD_TAGS_ONLY")
					else:
						formatting_hints.append("BOLD")
			if has_underline:
				# Check if PARTIAL underline (some runs underlined, some not)
				underline_runs = [r for r in runs if r.get('underline', False) and r.get('text', '').strip()]
				non_underline_runs = [r for r in runs if not r.get('underline', False) and r.get('text', '').strip()]
				is_partial_underline = len(underline_runs) > 0 and len(non_underline_runs) > 0
				if is_partial_underline:
					underline_texts = [r.get('text', '').strip()[:50] for r in underline_runs[:5]]
					formatting_hints.append(f"PARTIAL_UNDERLINE({'; '.join(underline_texts)})")
				else:
					formatting_hints.append("UNDERLINE")
			
			# Check for hyperlinks - these are dynamic variables (plsMatrix)
			has_hyperlink = any(r.get('isHyperlink', False) for r in runs)
			if has_hyperlink:
				hyperlink_texts = [r.get('text', '').strip()[:50] for r in runs if r.get('isHyperlink', False) and r.get('text', '').strip()]
				if hyperlink_texts:
					formatting_hints.append(f"HYPERLINK({'; '.join(hyperlink_texts)})")
			
			if font_size and (font_size >= 13.0 or font_size <= 8.0):  # Only flag headings/footnotes; skip common body sizes (8–12pt)
				formatting_hints.append(f"FONT_SIZE_{int(font_size)}pt")
			if alignment and alignment != 'left':
				formatting_hints.append(f"ALIGN_{alignment.upper()}")
			
			# Add indentation info for table format detection
			leading_spaces = block.get('leadingSpaces')
			if leading_spaces and leading_spaces > 0:
				formatting_hints.append(f"INDENT_{leading_spaces}spaces")
			
			# Add paragraph bottom border hint (signals horizontal rule separator)
			if block.get('borderBottom'):
				formatting_hints.append("BORDER_BOTTOM — this paragraph has a bottom border; render as <hr> if empty, or follow with <hr> if it has text")

			# Add list item indicator with type (CRITICAL for bullet/numbered detection)
			if block.get('isListItem'):
				list_level = block.get('listLevel', 0)
				list_type = block.get('listType', 'bullet')
				formatting_hints.append(f"LIST_ITEM(type={list_type}, level={list_level})")
			
			# Add left indent if significant (helps with margin-left decisions)
			left_indent = block.get('leftIndentPt')
			if left_indent and left_indent > 10:
				formatting_hints.append(f"INDENT_LEFT_{int(left_indent)}pt")
			
			# Include formatting information in the output
			formatting_note = f" [FORMATTING: {', '.join(formatting_hints)}]" if formatting_hints else ""
			
			# Handle soft returns (\n within a paragraph = Shift+Enter in Word).
			# Mark the split point so Claude knows to produce TWO separate <div> elements.
			if '\n' in cleaned_text:
				cleaned_text = cleaned_text.replace('\n', ' [SOFT_RETURN: output EACH PART as a SEPARATE <div>] ')
			
			# Transform "RE: Loan Number: {[M594]}" into explicit 3-column table instruction
			re_loan_match = re.match(r'^RE:\s*Loan Number:\s*(\{?\[.*?\]\}?)(.*)$', cleaned_text)
			if re_loan_match:
				loan_var = re_loan_match.group(1).strip()
				cleaned_text = f"[RE_TABLE_ROW_1: RE: | Loan Number: | {loan_var}] — USE 3-COLUMN TABLE: <td width=\"3%\" valign=\"top\">RE:</td><td width=\"20%\" valign=\"top\">Loan Number:</td><td>{loan_var}</td>"
			# Transform "RE: {Compress(...)}" or "Property Address: ..." into 3-column second row
			re_prop_match = re.match(r'^(?:RE:\s*)?(?:Property Address:\s*)?(\{Compress\([^)]+\)\})', cleaned_text)
			if re_prop_match and not re_loan_match:
				prop_var = re_prop_match.group(1).strip()
				cleaned_text = f"[RE_TABLE_ROW_2: (empty) | Property Address: | {prop_var}] — 3-COLUMN TABLE second row: <td width=\"3%\" valign=\"top\"></td><td width=\"20%\" valign=\"top\">Property Address:</td><td>{prop_var}</td>"
			
			para_counter += 1
			formatted.append(f"Paragraph {para_counter}: {cleaned_text[:char_limit]}{formatting_note}")
		elif block.get('type') == 'table':
			rows = block.get('rows', [])
			tbl_borders = block.get('tableBorders')
			tbl_style = block.get('styleName') or ''

			# Describe border style in plain words for the model
			if tbl_borders:
				bkind = tbl_borders.get('kind', '')
				bsides = tbl_borders.get('sides', {})
				if bkind == 'none':
					border_hint = 'TABLE_BORDERS: none (no visible borders)'
				elif bkind == 'box':
					# show outer border detail
					ex = next((v for v in bsides.values() if v and v != 'none'), 'solid')
					border_hint = f'TABLE_BORDERS: box (outer border only, style={ex})'
				elif bkind == 'grid':
					ex = bsides.get('top') or bsides.get('insideH') or 'solid'
					border_hint = f'TABLE_BORDERS: grid (full inside+outside borders, style={ex})'
				elif bkind == 'inner-only':
					ex = bsides.get('insideH') or bsides.get('insideV') or 'solid'
					border_hint = f'TABLE_BORDERS: inner-only (no outer border, inner lines style={ex})'
				else:
					parts = ', '.join(f'{k}={v}' for k, v in bsides.items() if v)
					border_hint = f'TABLE_BORDERS: mixed ({parts})'
			elif tbl_style and tbl_style.lower() not in ('normal', 'table normal', ''):
				border_hint = f'TABLE_BORDERS: inherited from style "{tbl_style}"'
			else:
				border_hint = 'TABLE_BORDERS: none (no explicit borders set)'

			table_text = [border_hint]
			for row_i, row in enumerate(rows):
				cells = row.get('cells', [])
				cell_texts = []
				for c in cells:
					cell_text = ''
					if c.get('runs'):
						cell_text = ''.join([r.get('text', '') for r in c.get('runs', [])])
					elif c.get('content'):
						parts = []
						for para in c['content']:
							para_text = ''.join([r.get('text', '') for r in para.get('runs', [])])
							if para_text.strip():
								parts.append(para_text.strip())
						cell_text = ' '.join(parts)
					# Build cell hint including width, colspan, cell-level border override
					cell_hint = cell_text.strip()[:200] if cell_text.strip() else '(empty)'
					w = c.get('widthPct')
					span = c.get('colSpan')
					vmerge = c.get('vMerge')
					cb = c.get('borders')
					cell_meta = []
					if w:
						cell_meta.append(f'w={w}%')
					if span:
						cell_meta.append(f'colspan={span}')
					if vmerge:
						cell_meta.append(f'vmerge={vmerge}')
					if cb:
						# Only report if it meaningfully overrides
						override = ', '.join(f'{k}={v}' for k, v in cb.items() if v and v != 'none')
						if override:
							cell_meta.append(f'cell-border={{{override}}}')
					if cell_meta:
						cell_hint = f'[{"; ".join(cell_meta)}] {cell_hint}'
					cell_texts.append(cell_hint)
				if cell_texts:
					table_text.append(f'  Row {row_i+1}: ' + ' | '.join(cell_texts))
			if table_text:
				formatted.append(f"Table {idx + 1} ({len(rows)} rows):")
				for line in table_text:
					formatted.append(f"  {line}")
	
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
	
	# Post-process step 0: Pre-convert source variable formats to standard {[...]} format
	# This ensures Claude sees clean, consistent variable syntax rather than mixed formats.
	def normalize_vars(text):
		# <CSPhoneNumber> → {[plsMatrix.CSPhoneNumber]}
		text = re.sub(r'<([A-Z][a-zA-Z]{2,})>', r'{[plsMatrix.\1]}', text)
		# #M594# → {[M594]}, #L001E8# → {[L001]} (strip E-suffixes)
		def hash_to_bracket(m):
			tag = m.group(1)
			# Strip E-suffixes (E6, E8, etc.)
			tag = re.sub(r'E\d+$', '', tag)
			return '{[' + tag + ']}'
		text = re.sub(r'#([A-Z]\d{3}\w{0,3})#', hash_to_bracket, text)
		return text
	formatted = [normalize_vars(line) for line in formatted]

	# Post-process step 1: Merge continuation lines
	# Word sometimes splits a single sentence across multiple paragraphs (soft returns).
	# Detect: a line that ends without terminal punctuation followed by a line that starts lowercase.
	merged = []
	i = 0
	while i < len(formatted):
		line = formatted[i]
		# Extract the text content (after "Paragraph N: ")
		m_para = re.match(r'^(Paragraph \d+:\s*)(.*)', line)
		if m_para:
			prefix = m_para.group(1)
			text = m_para.group(2)
			# Look ahead: merge with next lines that look like continuations
			while i + 1 < len(formatted):
				next_line = formatted[i + 1]
				m_next = re.match(r'^Paragraph \d+:\s*(.*)', next_line)
				if m_next:
					next_text = m_next.group(1)
					# Strip formatting notes for analysis
					text_clean = re.sub(r'\s*\[FORMATTING:.*?\]', '', text).rstrip()
					next_clean = re.sub(r'\s*\[FORMATTING:.*?\]', '', next_text).rstrip()
					# Continuation: current line ends mid-sentence AND next starts lowercase or with a preposition/article
					if (text_clean and not text_clean[-1] in '.!?:,;' and
						next_clean and (next_clean[0].islower() or next_clean.startswith('on ') or next_clean.startswith('of '))):
						# Merge — preserve any formatting notes from the next line
						fmt_notes = re.findall(r'\[FORMATTING:.*?\]', next_line)
						text = text.rstrip() + ' ' + next_text
						i += 1
						continue
				break
			merged.append(prefix + text)
		else:
			merged.append(line)
		i += 1
	formatted = merged

	# Post-process step 2: annotate RE address grouping and mailing address collapse
	# Pre-pass: detect mortgagee clause line indices, loan number line index, and subject heading index
	mortgagee_indices = set()
	loan_number_idx = None
	subject_heading_idx = None
	for idx, line in enumerate(formatted):
		if re.search(r'MortgageeClauseLine', line, re.IGNORECASE):
			mortgagee_indices.add(idx)
		if re.search(r'Loan Number:', line, re.IGNORECASE) and loan_number_idx is None:
			loan_number_idx = idx
	# Subject heading = bold paragraph immediately before the Loan Number line
	if loan_number_idx and loan_number_idx > 0:
		candidate = formatted[loan_number_idx - 1]
		if re.search(r'\[FORMATTING:.*\bBOLD\b', candidate) and 'BOLD_TAGS_ONLY' not in candidate:
			subject_heading_idx = loan_number_idx - 1

	result_lines = []
	mailing_addr_indices = set()
	for i, line in enumerate(formatted):
		# Detect mailing address M-code lines (M558–M566 are borrower mailing address fields)
		if re.search(r'\bM55[89]\b|\bM56[0-6]\b', line):
			mailing_addr_indices.add(i)

	# Detect which address variables exist in the RAW IR blocks (not the filtered list,
	# because M583/M568 may have been filtered as metadata but still need to be in Compress)
	all_block_text = ' '.join(
		''.join(r.get('text', '') for r in b.get('runs', []))
		for b in blocks if b.get('type') == 'paragraph'
	)
	has_m567 = bool(re.search(r'\bM567\b', all_block_text))
	has_m583 = bool(re.search(r'\bM583\b', all_block_text))
	has_m568 = bool(re.search(r'\bM568\b', all_block_text))
	compress_parts = []
	if has_m567: compress_parts.append('{[M567]}')
	if has_m583: compress_parts.append('{[M583]}')
	if has_m568: compress_parts.append('{[M568]}')
	compress_expr = '{Compress(' + '|'.join(compress_parts) + ')}' if len(compress_parts) > 1 else (compress_parts[0] if compress_parts else '{[M567]}')

	# Index of paragraph just before first mortgagee clause (to suppress <br> between them)
	pre_mortgagee_idx = min(mortgagee_indices) - 1 if mortgagee_indices else None

	for i, line in enumerate(formatted):
		if i in mailing_addr_indices:
			first = min(mailing_addr_indices)
			if i == first:
				line += " [NOTE: This and all consecutive M558-M566 lines are the borrower mailing address - output ONLY <div>{[mailingAddress]}</div> here, do NOT output individual M-code divs]"
			else:
				line += " [NOTE: Part of mailing address above - do NOT output as a separate paragraph]"
		# Subject heading before Loan Number table: force correct style
		if i == subject_heading_idx:
			line += ' [NOTE: This is the SUBJECT HEADING — format as: <b><div style="font-size: 11pt">text</div></b> — do NOT add <br> after this before the Loan Number table]'
		# Paragraph immediately before first mortgagee clause: suppress trailing <br>
		if i == pre_mortgagee_idx:
			line += " [NOTE: Mortgagee clause lines follow IMMEDIATELY after this paragraph — do NOT add <br> between this paragraph and the mortgagee lines]"
		# RE/Property Address row: merge address variables into Compress form using ONLY
		# the variables that actually appear in the source document (source-driven).
		if re.search(r'(?:RE:|Property Address:)\s+.*M567', line):
			para_num = re.match(r'Paragraph (\d+):', line)
			num = para_num.group(1) if para_num else '?'
			fmt_match = re.search(r'\[FORMATTING:[^\]]*\]', line)
			fmt_note = f' {fmt_match.group()}' if fmt_match else ''
			# Preserve the ORIGINAL label from the source (e.g. "Property Address:" or "RE:")
			label_match = re.match(r'Paragraph \d+:\s*((?:RE:|Property Address:)\s*)', line)
			original_label = label_match.group(1).strip() if label_match else 'Property Address:'
			line = f"Paragraph {num}: {original_label} {compress_expr}{fmt_note}"
		# Skip M583 standalone lines if M583 was merged into Compress above
		if has_m583 and re.search(r'^Paragraph \d+:\s*(?:\{?\[?M583\]?\}?|#M583#)\s*(?:\[|$)', line):
			continue
		# Skip M568 standalone lines — merged into the Compress expression above
		if re.search(r'^Paragraph \d+:\s*(?:\{?\[?M568\]?\}?|#M568#)\s*(?:\[|$)', line):
			continue
		# Mortgagee clause lines: annotate to prevent Compress wrapping and enforce no leading <br>
		if i in mortgagee_indices:
			if not '[NOTE:' in line:
				first_mortgagee = min(mortgagee_indices)
				if i == first_mortgagee:
					line += " [NOTE: Output as individual <div style=\"text-align: center\">...</div> — do NOT combine with Compress() — do NOT add <br> before this element]"
				else:
					line += " [NOTE: Output as individual <div style=\"text-align: center\">...</div> — do NOT combine with Compress()]"
		result_lines.append(line)
	
	return '\n'.join(result_lines)

def build_prompt(ir, few_shot_examples, user_instruction=None):
	"""Build the complete prompt for Claude API"""
	system_prompt = load_system_prompt()
	
	# Format IR content
	ir_content = format_ir_for_prompt(ir)
	
	# Detect header type from IR blocks — inject explicit directive so Claude doesn't guess
	import re as _re_header
	blocks = ir.get('blocks', [])
	has_h003_conditional = False
	has_h003_address_lines = False  # H002/H003/H004 listed as separate company address line variables
	has_nmls = False
	for b in blocks[:25]:  # Only check first 25 blocks (header area)
		runs = b.get('runs', [])
		text = ''.join(r.get('text', '') for r in runs)
		# Match NMLID (no S) and NMLSID — both are valid NMLS identifier tags
		if _re_header.search(r'NMLS?ID', text, _re_header.IGNORECASE):
			has_nmls = True
			break
		# H003 with explicit conditional/suppress language
		if _re_header.search(r'H003', text) and _re_header.search(r'suppress|IF\s+.*H003|null|hide|conditional', text, _re_header.IGNORECASE):
			has_h003_conditional = True
		# H002/H003/H004 appearing as separate company address line variables
		# (Company Address Line 1/2/3) → these are the individual components of the tag header
		if _re_header.search(r'H00[234]', text) and _re_header.search(r'Company Address Line|Address Line', text, _re_header.IGNORECASE):
			has_h003_address_lines = True
	
	header_texts = ir.get('meta', {}).get('headerTexts', [])
	for ht in header_texts:
		# Match NMLID (no S) and NMLSID — both appear in different document templates
		if _re_header.search(r'NMLS?ID', ht, _re_header.IGNORECASE):
			has_nmls = True
			break
	
	if has_nmls:
		header_directive = "\n[HEADER_DIRECTIVE: Use <div>{Header(NMLSID)}</div> — NMLS detected]\n"
	elif has_h003_conditional or has_h003_address_lines:
		header_directive = "\n[HEADER_DIRECTIVE: Use <div>{Insert(H003 TagHeader)}</div> — H003/company address line variables detected]\n"
	else:
		header_directive = "\n[HEADER_DIRECTIVE: Use <div>{[tagHeader]}</div> — no H003 address lines detected, use default]\n"
	
	# Inject default font directive if detected in document metadata
	default_font = ir.get('meta', {}).get('defaultFont')
	default_font_size_pt = ir.get('meta', {}).get('defaultFontSizePt')
	if default_font and default_font_size_pt:
		font_directive = f"\n[DEFAULT_FONT: {default_font} {default_font_size_pt}pt — emit `&nbsp;{{Font({default_font}|{default_font_size_pt}pt)}}` as the very first line before the header div]\n"
	else:
		font_directive = ""

	ir_content = header_directive + font_directive + ir_content
	
	# Append text box content if present (floating text boxes are not in body flow)
	text_boxes = ir.get('meta', {}).get('textBoxes', [])
	if text_boxes:
		ir_content += "\n\n=== FLOATING TEXT BOXES (appear as bordered boxes in document) ===\n"
		ir_content += "IMPORTANT: These are visually prominent boxes (often with borders) that appear at the top right or elsewhere.\n"
		ir_content += "They typically contain Loan Number, Property Address, or other key reference info.\n"
		ir_content += "Include their content as a table in the appropriate location (usually just before or after the salutation area).\n"
		for i, tb in enumerate(text_boxes):
			ir_content += f"\nText Box {i+1}:\n"
			for row in tb.get('rows', []):
				text = ''.join(r.get('text', '') for r in row.get('runs', []))
				if text.strip():
					ir_content += f"  {text.strip()}\n"
	
	# Build few-shot examples section - show ALL examples with proper formatting
	few_shot_text = "\n## CRITICAL: Example Outputs - Study These Carefully\n\n"
	few_shot_text += "These examples show the EXACT formatting structure you must follow:\n"
	few_shot_text += "- Each element on its own line (with newlines)\n"
	few_shot_text += "- Proper <br> tags for spacing based on source document\n"
	few_shot_text += "- Structure derived from the actual document content (header, date, mailing address, tables, salutation, etc.)\n"
	few_shot_text += "- Conditional logic wrapped in {If()}...{End If}\n"
	few_shot_text += "- Property address variables combined with Compress() when multiple appear together\n\n"
	few_shot_text += "IMPORTANT: Notice how each example has proper newlines - each <div>, <br>, <table> is on its own line!\n\n"
	
	for idx, ex in enumerate(few_shot_examples):  # Show ALL examples
		few_shot_text += f"### Example {idx + 1}: {ex['name']}\n```html\n{ex['html']}\n```\n\n"
	
	# Build user message
	# Note: Using regular string concatenation instead of f-string to avoid issues with {If()} syntax
	user_message = """You are converting a Word document into a formatted HTML template. Your task is to:

1. Extract the actual document content (ignore variable definitions and instructions)
2. Format it as HTML following the EXACT structure and style shown in the examples
3. Use proper newlines - each HTML element on its own line
4. Include ALL elements that are PRESENT in the document — do NOT add elements that aren't there, do NOT omit elements that are
5. Wrap conditional content in {If()}...{End If} blocks
6. Match spacing and formatting from the source document exactly

CRITICAL UNIVERSAL RULES - APPLY TO ALL DOCUMENTS:

0. FORMULAS AND CALCULATIONS - NEVER leave these as empty placeholders:
   
   **FORMULA PATTERNS TO RECOGNIZE:**
   - `[(TAG1 + TAG2/X)*100]%` → Convert to conditional with Math
   - `[TAGE8 + N years]` → Convert to `{DateAdd({[TAG]}|+N|format|Year)}`
   - `<VariableName>` → Convert to `{[plsMatrix.VariableName]}`
   - `X` in formulas → Usually means "lesser of two values" (e.g., M467 and M962)
   
   **CURRENCY/MONEY DISPLAY:**
   - When you see `$[TAG]` or `$` followed by a variable tag → Use `{Money({[TAG]})}`
   - `$[M010]` or `$[M010E4]` → `{Money({[M010]})}`
   - `$[M011]` → `{Money({[M011]})}`
   - The Money() function formats a number as currency with dollar sign
   - Do NOT output literal `$` before a tag - always use `{Money({[TAG]})}` instead
   - For calculated amounts, use `{Math(formula|Money)}` instead
   
   **CALCULATION SYNTAX - CRITICAL RULES:**
   
   **Math Function:**
   - Syntax: `{Math(formula|format)}`
   - Formats: `|Money` for currency, `|Date` for dates
   - For percentages: NO format parameter, just use `{Math(formula)}%`
   - Example: `{Math(({[C001]}+{[M585]}-{[M013]}|Money)}` for currency
   - Example: `{Math((({[M010]}+{[T054]})/{[M467]})*100)}%` for percentage
   - NEVER use `|0` or other numeric formats
   
   **DateAdd Function:**
   - Syntax: `{DateAdd({[TAG]}|amount|format|unit)}`
   - NEVER wrap in {[...]} brackets
   - Examples: `{DateAdd({[L001]}|+14|MM/dd/yyyy|Day)}`, `{DateAdd({[M486]}|+2|MMM yyyy|Year)}`
   
   **Numeric Comparisons:**
   - Use `{Number({[TAG]})}` to convert comma-formatted strings to numbers
   - Example: `{If({Number({[M467]})} < {Number({[M962]})})}`
   - Prevents string comparison issues with values like "100,000"
   
   **Blank/Zero Checks — field type determines the NOT IN list:**

   - **Numeric/money fields** (amounts, balances, percentages — M-prefix variables like M467, M591, T106, Q365, etc.):
     Use `('', '0', '.00', NULL)` — catches numeric zeros stored as strings
     Example: `{If('{[M467]}' IN ('', '0', '.00', NULL))}{[M962]}{Else}...{End If}`

   - **Text/name/contact fields** (SPOC names, addresses, labels — O-prefix variables like O274, O294, O295, O276, O296, etc.):
     Use `('', NULL)` ONLY — never add `'0'` or `'.00'` to text field checks
     Example: `{If('{[O294]}' NOT IN ('', NULL) AND '{[O295]}' NOT IN ('', NULL))}{[O294]}, {[O295]}{Else}{[plsMatrix.SPOCContact]}{End If}`

   **CRITICAL**: O294, O295, O274, O276, O296 are SPOC contact name/text fields.
   NEVER use `'0'` or `'.00'` in their NOT IN checks — only `('', NULL)`.
   
   **CRITICAL: NEVER nest {If()} inside {Math()}!**
   - WRONG: `{Math(formula/{If(condition)}{[TAG1]}{Else}{[TAG2]}{End If}*100)}`
   - RIGHT: `{If(condition)}{Math(formula/{[TAG1]}*100)}{Else}{Math(formula/{[TAG2]}*100)}{End If}`
   - Each conditional branch must have its own complete {Math()} call
   
   **CONDITIONAL PRIORITY RULES:**
   When handling multiple conditions, order by specificity:
   1. Check for invalid/blank values FIRST (blank, zero, null)
   2. Then perform numeric comparisons
   3. Finally, handle the default case
   
   **EXAMPLE: Lesser-of Pattern (commonly used for property values)**
   When document says "X = lesser of TAG1 and TAG2" or "divide by lesser of purchase price/appraisal":
   ```
   {If('{[TAG1]}' IN ('', '0', NULL))}
     {Math(formula/{[TAG2]}*100)}
   {Else If('{[TAG2]}' IN ('', '0', NULL))}
     {Math(formula/{[TAG1]}*100)}
   {Else If({Number({[TAG1]})} < {Number({[TAG2]})})}
     {Math(formula/{[TAG1]}*100)}
   {Else If({Number({[TAG2]})} < {Number({[TAG1]})})}
     {Math(formula/{[TAG2]}*100)}
   {Else}
     {Math(formula/{[TAG2]}*100)}
   {End If}%
   ```
   - Check blanks/zeros first to prevent comparison errors
   - Use {Number()} for all numeric comparisons
   - Each branch has complete {Math()} call, not nested inside conditionals
   
   **PLACEHOLDER VARIABLES:**
   - If you see `<EscrowEmail>`, `<CSPhoneNumber>`, `<CompanyLongName>`, `<HoursOfOperation>` in angle brackets
   - Convert to: `{[plsMatrix.EscrowEmail]}`, `{[plsMatrix.CSPhoneNumber]}`, etc.
   - ONLY underline if the source paragraph has [FORMATTING: UNDERLINE] or [FORMATTING: HYPERLINK(...)]
   
   **INLINE ADDRESS CONDITIONALS:**
   When address variables appear INLINE in a sentence (not stacked), check if any are optional.
   Common pattern: M567 (street) and M568 (city/state/zip) are required, but M583 (unit number) 
   is optional and may be empty. When an optional variable appears between commas, wrap it in a 
   conditional to suppress the extra comma when empty:
   - WRONG: `{[M567]}, {[M583]}, {[M568]}` (leaves ", ," if M583 is empty)
   - RIGHT: `{[M567]}{If('{[M583]}' <> '')}, {[M583]}{End If}, {[M568]}`
   Detection: In the source document, required variables are often in RED and optional ones 
   are in BLACK (or a different color). If a variable in an inline list is a different color 
   from the others, it's likely optional and needs a conditional wrapper.
   
   **Compress() — STACKING LINES WITHOUT GAPS:**
   Compress() takes multiple values separated by `|` and stacks them as lines, 
   suppressing any that are empty. Use it whenever you have consecutive lines that 
   would normally be separate `<div>` elements but need to collapse blank ones.
   
   The pattern: instead of `<div>{[A]}</div><div>{[B]}</div><div>{[C]}</div>`,
   use `{Compress({[A]}|{[B]}|{[C]})}`.
   
   Use Compress() when:
   - 2+ consecutive lines are variable-only (no static text mixed in) and stacked
   - Any of those lines could potentially be empty/blank
   - Common cases: address blocks, mailing info, contact stacks, property addresses
   - Can be ANY number of items — 2, 3, 4, 5+ depending on the document
   
   You can wrap Compress() in a styled div for alignment:
   `<div style="text-align: center">{Compress({[A]}|{[B]}|{[C]})}</div>`
   
   Do NOT use Compress() when:
   - Lines contain a mix of static text and variables (e.g., "Phone number: {[plsMatrix.CSPhoneNumber]}")
   - Lines are intentionally separate with different purposes (e.g., phone on one line, website on another, hours on another)
   - The lines have `<br>` breaks between them in the source — that spacing is intentional
   
   **COMPLETE FUNCTION REFERENCE** (use these when appropriate — do not invent syntax):

   String / Display:
   - `{Upper(value)}` — converts value to UPPERCASE
   - `{Lower(value)}` — converts value to lowercase
   - `{PadLeft(value|width|char)}` — left-pads value: `{PadLeft(123|6|0)}` → 000123
   - `{Replace(source|"old"|"new")}` — replaces all occurrences of old with new in source
   - `{Symbol(value)}` — outputs a symbol wrapped in an HTML label tag

   Numeric / Formatting:
   - `{Number(value|decimals)}` — formats number with rounding: `{Number(1234.567|2)}` → 1234.57; also use for numeric comparisons
   - `{Money(value|abs|neg)}` — formats as currency: `{Money(-123.456)}` → ($123.46)
   - `{IsNumber(value)}` — returns true/false; use in {If()} to check if a value is numeric
   - `{Max(a|b|type|decimals)}` — returns the larger of two values: `{Max(100|250|int)}` → 250
   - `{Min(a|b|type|decimals)}` — returns the smaller of two values
   - `{MinNonZero(a|b|type)}` — returns the smallest non-zero value: `{MinNonZero(0|125|int)}` → 125

   Conditional:
   - `{If(expression)}...{Else If(...)}...{Else}...{End If}` — multi-branch conditional block
   - `{IIf(expr|true_value|false_value)}` — inline conditional: `{IIf(BALANCE>0|Due|Paid)}`
   - `{IsNotEmpty(value|output)}` — displays output only when value is not empty

   Numbering:
   - `{InitAutoNumber(N|start)}` — initializes auto-numbering with a starting value
   - `{AutoNumber(expr)}` — outputs and increments auto number when condition is true

   Layout / Fonts:
   - `{Font(Font|Size)}` — sets default font/size for subsequent content: `{Font(Calibri|11pt)}`
   - `{FixedFont(text|font|size|spaces)}` — displays text in fixed-width font
   - `{MarginBottom(value)}` — sets page bottom margin: `{MarginBottom(3.5in)}`
   - `{PageNumbers(True|False)}` — enables/disables page numbering

   Content Insertion:
   - `{Insert(Template_Description)}` — inserts stored template HTML by description
   - `{InsertReport(ID)}` — embeds another documentation record by ID
   - `{InsertComposition(Title|TypeId)}` — inserts documentation content by title and file type

   Data / Tables:
   - `{SqlLookup(fields|table|where)}...{End SqlLookup}` — executes SQL query; shows content if rows found
   - `{SqlTable(fields|table|where|sort|type)}` — renders SQL query results as a formatted table
   - `{Table(col1~col2|r1~r2)}` — creates a manual HTML table from delimited values

   Address Stacking:
   - `{Compress(a|b|c)}` — combines values with line breaks, suppressing empty lines (use for address stacks)
   - `{CompressPdf(a|b|c)}` — same as Compress but optimized for PDF output

   Regulatory:
   - `{Q189V2({[PMT]}|headers...)}` — generates vertical Reg Z Q189 repayment table
   - `{Q189V3()}` — generates compact two-column Reg Z Q189 repayment table

   **CRITICAL**: NEVER output empty `%` or `[]` - always convert formulas to proper syntax!

1. SYSTEMATIC EXTRACTION - Read the ENTIRE Document Content from start to finish:
   - Extract EVERY paragraph in the exact order it appears
   - Do NOT stop until you've processed all content
   - Count paragraphs and verify you've included all of them

2. IGNORE METADATA - Filter out variable definitions and instructions:
   - Skip: "[H002] Company Address Line 1" - variable definitions
   - Skip: "(or if [H581] present)" - conditional instructions  
   - Skip: "If [M065] ≥ 'July 29, 1999' then print:" - instructions (convert to {If()} instead)
   - Remove parenthesis descriptions like "(Property Line 1)", "(Due Date)", "(Balance)" after variables
   - Keep: "(the Property)" - actual content, not metadata

3. STRUCTURE DETECTION - Scan the document for labeled sections (loan number, property address, RE, etc.):
   - If you see a loan number label (e.g. "Loan Number:", "Re: Loan No:", etc.) with a variable → Create a table row using the EXACT label from the source
   - If you see a property address label (e.g. "RE:", "Property Address:", etc.) with address variables → Create a table row using Compress() with ONLY the address variables present
   - Use the EXACT labels from the document — do NOT rename them
   - Place the table where it appears in the document relative to other content

4. FORMATTING RULES:
   
   **LIST FORMATTING - CRITICAL RULES:**
   - Look for [FORMATTING: LIST_ITEM_LEVEL_X] in Document Content
   - Check the ACTUAL TEXT for list markers:
     * If you see "1.", "2.", "3." → USE NUMBERED FORMAT
     * If you see "•", "-", "*" → USE BULLET FORMAT
   
   **TABLE vs DIV for list items - THIS IS ABOUT SPATIAL ALIGNMENT:**
   
   The choice between TABLE and DIV format depends on how the text wraps in the source document:
   
   **Use TABLE format** when the list item text is INDENTED PAST the number/bullet, meaning
   wrapped lines align with the start of the text, NOT the number. The number acts as its 
   own column and multi-line text stays in its own column:
   ```
   1.  This is the first item and when the text wraps it
       continues aligned here, past the number.
   2.  Second item text stays in its own column too.
   ```
   → Table structure (MUST include <div> wrapper and margin-left):
   <div><table width="100%" style="border-collapse: collapse; margin-left: 30px"><tbody><tr>
     <td width="5%" valign="top">1.</td>
     <td>This is the first item and when the text wraps it continues aligned here, past the number.</td>
   </tr><tr>
     <td width="5%" valign="top">2.</td>
     <td>Second item text stays in its own column too.</td>
   </tr></tbody></table></div>
   
   **Use DIV format** when the list item text WRAPS BACK to the same margin as the number,
   meaning the number and text share the same column and wrapped text goes all the way left:
   ```
   1. This is the first item and when the text wraps it
   continues here, aligned with the number not indented past it.
   2. Second item also wraps back to the left margin.
   ```
   → Div structure (with margin-left):
   <div style="margin-left: 25px">1. This is the first item and when the text wraps it continues here, aligned with the number not indented past it.</div>
   <div style="margin-left: 25px">2. Second item also wraps back to the left margin.</div>
   
   **DETECTION CLUES:**
   - If [FORMATTING: INDENT_X] is present AND text after the number has ADDITIONAL indent → TABLE
   - If [FORMATTING: LIST_ITEM_LEVEL_X] shows indentation matching the number position → TABLE
   - If text wraps inline with the number (same indent level) → DIV
   - When in doubt, check the source document's spatial layout
   
   **BULLET LIST FORMAT (width="3%", border-collapse, margin-left) - when using TABLE:**
   <div><table width="100%" style="border-collapse: collapse; margin-left: 30px"><tbody><tr>
     <td width="3%" valign="top">•</td>
     <td>First item text</td>
   </tr></tbody></table></div>
   CRITICAL: The margin-left and <div> wrapper are MANDATORY for all bullet/numbered list tables.
   
   **CRITICAL**: NEVER change numbered lists (1., 2.) to bullets (•) or vice versa!
   **CRITICAL**: Numbered lists use width="5%", bullet lists use width="3%" when using TABLE format!
   
   **BOLD FORMATTING - CRITICAL RULES:**
   
   Check for [FORMATTING: BOLD] or [FORMATTING: PARTIAL_BOLD(...)] notes:
   
   **[FORMATTING: PARTIAL_BOLD(text here)]** - Only specific parts are bold:
   - The text in parentheses shows WHICH PARTS are bold
   - Example: "PARTIAL_BOLD(Please note that all appraisals)" = only that text is bold
   - Format: <b>Bold part only.</b> Rest of paragraph continues.
   
   **Common patterns:**
   - First sentence only: <div><b>First sentence ends.</b> More text continues here.</div>
   - Mid-paragraph: <div>Regular text <b>bold term</b> more regular text.</div>
   - Bold with underline inside: <div><b>Bold text with <u>underlined part</u> inside.</b></div>
   - Nested in tables: <td>Regular text with <b>Exterior BPO</b> in middle.</td>
   
   **[FORMATTING: BOLD]** - Entire paragraph is bold:
   - Wrap entire text: <div><b>All text is bold here.</b></div>
   
   **CRITICAL**: If you see PARTIAL_BOLD, DO NOT make the entire paragraph bold!
   **CRITICAL**: Check the parentheses content to see exactly which text should be bold!
   
   **BOLD ON VARIABLE TAGS - IMPORTANT:**
   Variable tags (short alphanumeric codes like {[M594]}, {[U121]}, {[M010]}, etc.) are often 
   displayed as bold in the source template. This is how the client MARKS that a tag is present - 
   it does NOT mean the tag should be bold in the output.
   - [FORMATTING: BOLD_TAGS_ONLY] means bold is ONLY on variable tags → Do NOT bold anything
   - [FORMATTING: PARTIAL_BOLD] where the bold parts are ONLY tags → Do NOT bold anything
   - If a paragraph's ONLY bold content is a variable tag → Do NOT bold it
   - If a label like "Your new loan number:" is followed by a bold tag → The LABEL may or may not 
     be bold (check the label text itself), but the TAG should NOT be bold
   - Only bold a variable tag if the surrounding sentence/phrase is genuinely bold text
   - Example: "Your new loan number: {[M594]}" → Neither bold: `<td>{[M594]}</td>`
   - Example: "Your Principal Balance is currently: $[M010E4]" → NOT bold even if tag is bold:
     `<div>Your Principal Balance is currently: {Money({[M010]})}</div>`
   - Example: "an Exterior BPO must be completed" → The words "Exterior BPO" ARE genuinely bold:
     `an <b>Exterior BPO</b> must be completed`
   - Rule of thumb: If the PARTIAL_BOLD text looks like a tag code (M594, M010, U121, etc.), 
     it's not real bold. If it looks like English words, it IS real bold.
   
   **HYPERLINK/LINK VARIABLES:**
   When the source document contains hyperlinked text (URLs, email addresses, clickable text), 
   these are variables that should be converted to plsMatrix format:
   - Hyperlinked website text → `{[plsMatrix.WebSite]}`
   - Hyperlinked email text → `{[plsMatrix.CSEmail]}` or `{[plsMatrix.EscrowEmail]}`
   - The fact that text is a hyperlink in Word means it's a dynamic variable, NOT a static URL
   - ONLY underline if the source paragraph has [FORMATTING: UNDERLINE] or [FORMATTING: HYPERLINK(...)]
   - Do NOT automatically underline phone numbers, fax numbers, or email variables
   - If the hyperlink text looks like a URL (http://..., www...) → Convert to plsMatrix variable
   
   **VARIABLES - plsMatrix PLACEHOLDERS:**
   - If you see <VariableName> in angle brackets (e.g., <EscrowEmail>, <CSPhoneNumber>), convert to {[plsMatrix.VariableName]}
   - Common plsMatrix variables: EscrowEmail, CSPhoneNumber, CompanyLongName, HoursOfOperation, SPOCContactPhone
   
   **OTHER FORMATTING:**
   - Underlined text → <u>text</u> ONLY when [FORMATTING: UNDERLINE] is present in the source
   - Do NOT automatically underline phone numbers, fax numbers, emails, or URLs unless the source explicitly marks them as underlined
   - Each HTML element on its own line

5. COMPLETE EXTRACTION - Include ALL content after main body:
   - Include "Sincerely," line
   - Include ALL company information (name, address, phone)
   - Include ALL legal notices and disclaimers at the end
   - Include ALL-CAPS text (these are important legal notices)
   - Do NOT stop early - process until no more content remains

Document Content:
""" + ir_content + """

"""
	
	if user_instruction:
		user_message += f"Additional Instruction: {user_instruction}\n\n"
	
	user_message += """CRITICAL: You MUST format the HTML with proper newlines. Each HTML element MUST be on its own line.

**BEFORE YOU START - MANDATORY PRE-SCAN:**
Read the ENTIRE Document Content once before generating ANY HTML. Answer these questions:
1. Is there a "Loan Number:" or "Re: Loan Number:" label? → Note the EXACT label text. Check for metadata instructions like "LAST 4 DIGITS" → determines variable ({[M594]} vs {[loanNumberLast4]})
2. Is there a "RE:" or "Property Address:" label? → YES = create table row with Compress() using ONLY the address variables present in the document (M567, M583, M568 — include only those that appear)
3. Check the [HEADER_DIRECTIVE] at the top of Document Content — it tells you EXACTLY which header to use. OBEY IT. Three cases:
   - [HEADER_DIRECTIVE: ... NMLS detected] → Use <div>{Header(NMLSID)}</div>
   - [HEADER_DIRECTIVE: ... H003/company address line variables detected] → Use <div>{Insert(H003 TagHeader)}</div>
   - [HEADER_DIRECTIVE: ... use default] → Use <div>{[tagHeader]}</div>
4. Where does "Sincerely," appear? → Note the paragraph number
5. What comes AFTER "Sincerely,"? → List all remaining content
6. How many total paragraphs are there? → You MUST extract this many
7. CRITICAL: Read EVERY label, tag, and instruction EXACTLY as written in the source — do not substitute, assume, or generalize

**COMMON ERRORS TO AVOID (especially in MI001-type PMI documents):**

❌ **WRONG**: Leaving formulas as empty placeholders
   - Bad: `Currently, your Loan to Value is at %.`
   - Good: `Currently, your Loan to Value is at {Math((({[M010]}+{[T054]})/{[M467]})*100)}%.`
   - Note: Use {Math()} for calculations, NO format parameter for percentages

❌ **WRONG**: Nesting {If()} inside {Math()}
   - Bad: `{Math(formula/{If(cond)}{[TAG1]}{Else}{[TAG2]}{End If}*100)}`
   - Good: `{If(cond)}{Math(formula/{[TAG1]}*100)}{Else}{Math(formula/{[TAG2]}*100)}{End If}`
   - Rule: Conditionals OUTSIDE, each branch has complete {Math()} call

❌ **WRONG**: Not using {Number()} for numeric comparisons
   - Bad: `{If({[M467]} < {[M962]})}`  (string comparison with commas)
   - Good: `{If({Number({[M467]})} < {Number({[M962]})})}` (numeric comparison)

❌ **WRONG**: Leaving dates as empty brackets
   - Bad: `Following your [] payment`
   - Good: `Following your {DateAdd({[M486]}|+2|MMM yyyy|Year)} payment`
   - Note: {DateAdd()} is NOT wrapped in {[...]} brackets

❌ **WRONG**: Wrapping DateAdd in extra brackets
   - Bad: `{[DateAdd({[M486]}|+2|MMM yyyy|Year)]}`
   - Good: `{DateAdd({[M486]}|+2|MMM yyyy|Year)}`

❌ **WRONG**: Using bullets when document has numbered lists
   - Bad: `<td width="3%" valign="top">•</td>` (for items labeled 1., 2.)
   - Good: `<td width="5%" valign="top">1.</td>` (for first item), `<td width="5%" valign="top">2.</td>` (for second)

❌ **WRONG**: Over-bolding entire paragraphs when only part is bold
   - Bad: `<div><b>Please note that all appraisals must be ordered through our offices and are at the expense of the property owner. Due to your loan's investor...</b></div>`
   - Good: `<div><b>Please note that all appraisals must be ordered through our offices and are at the expense of the property owner.</b> Due to your loan's investor...</div>`

❌ **WRONG**: Underlining phone/email/fax when source does NOT show underline
   - Bad: `<u>{[plsMatrix.CSPhoneNumber]}</u>` or `<u>{[plsMatrix.TaxEmail]}</u>` (added underline not in source)
   - Good: `{[plsMatrix.CSPhoneNumber]}` (no underline unless source explicitly has [FORMATTING: UNDERLINE])
   - Rule: ONLY underline if the source paragraph explicitly has underline formatting — do NOT assume phone numbers/emails/fax should be underlined
   - CRITICAL: Email hyperlinks in Word show as underlined because they're hyperlinks. The [FORMATTING: HYPERLINK(...)] or [FORMATTING: UNDERLINE] hint from an email/URL does NOT mean you should output `<u>` — it just means Word displayed it as a link. Leave email/phone/fax plsMatrix variables plain (no tags) unless the IR shows BOTH [FORMATTING: UNDERLINE] AND [FORMATTING: ITALIC] together.

❌ **WRONG**: Guessing spacing around Sincerely instead of reading the source
   - Rule: The `<br>` tags around "Sincerely," are determined by ACTUAL blank lines in the source document
   - Count the blank lines before and after "Sincerely," in the source — each blank line = one `<br>`
   - Do NOT assume a fixed pattern — read the spacing from the document

❌ **WRONG**: Adding M583 to Compress() when it's not in the source document
   - Bad: `{Compress({[M567]}|{[M583]}|{[M568]})}` when the source only has M567 and M568
   - Good: `{Compress({[M567]}|{[M568]})}` — include ONLY the variables present in the source
   - Rule: NEVER default to 3-part Compress. Scan the IR for which address variables actually appear.

❌ **WRONG**: Using "RE:" as the second row label when the source says "Property Address:"
   - Bad: `<td>RE:</td>` for the property address row when source says "Property Address:"
   - Good: `<td>Property Address:</td>` — copy the EXACT label from the source document
   - Rule: The second row label in an RE table is NOT always "RE:" — read the source.

❌ **WRONG**: Not detecting aligned label-value groups as tables
   - Bad: Multiple consecutive `<div>Label: value</div>` with same indentation
   - Good: When 3+ consecutive paragraphs share SAME indent AND have ":" → Table format
   - Example: "Your new loan number:", "New toll-free line:", "New website..." should be ONE table
   - Rule: Check [FORMATTING: INDENT_X] to detect spatial alignment, then group into table

❌ **WRONG**: Bolding variable tags just because they appear bold in source
   - Bad: `<div><b>Your new loan number:</b> <b>{[M594]}</b></div>` (tags bold because client marks them)
   - Good: `<div>Your new loan number:</div>` with `{[M594]}` not bold
   - Rule: Bold on short tags like {[M594]} is just the client marking a tag, NOT actual bold formatting

❌ **WRONG**: Treating hyperlinked text as static content
   - Bad: `<div>New website: <u>www.example.com</u></div>`
   - Good: `<div>New website: <u>{[plsMatrix.WebSite]}</u></div>`
   - Rule: Hyperlinks in source are dynamic variables → convert to plsMatrix format

❌ **WRONG**: Applying italic/underline to email/phone/fax variables that are just linked, not formatted
   - Bad: `<u><i>{[plsMatrix.TaxEmail]}</i></u>` or `<i>{[plsMatrix.TaxEmail]}</i>` or `<u>{[plsMatrix.TaxEmail]}</u>`
   - Good: `{[plsMatrix.TaxEmail]}` — plain by default
   - Rule: Hyperlinks on email addresses appear underlined in Word because they are hyperlinks, NOT because of italic/underline formatting applied to the run. **NEVER apply `<u>` alone to `{[plsMatrix.TaxEmail]}`, `{[plsMatrix.TaxFax]}`, `{[plsMatrix.CSPhoneNumber]}`, or any plsMatrix contact variable.** ONLY apply `<u><i>` when the IR explicitly shows BOTH the UNDERLINE AND ITALIC hints TOGETHER in the same formatting note. Email at the END of a paragraph (e.g., "or email {[plsMatrix.TaxEmail]}") is NEVER underlined.

❌ **WRONG**: Outputting a company/servicer name as literal text when it appears in the document body
   - Bad: `<div>I understand that by canceling my escrow account, Triad Financial Services will no longer...</div>`
   - Good: `<div>I understand that by canceling my escrow account, {[plsMatrix.CompanyLongName]} will no longer...</div>`
   - Rule: When you see the servicer/company name (like "Triad Financial Services", "NewCourse", or any company name that matches the document producer) used in body text paragraphs, replace it with `{[plsMatrix.CompanyLongName]}`. Company names in document body are ALWAYS dynamic variables.

❌ **WRONG**: Wrapping comma-separated address lines in {Compress()} when the source shows them inline
   - Bad: `<div style="text-align: center">{Compress({[plsMatrix.CompanyReturnAddr1]}|{[plsMatrix.CompanyReturnAddr2]}|{[plsMatrix.CompanyReturnAddr3]})}</div>`
   - Good: `<div style="text-align: center">{[plsMatrix.CompanyReturnAddr1]}, {[plsMatrix.CompanyReturnAddr2]}, {[plsMatrix.CompanyReturnAddr3]}</div>`
   - Rule: When the document shows company return address components (CompanyReturnAddr1/2/3) as a SINGLE LINE with commas between them, output them comma-separated inline. Only use {Compress()} for stacked address blocks (one per line). The signal: if the source document has all three on one line separated by commas → inline; if they're on separate lines → {Compress()}

❌ **WRONG**: Not closing the outer centered div after the title box
   - Bad: `<div style="text-align: center"><div style="display: inline-block; ...">Title</div>` ← missing closing </div>
   - Good: `<div style="text-align: center"><div style="display: inline-block; ...">Title</div></div>`
   - Rule: The CENTERED TITLE BOX pattern uses TWO nested divs. BOTH must be closed. The pattern is: `<div style="text-align: center"><div style="display: inline-block; ...">CONTENT</div></div>` — exactly TWO closing `</div>` tags at the end, on the SAME line.

❌ **WRONG**: HTML-encoding `&nbsp;` as `&amp;nbsp;` in Font() declarations
   - Bad: `&amp;nbsp;{Font(Arial|9.5pt)}`
   - Good: `&nbsp;{Font(Arial|9.5pt)}`
   - Rule: The `&nbsp;` before `{Font()}` is a literal HTML non-breaking space entity — output it as `&nbsp;` exactly, NOT as `&amp;nbsp;`

❌ **WRONG**: Using CSS `double` border or `6px double` for warning boxes with red borders
   - Bad: `<div style="border: 6px double red; ...">...</div>`
   - Good: Nested table — outer table 1px red border, inner td 3px red border (creates visual double-border):
     `<table style="border: 1px solid rgba(255,0,0,1); padding: 0; width: 80%; margin: 0"><tbody><tr><td style="border: 3px solid rgba(255,0,0,1); padding: 8px; ...">...</td></tr></tbody></table>`
   - Rule: When IR shows `[TABLE_BORDERS: red]` or `borderColor: red` on a warning box, use the nested table pattern

❌ **WRONG**: Using `{If(...)}` conditional for co-borrower names when {Compress()} is available
   - Bad: `{If('{[M559]}' NOT IN ('', NULL))}<div>{[M559]}</div>{End If}`
   - Good: `{Compress({[M558]}|{[M559]})}` — Compress already suppresses empty lines
   - Rule: When listing borrower names (M558/M559), use Compress() to handle optional co-borrower, not {If()}

❌ **WRONG**: Skipping colored or highlighted text
   - Bad: Missing conditional sections, missing tags, missing paragraphs
   - Good: ALL content from the document is included regardless of text color
   - Rule: Color/highlighting in source is NOT markup to exclude - it's real content

❌ **WRONG**: Using literal `$` before a variable tag for currency
   - Bad: `<div>Your Principal Balance is currently: ${[M010]}</div>`
   - Good: `<div>Your Principal Balance is currently: {Money({[M010]})}</div>`
   - Rule: `$` + tag → `{Money({[TAG]})}` function, NEVER literal dollar sign before a tag

❌ **WRONG**: Ignoring metadata instructions like "LAST 4 DIGITS" or "PRINT LAST 4"
   - Bad: Using `{[M594]}` when the source says *PRINT LAST 4 DIGITS OF LOAN NUMBER*
   - Good: Using `{[loanNumberLast4]}` when any "last 4" instruction appears near the loan number
   - Rule: Read ALL asterisked (*...*) metadata instructions — they contain critical variable selection info

❌ **WRONG**: Not reading the EXACT label from the source document
   - Bad: Using "Loan Number:" when the source says "Re: Loan Number:"
   - Good: Copying the label text EXACTLY as it appears in the source
   - Rule: Labels in Loan Number/RE tables must match the source document verbatim

❌ **WRONG**: Using {[tagHeader]} when the source document has H002/H003/H004 company address line variables
   - Bad: `{[tagHeader]}` when the source document lists `{[H002]} (Company Address Line 1)`, `{[H003]} (Company Address Line 2)`, `{[H004]} (Company Address Line 3)` separately
   - Good: `{Insert(H003 TagHeader)}` — use this when the source has H002/H003/H004 as separate address line variables, OR when H003 has conditional suppression logic
   - Rule: Check the [HEADER_DIRECTIVE] at the top of Document Content — it tells you exactly which header to use based on IR analysis

**FONT DECLARATION — when IR metadata shows a document-level font/size:**
When the document IR contains a `defaultFont` or the first paragraph style specifies a default font (e.g. `Arial 9.5pt`), emit it as the very first line of the template, before the header div:
```html
&nbsp;{Font(Arial|9.5pt)}
<div>{Insert(H003 TagHeader)}</div>
```
The `{Font(Font|Size)}` directive sets the base font for the entire document. If you see an IR metadata note `[DEFAULT_FONT: Arial 9.5pt]` or similar, always output `&nbsp;{Font(Arial|9.5pt)}` (or the detected font/size) on the first line.

**HORIZONTAL RULE DIVIDER — after mailing address:**
When the document has a thin horizontal line separating the mailing address from the body (often a paragraph with bottom border in the DOCX), output it as `<hr>` instead of `<br>` tags:
```html
<div>{[mailingAddress]}</div>
<hr>
<div style="text-align: center">...
```
Detection: If the IR contains `[FORMATTING: BORDER_BOTTOM]` on a paragraph between the mailing address and the document title/body, or a paragraph that is blank with only a bottom border → render as `<hr>`.

**CENTERED TITLE BOX with {Compress()} for multi-line titles:**
When a document has a large centered title in a bordered box where the title spans two lines (e.g. "Escrow Cancellation / Request"), use `{Compress()}` to split it across lines inside the box — do NOT use `font-weight: bold` unless the document explicitly shows bold:
```html
<div style="text-align: center"><div style="display: inline-block; border: 2pt solid rgba(0,0,0,1); padding: 10px; font-size: 18pt; min-width: 246pt; text-align: center">{Compress(Escrow Cancellation|Request)}</div></div>
```
- The outer centered div ensures the box is centered on the page
- `min-width: 246pt` sets minimum box width (match the source document's text box width)
- Use `{Compress(...)}` when the title has a line break (pipe `|` separating each line)

**ACCOUNT + BORROWER NAME TABLE — form-style documents:**
When a document has "Account Number:" and "Borrower Name(s):" as labeled fields (not in a paragraph, but in a form structure), render them as a compact table, and use `{Compress()}` for the borrower name to handle co-borrower on same field:
```html
<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="20%" colspan="2">Account Number: {[M594]}</td>
  <td></td>
</tr><tr>
  <td width="16%" valign="top">Borrower Name(s): </td>
  <td>{Compress({[M558]}|{[M559]})}</td>
</tr></tbody></table></div>
```
Use `{Compress({[M558]}|{[M559]})}` — NOT a conditional `{If(...)}` block — because `{Compress()}` already suppresses empty lines.

**SIGNATURE TABLE DIMENSIONS — form-style letters (escrow, cancellation, request forms):**
For signature tables on FORM documents (not affidavits), use 80% table width with a 40% signature column, 1% spacer, and 20% date column:
```html
<table width="80%" style="border-collapse: collapse"><tbody><tr>
  <td width="40%" style="border-top: 0.85pt solid rgba(0,0,0,1); padding: 2px 8px 4px; font-size: 8pt">Borrower Signature</td>
  <td width="1%"></td>
  <td width="20%" style="border-top: 0.85pt solid rgba(0,0,0,1); padding: 2px 8px 4px; font-size: 8pt">Date</td>
</tr></tbody></table>
```
This is different from affidavit documents (CL028 style) which use 100% width with 50/50 columns.

**ADDRESS SECTION TABLE — label + writing line pairs:**
When the document has fill-in lines for "City/State/Zip:" and "Contact Phone:" (or similar label+line fields), use a table where the label is in one cell and the writing line is the next cell with `border-bottom`:
```html
<table width="80%" style="border-collapse: collapse"><tbody><tr>
  <td colspan="2">Once cancelled, please send escrow overage (if applicable) to the following address:</td>
  <td></td>
</tr><tr>
  <td colspan="2" style="padding: 6px 0"></td>
</tr><tr>
  <td style="width: 20%">City/State/Zip:</td>
  <td style="width: 60%; border-bottom: 0.85pt solid rgba(0,0,0,1)"></td>
</tr><tr>
  <td colspan="2" style="padding: 6px 0"></td>
</tr><tr>
  <td style="width: 20%">Contact Phone:</td>
  <td style="width: 60%; border-bottom: 0.85pt solid rgba(0,0,0,1)"></td>
</tr></tbody></table>
```
Use `padding: 6px 0` rows as spacers between label-line pairs. Do NOT use `<div>Label: <span style="...">` inline span — use the table format.

**DOUBLE-BORDER WARNING BOX — using nested table (NOT CSS `double`):**
When the source DOCX has a red double-line border box (VML `thinThick` or `thickThin` line style, red stroke), the correct HTML is a nested table: outer table with thin border, inner `<td>` with thick border, both red. This creates the visual double-border effect:
```html
<table style="border: 1px solid rgba(255,0,0,1); padding: 0; width: 80%; margin: 0"><tbody><tr>
  <td style="border: 3px solid rgba(255,0,0,1); padding: 8px; font-size: 9.5pt; font-weight: bold; text-align: center">If you do not return this signed &amp; dated form we are required to collect monthly escrow payments and your monthly payment will increase to cover any escrow shortages.</td>
</tr></tbody></table>
```
Detection cues: IR shows `[FORMATTING: BORDER_COLOR_RED]` or `[TABLE_BORDERS: red]` or `borderColor: red` on a text box or paragraph. Do NOT use `border: 6px double red` CSS — use the nested table pattern instead.

**SPECIAL HEADER LAYOUT — "IMPORTANT NOTICE" documents (affidavits, legal notices):**
When the source document has a large bold "IMPORTANT NOTICE" or similar title in the upper right alongside the company header, use a two-column header table instead of a plain tagHeader div:
```html
<table width="100%"><tbody><tr>
  <td width="60%">{Insert(H003 TagHeader)}</td>
  <td width="40%" style="font-size: 16pt; font-weight: bold; text-align: center; font-family: Arial Black; vertical-align: middle">IMPORTANT<br>NOTICE</td>
</tr></tbody></table>
```
This applies to: CL028 (Illinois Affidavit of Defense) and similar legal affidavit/notice documents.

**BORDERED LENDER/CONSUMER TABLE — affidavit documents:**
When the document has a side-by-side "Lender Name and Address | Consumer Name and Address" info block, wrap the table in a border div:
```html
<div style="border: 2px solid rgba(0,0,0,1)">
  <table width="100%" style="border-collapse: collapse"><tbody>
    <tr>
      <td width="50%" valign="top" style="border: 1px solid rgba(0,0,0,1); padding: 6px 8px; text-align: center; font-weight: bold">Lender (Lienholder) Name and Address</td>
      <td width="50%" valign="top" style="border: 1px solid rgba(0,0,0,1); padding: 6px 8px; text-align: center; font-weight: bold">Consumer Name and Address</td>
    </tr>
    <tr>
      <td width="50%" valign="top" style="border: 1px solid rgba(0,0,0,1); padding: 6px 8px">{Compress({[H131]}|{[H132]}|{[H133]}|{[H134]}|{[H135]})}</td>
      <td width="50%" valign="top" style="border: 1px solid rgba(0,0,0,1); padding: 6px 8px">{Compress({[M558]}|{[M567]}|{[M568]}|Loan Number: {[M594]})}</td>
    </tr>
  </tbody></table>
</div>
```
Do NOT use O294/O295/O296/O297 etc. for this table — those are SPOC variables, not borrower address variables.

**WRITING LINES (defense/response lines) — use border-bottom divs, NOT tables:**
When the source document has blank horizontal lines for the reader to write on:
```html
<div style="border-bottom: 1px solid rgba(0,0,0,1); padding-top: 22px; margin-bottom: 4px"></div>
```
Repeat once per line needed. Do NOT use a table with &nbsp; cells — that creates invisible blank space, not visible lines.

**SIGNATURE TABLES — two separate tables for two signatories:**
```html
<table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="50%" style="border-top: 1px solid rgba(0,0,0,1); padding-top: 2px; font-size: 8pt">Consumer's Name</td>
  <td width="50%" style="border-top: 1px solid rgba(0,0,0,1); padding-top: 2px; font-size: 8pt">Date Signed</td>
</tr></tbody></table>
<br>
<table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="50%" style="border-top: 1px solid rgba(0,0,0,1); padding-top: 2px; font-size: 8pt">Consumer's Name</td>
  <td width="50%" style="border-top: 1px solid rgba(0,0,0,1); padding-top: 2px; font-size: 8pt">Date Signed</td>
</tr></tbody></table>
```
Do NOT use a 3-column layout with a blank middle spacer column.

Generate the HTML template following these EXACT rules:

STEP 0 - SYSTEMATIC CONTENT SCAN (DO THIS FIRST):
   - Read through ALL paragraphs in Document Content from beginning to end
   - Make a mental map: Where is "Loan Number:"? Where is "RE:"? Where is "Sincerely,"?
   - Identify ALL sections: header area, body paragraphs, signature area, legal notices
   - Count total paragraphs so you know when you're done
   - **CHECK FOR FLOATING TEXT BOXES**: Look for the "=== FLOATING TEXT BOXES ===" section at the bottom of Document Content.
     If present, these are bordered boxes (often upper right) containing Loan Number, Property Address, etc.
     ALWAYS convert these to a table in the header area (after mailing address, before salutation).
     Even if the body paragraphs don't mention "Loan Number:", if a text box has it — include the table.
   - Look for CONDITIONAL SECTIONS: Text like "(IF TAG = value then insert the below):" 
     indicates conditional content. Convert these to {If()} blocks in the output.
     Example: "(IF M007 IBM State Code = "19" then insert the below):" → {If('{[M007]}' = '19')}
   - ALL content must be included regardless of color or highlighting in the source document
   - Colored or highlighted text is NOT markup to be excluded - it's real content

STEP 1 - EXTRACT STRUCTURE ELEMENTS (BEFORE SALUTATION):
   - Look for "Loan Number:" text → If found, create table row
   - Look for "RE:" or "Property Address:" text → If found, create table row
   
   - **LABEL-VALUE TABLE DETECTION** - Detect groups of aligned label-value pairs:
     When you see multiple consecutive paragraphs that:
     1. ALL have the SAME [FORMATTING: INDENT_X] value (spatially aligned)
     2. Follow "Label:" or "Label: value" pattern
     3. Form a logical group (e.g., "Your new loan number:", "New toll-free line:", "New website for account access:")
     
     **Format these as a table:**
     ```
     <table width="100%"><tbody><tr>
       <td width="20%" valign="top">Your new loan number:</td>
       <td>{[M594]} Loan Number – No Dash</td>
     </tr><tr>
       <td width="20%" valign="top">New toll-free line:</td>
       <td><u>{[plsMatrix.CSPhoneNumber]}</u></td>
     </tr><tr>
       <td width="20%" valign="top">New website for account access:</td>
       <td><u>{[WebSite]}</u>
       <div><b>Important note: user IDs must be re-created at the new site</b></div></td>
     </tr><tr>
       <td width="20%" valign="top">New Payment Address:</td>
       <td>{[plsMatrix.CompanyLongName]}
       <div>{[plsMatrix.LockBoxAddr1]}</div>
       <div>{[plsMatrix.LockBoxAddr2]}</div></td>
     </tr><tr>
       <td width="20%" valign="top">New email address:</td>
       <td><u>{[plsMatrix.CSEmail]}</u></td>
     </tr></tbody></table>
     ```
     
     **DETECTION RULES:**
     - Check [FORMATTING: INDENT_X] for each paragraph
     - If 3+ consecutive paragraphs have SAME indent AND contain ":" or end with ":" → Table format
     - If a paragraph immediately follows with DIFFERENT indent or no ":", it's NOT part of the table
     - Lines that follow immediately after the label (with MORE indent) go in the SAME table cell as nested <div>
     - Use valign="top" for all cells to align content at top
     - Keep the label's trailing colon ":" in the table cell
     
     **Handling multi-line values in table cells:**
     ```
     Example: "New Payment Address:" followed by company name and 2 address lines
     <tr>
       <td width="20%" valign="top">New Payment Address:</td>
       <td>{[plsMatrix.CompanyLongName]}
       <div>{[plsMatrix.LockBoxAddr1]}</div>
       <div>{[plsMatrix.LockBoxAddr2]}</div></td>
     </tr>
     ```
     
     **Handling inline bolded notes within a value:**
     ```
     Example: "New website for account access:" followed by URL and bolded note
     <tr>
       <td width="20%" valign="top">New website for account access:</td>
       <td><u>{[WebSite]}</u>
       <div><b>Important note: user IDs must be re-created at the new site</b></div></td>
     </tr>
     ```
     
     **When NOT to use table:**
     - Single "Label: value" paragraphs → Use regular <div>
     - Labels with different indentation → Use regular <div> with style="margin-left"
     - Non-label content (no colon) → Use regular <div>
   
   - TABLE FORMAT DETECTION - Based on indentation/alignment:
     
     **DETECTION RULE**: Check [FORMATTING: INDENT_X] notes to determine if "RE:" hangs left
     
     **Pattern A (2-column)**: When labels are ALIGNED (same indentation)
     ```
     Document Content shows both at same indent level:
     Loan Number:    {[M594]}     [no INDENT note]
     RE:             {Compress...} [no INDENT note]
     ```
     Format as 2-column table (Compress vars MUST match source — include M583 ONLY if source has it):
     <table width="100%"><tbody><tr>
       <td width="20%" valign="top">Loan Number:</td>
       <td>{[M594]}</td>
     </tr><tr>
       <td width="20%" valign="top">RE:</td>
       <td>{Compress({[M567]}|{[M568]})}</td>  ← add M583 ONLY if it appears in the source
     </tr></tbody></table>
     
     **Pattern B (3-column)**: When "RE:" hangs left (different indentation)
     ```
     Document Content shows:
     RE: Loan Number:       {[M594]}     [no INDENT note]
            Property Address:  {Compress...} [INDENT_7spaces]
     
     The paragraph with "RE:" has NO indent, but "Property Address:" HAS indent
     ```
     Format as 3-column table (split "RE:" from "Loan Number:") — Compress vars MUST match source:
     <table width="100%"><tbody><tr>
       <td width="3%" valign="top">RE:</td>
       <td width="20%" valign="top">Loan Number:</td>
       <td>{[M594]}</td>
     </tr><tr>
       <td width="3%" valign="top"></td>
       <td width="20%" valign="top">Property Address:</td>
       <td>{Compress({[M567]}|{[M568]})}</td>  ← add M583 ONLY if it appears in the source
     </tr></tbody></table>
     
     **CRITICAL DETECTION**: 
     - Check if paragraph containing "RE:" or starting with "RE:" has [FORMATTING: INDENT_X]
     - Check if next paragraph with "Property Address:" has [FORMATTING: INDENT_X]
     - If "RE:" line has NO indent AND "Property Address:" line HAS indent → Pattern B (3-column)
     - If both have same indentation → Pattern A (2-column)
     
     **DEFAULT**: If no INDENT notes or unclear, use Pattern A (2-column)
   
   - This table goes AFTER mailing address, BEFORE "Dear {[Salutation]},"

STEP 2 - EXTRACT BODY CONTENT:
   - Extract EVERY paragraph after salutation
   - Preserve order exactly as shown in Document Content
   - Format paragraphs with [FORMATTING: LIST_ITEM_LEVEL_X] as bullet point tables (with div wrapper)
   - Apply formatting (bold, underline) based on [FORMATTING: ...] notes
   - Continue until you reach "Sincerely,"

STEP 3 - EXTRACT CLOSING SECTION (AFTER "SINCERELY,"):
   - Include "Sincerely," line
   - Extract ALL remaining paragraphs/variables:
     * Company name: {[plsMatrix.CompanyLongName]}
     * Company addresses: {[plsMatrix.CompanyReturnAddr1]}, {[plsMatrix.CompanyReturnAddr2]}
     * Phone numbers: {[plsMatrix.SPOCContactPhone]} or {[plsMatrix.CSPhoneNumber]}
     * Department names if present
   - Include ALL legal notices (often ALL-CAPS text)
   - Include ALL final paragraphs - nothing should be skipped

STEP 4 - VERIFY COMPLETENESS:
   - Count paragraphs you extracted vs. Document Content
   - If Document Content has 20 paragraphs, your output should have all 20
   - Check that you included content from the END of the document
   - Confirm no sections were skipped

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

4. SALUTATIONS: If the source document has a "Dear" line with a placeholder or generic name (e.g. "Dear Borrower(s),"), convert it to <div>Dear {[Salutation]},</div>. If the document uses a different greeting format, match what the document shows.

5. MAILING ADDRESS: When the document has consecutive individual address-line variables (e.g. M558, M559, M560, etc.), these represent the borrower mailing address — collapse them into a SINGLE <div>{[mailingAddress]}</div>. The IR annotations will tell you which lines to collapse.

6. ANGLE-BRACKET TAGS: When the source has tags like <SeeReverse>, <CompanyLongName>, <CSPhoneNumber>, etc., convert them to {[plsMatrix.TagName]} format (e.g. <SeeReverse> → {[plsMatrix.SeeReverse]}, <CSPhoneNumber> → {[plsMatrix.CSPhoneNumber]}). Match the exact tag name from the source.

7. LABELS: Copy the EXACT label text from the source document — do NOT rename or normalize any labels.
   If the source says "Re: Loan No:" keep it as "Re: Loan No:". If it says "Loan Number:" keep that.
   If the source says "Property Address:" keep that. If it says "RE:" keep that.
   This applies to ALL labels in the document, not just the RE/Loan Number table.

8. PROPERTY ADDRESS COMPRESS: When a property address section has multiple address-line variables, combine them into a single Compress() call with ONLY the variables that actually appear in the document. Follow the IR annotations — they tell you exactly which variables to include and the correct Compress() expression. Do NOT add variables that aren't present in the source.

9. LANGUAGE SERVICES / TRANSLATION BLOCKS: When the document has consecutive centered paragraphs that form a multi-language notice (e.g. English + Spanish translation text), wrap ALL of them in a SINGLE {Compress()} inside one centered div. Preserve the exact text and variables from each line, separated by | in the Compress(). Do NOT output them as separate divs.

10. ALIGNMENT: Apply ALL [FORMATTING: ALIGN_*] hints from the Document Content. If a paragraph has [FORMATTING: ALIGN_RIGHT], output it with style="text-align:right". If ALIGN_CENTER, use style="text-align: center". The formatting hints tell you exactly what the source document shows — follow them.

11. SPACING: Use <br> tags for spacing between sections. Standard pattern:
    - 1 <br> after header tag
    - NO <br> between date and mailing address (they are adjacent)
    - <br><br><br><br><br> after mailing address (standard 5-br gap before next section)
    - EXCEPTION: If a horizontal rule/line (`<hr>`) immediately follows the mailing address, use `<hr>` instead of the 5-br gap — do NOT add both
    - 1 <br> after Loan Number/Property Address table (if present)
    - 1 <br> before and after salutation line
    - 1 <br> between body paragraphs
    - Spacing around "Sincerely," is SOURCE-DRIVEN: check the IR for actual blank lines before/after it. If the IR shows a <br> between "Sincerely," and the next line, include it. If there is NO <br> (they are adjacent), do NOT add one. Do NOT assume 1 <br> after "Sincerely," — read the source.
    - In the closing section, use 1 <br> to separate logical groups (e.g. between company name and legal notice lines)

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
   - CRITICAL: ONLY underline text when the source explicitly shows [FORMATTING: UNDERLINE] or [FORMATTING: HYPERLINK(...)]
     * Do NOT automatically underline phone numbers, fax numbers, emails, or URLs
     * If the source paragraph has [FORMATTING: UNDERLINE], then apply <u> to the relevant text
     * If no underline formatting is indicated, leave the text plain — even for phone numbers and emails
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

1. HEADER DETECTION — OBEY THE [HEADER_DIRECTIVE] INJECTED AT THE TOP OF DOCUMENT CONTENT:
   - The system has already analysed the document and injected a [HEADER_DIRECTIVE] telling you exactly which header to use.
   - [HEADER_DIRECTIVE: ... NMLS detected] → <div>{Header(NMLSID)}</div>
   - [HEADER_DIRECTIVE: ... H003 conditional logic detected] → <div>{Insert(H003 TagHeader)}</div>
   - [HEADER_DIRECTIVE: ... use default] → <div>{[tagHeader]}</div>
   - DO NOT override the directive — do not second-guess it by looking for NMLS/H003 yourself.
   - Key rule: {Insert(H003 TagHeader)} is ONLY correct when H003 has explicit conditional suppression logic in the source. A plain H003 tag appearance uses {[tagHeader]} (the default).

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
   - STEP 5: If labels exist, create a **2-COLUMN** table (label | value).
     * First row: The FULL loan number label as ONE cell → loan number variable
     * Second row: Property address label → Compress() with ONLY the address variables present in the document
   - LOAN NUMBER VARIABLE DETECTION:
     * If metadata says "LAST 4 DIGITS" or "last four" or similar → use `{[loanNumberLast4]}`
     * Otherwise → use `{[M594]}`
     * The "last 4" instruction often appears as red/asterisked metadata after the tag, e.g.: 
       "{[M594]} *METADATA ONLY PRINT LAST 4 DIGITS OF LOAN NUMBER*"
   - LABEL EXTRACTION - Use the COMPLETE label as ONE cell:
     * "Re: Loan Number:" → ONE cell: `<td width="20%" valign="top">Re: Loan Number:</td>`
     * "Loan Number:" → ONE cell: `<td width="20%" valign="top">Loan Number:</td>`
     * NEVER split a label into multiple columns (e.g., NEVER put "Re:" in one cell and "Loan Number:" in another)
   - RE/PROPERTY ADDRESS ROW - Combine address variables using Compress() with ONLY the variables PRESENT IN THE DOCUMENT:
     * The IR annotations tell you exactly which variables to combine and the correct Compress() expression — follow them
     * Address continuation lines (annotated with "[NOTE: Part of property address above]") are NOT separate rows — they belong in the same Compress()
     * NEVER output address variables as separate table rows
   - CRITICAL: This is always a 2-column table. Labels NOT bold. Format:
     <table width="100%"><tbody><tr>
       <td width="20%" valign="top">Re: Loan Number:</td>
       <td>{[loanNumberLast4]}</td>
     </tr><tr>
       <td width="20%" valign="top">RE:</td>
       <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
     </tr></tbody></table>
   - ONLY include this table if Document Content shows EXPLICIT labels like "Loan Number:", "RE:", "Property Address:" as separate labeled sections
   - DO NOT create this table just because property address variables appear in regular content paragraphs

3. STRUCTURE — DERIVE FROM THE DOCUMENT (do NOT assume a fixed layout):
   The document content tells you what elements exist and in what order. Output them in the same order.
   Common elements (include ONLY if present in the document):
   - Header tag (use the [HEADER_DIRECTIVE] to determine format)
   - Date line (apply alignment from [FORMATTING: ALIGN_*] hints)
   - Mailing address (collapse individual address M-codes into {[mailingAddress]} per IR annotations)
   - Loan Number / Property Address table (use EXACT labels from source, Compress() per IR annotations)
   - Translation / language services block (if present)
   - Salutation
   - Body paragraphs
   - Closing (Sincerely, company info, legal notices)

   Example base structure (adapt to match your document):
<div>{[tagHeader]}</div>
<br>
<div>{[L001]}</div>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>
<!-- CRITICAL: Loan Number and RE: table - ONLY include if Document Content shows EXPLICIT labels like "Loan Number:" or "RE:" as separate labeled sections -->
<!-- DO NOT create this table just because property address variables (M567, M583, M568) appear in content paragraphs -->
<!-- ONLY create if you see explicit labels like "Loan Number: [M594]" or "RE: [M567]" as separate sections -->
[Loan Number/RE table ONLY if explicit labels exist — ALWAYS 2-COLUMN format:
<table width="100%"><tbody><tr>
  <td width="20%" valign="top">EXACT_FULL_LABEL:</td>  <!-- e.g., "Re: Loan Number:" as ONE cell, NOT split -->
  <td>{[loanNumberLast4]} or {[M594]}</td>  <!-- Based on metadata instruction -->
</tr><tr>
  <td width="20%" valign="top">RE:</td>
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>  <!-- ALWAYS Compress ALL address parts -->
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

CRITICAL: YOU MUST INCLUDE ALL CONTENT FROM THE DOCUMENT IN THE EXACT ORDER IT APPEARS:

**UNIVERSAL COMPLETENESS RULES:**
1. Extract EVERY paragraph shown in Document Content - count them to verify
2. Output content in the SAME ORDER it appears in the Document Content
3. Include ALL elements present in the document — do NOT skip any paragraphs, tables, or sections
4. Do NOT add elements that are NOT in the document (no inventing tables, sections, or variables)
5. Closing section: include everything after "Sincerely," — company info, legal notices, ALL remaining content

**CRITICAL DETECTION RULES:**
- If Document Content shows text AFTER "Sincerely," → Include ALL of it
- If you see ALL-CAPS paragraphs → These are legal notices, include them
- If you see {[plsMatrix.CompanyReturnAddr1]} → Include company address block
- If you see "FEDERAL LAW REQUIRES" or "DEBT COLLECTOR" → Include entire legal notice
- Do NOT assume document ends at "Sincerely," - always check for more content

**STOPPING CRITERIA:**
- ONLY stop when you've processed ALL paragraphs in Document Content
- Check the END of Document Content - are there more paragraphs after "Sincerely,"?
- If yes, extract ALL of them
- PRESERVE ALL STYLING from the source document:
  - If text is centered, use style="text-align: center"
  - If text has a specific font size, include font-size in the style attribute
  - If text is bold, wrap in <b> tags
  - If text is underlined, wrap in <u> tags
  - If text is both bold and underlined, use <b><u>...</u></b>
- For tables, extract the ACTUAL table structure and content from the document - look at the Document Content for table information
- NEVER generate placeholder tables with "Column 1, Column 2" or "Add actual table rows here" - extract the real table content
- If you see table content in the Document Content, extract ALL rows and cells with their actual content
- Tables should have proper structure: headers in first row with <b> tags, data rows below

**TABLE BORDER RULES — read the TABLE_BORDERS annotation on every table and apply exactly:**
- `TABLE_BORDERS: none` → `<table width="100%" style="border-collapse:collapse">` with NO border styles on any td/th
- `TABLE_BORDERS: box (outer border only …)` → add `border="1"` (or equivalent CSS) on the `<table>` only; no `<td>` borders
- `TABLE_BORDERS: grid (full inside+outside …)` → `<table width="100%" border="1" style="border-collapse:collapse">` — every cell gets a visible border. Use the reported style (e.g. "single 0.5pt") to set the CSS border value on the table
- `TABLE_BORDERS: inner-only …` → no outer table border; add `border-top: 1px solid` / `border-bottom: 1px solid` on each `<td>` for row separators only
- `TABLE_BORDERS: mixed (…)` → set each `<td>` individually using the per-side values listed
- If a cell annotation includes `cell-border={…}`, that cell overrides the table-level border for those sides
- Column widths: if a cell has `[w=X%]`, apply `style="width:X%"` on that `<td>` / `<th>`
- Colspan: if `[colspan=N]`, emit `colspan="N"` on that `<td>`
- Row height from `vAlign`: apply `valign="top"` / `valign="middle"` / `valign="bottom"` as reported
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
- Include closing signature section with proper spacing:
  * Standard spacing: 2 <br> tags BEFORE "Sincerely," not after
  * Example: <div>Last paragraph.</div><br><br><div>Sincerely,</div><div>Department Name</div><div>{[plsMatrix.CompanyLongName]}</div>
  * Do NOT add extra <br> tags after "Sincerely," or between department/company name
- CRITICAL: After "Sincerely," check Document Content for company information block:
  * Look for company name variables: {[plsMatrix.CompanyLongName]}
  * Look for company address variables: {[plsMatrix.CompanyReturnAddr1]}, {[plsMatrix.CompanyReturnAddr2]}
  * Look for phone number variables: {[plsMatrix.SPOCContactPhone]}, {[plsMatrix.CSPhoneNumber]}
  * If these appear after "Sincerely," in Document Content, include them in a company info block:
    <br>
    <div>{[plsMatrix.CompanyLongName]}</div>
    <div>{[plsMatrix.CompanyReturnAddr1]}</div>
    <div>{[plsMatrix.CompanyReturnAddr2]}</div>
    <div>{[plsMatrix.SPOCContactPhone]}</div>
- CRITICAL: Some documents have a legal notice (debt collection notice) after the signature - include ALL paragraphs after "Sincerely,"
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
- STEP 2: For each paragraph, check if it has [FORMATTING: BOLD] or [FORMATTING: PARTIAL_BOLD(...)] note
- STEP 3: Handle different bold types:
  
  **[FORMATTING: BOLD]** - Entire paragraph is bold:
  * Wrap entire text: <div><b>entire paragraph text</b></div>
  
  **[FORMATTING: PARTIAL_BOLD(text1; text2)]** - Only specific parts are bold:
  * The parentheses show WHICH text is bold
  * Example: "PARTIAL_BOLD(Please note that all appraisals)" means ONLY that first sentence is bold
  * Format as: <div><b>First sentence only bold.</b> Rest of paragraph not bold.</div>
  * CRITICAL: Do NOT make entire paragraph bold if it shows PARTIAL_BOLD
  
  **Common bold patterns to look for:**
  - First sentence only: <div><b>First sentence.</b> Rest continues.</div>
  - Mid-sentence emphasis: <div>Text before <b>bold term</b> text after.</div>
  - Combined with underline: <div><b>Bold text with <u>underlined part</u> inside.</b></div>
  - Program names: "Emergency Mortgage Assistance Program (EMAP)" → <b>EMAP</b>
  - Time-sensitive phrases: "within 60 days" → <b>within 60 days</b>
  - Section headers: "You may be eligible if:" → <b>You may be eligible if:</b>
  
- STEP 4: Apply bold formatting consistently throughout the document
- STEP 5: Double-check that ALL [FORMATTING: BOLD] and [FORMATTING: PARTIAL_BOLD] notes have been addressed

BULLET POINTS ANALYSIS (MUST PERFORM SYSTEMATICALLY):
- STEP 1: Scan Document Content for [FORMATTING: LIST_ITEM_LEVEL_X] notes - these indicate actual Word list items
- STEP 2: When you find LIST_ITEM paragraphs, identify where they start and end (consecutive LIST_ITEM paragraphs form one list)
- STEP 3: Determine TABLE vs DIV format based on spatial alignment:
  * If the list text is indented PAST the bullet/number (text wraps in its own column) → TABLE format
  * If the list text wraps back to the SAME margin as the bullet/number → DIV format
  
  TABLE format (text indented past bullet):
  <div><table width="100%" style="border-collapse: collapse"><tbody><tr><td width="3%" valign="top">•</td><td>Bullet point text here</td></tr><tr><td width="3%" valign="top">•</td><td>Next bullet point</td></tr></tbody></table></div>
  CRITICAL: Notice the <div> wrapper around the table - this is required!
  CRITICAL: Use style="border-collapse: collapse" on the table
  CRITICAL: Bullet character goes in FIRST <td>, content in SECOND <td>
  
  DIV format (text wraps inline with bullet):
  <div style="margin-left: 25px">• Bullet point text here</div>
  <div style="margin-left: 25px">• Next bullet point</div>
  CRITICAL: NO style="text-align: center" on the bullet <td> - just plain <td width="3%" valign="top">
  CRITICAL: Use • (bullet character) for list items, not just regular dashes
- STEP 4: Continue scanning after formatting one set - look for MORE LIST_ITEM sets
- STEP 5: Format EACH set of LIST_ITEM paragraphs as a separate table (with div wrapper)
- CRITICAL: When converting LIST_ITEM paragraphs to tables, you MUST include the COMPLETE text from each item - NEVER truncate
- CRITICAL: ONLY format paragraphs with [FORMATTING: LIST_ITEM_LEVEL_X] as bullet point tables
- CRITICAL: Do NOT format regular paragraphs (without LIST_ITEM) as bullet points
  If Document Content shows:
  "Next Steps:
  • Paragraph 1 about step 1
  • Paragraph 2 about step 2
  • Paragraph 3 about step 3"
  Then format as:
  <div><b>Next Steps:</b></div>
  <br>
  <div><table width="100%" style="border-collapse: collapse"><tbody>
  <tr>
    <td width="3%" valign="top">•</td>
    <td>Paragraph 1 about step 1</td>
  </tr>
  <tr>
    <td width="3%" valign="top">•</td>
    <td>Paragraph 2 about step 2</td>
  </tr>
  <tr>
    <td width="3%" valign="top">•</td>
    <td>Paragraph 3 about step 3</td>
  </tr>
  </tbody></table></div>
  
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
- ONLY include a Loan Number / RE / Property Address table if the Document Content shows explicit labels for it — do NOT add one if none exists
- Use the EXACT labels from the document — do NOT rename "Re: Loan No:" to "Loan Number:" or any other normalization
- OBEY the [HEADER_DIRECTIVE] at the top of Document Content — it tells you the correct header format
- Conditional syntax - STRING comparisons need quotes: '{[TAG]}', NUMERIC comparisons don't: {[TAG]}, always use &gt; not >
- After section headers ending with ":", check if bullet points follow — if so, format them as tables

STEP 3 - FORMATTING (MANDATORY - THIS IS CRITICAL):
YOU MUST FORMAT WITH NEWLINES. LOOK AT THE EXAMPLES - THEY ALL HAVE EACH ELEMENT ON ITS OWN LINE.

Example of CORRECT formatting (showing different header layouts):
<div>{[tagHeader]}</div>
<br>
<div>{[L001]}</div>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>
[Example 1 - 2-column table with labels copied from source document:]
<table width="100%"><tbody><tr>
  <td width="20%" valign="top">EXACT_LABEL_FROM_SOURCE:</td>
  <td>{[loan_number_variable]}</td>
</tr><tr>
  <td width="20%" valign="top">EXACT_LABEL_FROM_SOURCE:</td>
  <td>{Compress(address variables from document)}</td>
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
[Example of bullet points formatted as table with div wrapper:]
<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="3%" valign="top">•</td>
  <td>Your mortgage loan must be current at the time of cancellation.</td>
</tr><tr>
  <td width="3%" valign="top">•</td>
  <td>Another bullet point item here.</td>
</tr></tbody></table></div>
<br>
<br>
<div>Sincerely,</div>
<div>PMI/MIP Department</div>
<div>{[plsMatrix.CompanyLongName]}</div>
<br>
[Example 2 - ONLY use 3-column format if Document Content shows "RE:" on the same line as "Loan Number:":]
Pattern: If you see "RE: Loan Number: [M594]" on ONE line, use 3-column table:
<table width="100%"><tbody><tr>
  <td width="3%" valign="top">RE:</td>
  <td width="20%" valign="top">Loan Number:</td>
  <td>{[M594]}</td>
</tr><tr>
  <td width="3%" valign="top"></td>
  <td width="20%" valign="top">Property Address:</td>
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table>

Default Pattern: If "Loan Number:" and "RE:" are on SEPARATE lines, use 2-column table (Pattern A from STEP 1).
<br>
<div style="text-align: center; font-size: 14pt"><b>IMPORTANT NOTICE:</b></div>
<div style="text-align: center; font-size: 14pt"><b>MORTGAGE PAYMENT INCREASE BEGINS...</b></div>
<br>
<div><b>This notice is to advise you that important information follows.</b> Then continues with regular text.</div>
<br>

Example of WRONG formatting (DO NOT DO THIS):
<div>{[tagHeader]}</div><br><div>{[L001]}</div><div>{[mailingAddress]}</div><br><br><br><br><br>...

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
			layout_png_b64 = data.get('layoutPngBase64')
			if isinstance(layout_png_b64, str) and 'base64,' in layout_png_b64:
				layout_png_b64 = layout_png_b64.split('base64,', 1)[-1].strip()
			
			if not ir:
				return self._send(400, {'success': False, 'error': 'No IR data provided'})
			
			# PII Policy Compliance Check - scan IR before sending to AI
			if scan_ir_for_pii is not None:
				pii_result = scan_ir_for_pii(ir)
				if pii_result.has_pii or pii_result.severity == 'BLOCKED':
					error_msg = build_error_response(pii_result)
					if log_audit_event:
						log_audit_event('GENERATE_BLOCKED', None, pii_result, error_msg[:120] if error_msg else '')
					print(f"PII SCAN BLOCKED: {pii_result.to_dict()}")
					return self._send(403, {
						'success': False,
						'error': error_msg or 'Document blocked by PII policy scanner.',
						'pii_scan': pii_result.to_dict()
					})
				elif pii_result.severity == 'WARNING':
					if log_audit_event:
						log_audit_event('GENERATE_WARNING', None, pii_result, 'Proceeding with warnings')
					print(f"PII SCAN WARNING (proceeding): {pii_result.to_dict()}")
			else:
				print("WARNING: PII scanner module not available - proceeding without scan")
			
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
			
			print(f"Anthropic API key found (length: {len(api_key)})")
			
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

				use_layout_image = (
					isinstance(layout_png_b64, str)
					and len(layout_png_b64) > 200
				)
				if use_layout_image:
					max_tokens = min(max_tokens + 4000, 16000)

				print(f"Document has {ir_blocks} blocks, estimated input tokens: ~{estimated_input_tokens}, using max_tokens={max_tokens}, layoutImage={bool(use_layout_image)}")

				if use_layout_image:
					layout_note = (
						"The first image is page 1 of the source document as rendered (PDF raster). "
						"Use it to match table grid, borders, column widths, cell alignment, and spacing. "
						"Preserve bold/italic/underline from the IR run formatting below; use the image to confirm structure and alignment. "
						"All wording and merge fields must still come from the Document Content / IR text below, not from the image.\n\n"
					)
					user_blocks = [
						{
							"type": "image",
							"source": {
								"type": "base64",
								"media_type": "image/png",
								"data": layout_png_b64.strip(),
							},
						},
						{"type": "text", "text": layout_note + user_message},
					]
					messages = [{"role": "user", "content": user_blocks}]
				else:
					messages = [{"role": "user", "content": user_message}]

				if messages_create_with_retries is not None:
					response = messages_create_with_retries(
						client,
						model=model_name,
						max_tokens=max_tokens,
						system=full_system_prompt,
						messages=messages,
						temperature=0,
					)
				else:
					response = client.messages.create(
						model=model_name,
						max_tokens=max_tokens,
						system=full_system_prompt,
						messages=messages,
						temperature=0,
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
				'notes': notes,
				'layoutImageUsed': bool(use_layout_image),
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

