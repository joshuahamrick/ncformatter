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
	"""Normalize HTML for deterministic exact snapshot matching"""
	if not html or not isinstance(html, str):
		return ''
	
	normalized = html
	
	# Normalize line endings
	normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
	
	# Normalize <br> tags
	normalized = re.sub(r'<br\s*/?>', '<br>', normalized, flags=re.IGNORECASE)
	
	# Normalize whitespace around tags
	normalized = re.sub(r'\s+</', '</', normalized)
	normalized = re.sub(r'>\s+', '>', normalized)
	
	# Normalize conditional blocks
	normalized = re.sub(r'\{If\([^}]+\}\)\s+', lambda m: m.group(0).strip() + ' ', normalized)
	normalized = re.sub(r'\s+\{End If\}', lambda m: ' ' + m.group(0).strip(), normalized)
	
	# Normalize multiple <br> tags
	normalized = re.sub(r'(<br>\s*){3,}', lambda m: '<br>' * len(re.findall(r'<br>', m.group(0))), normalized)
	
	# Normalize whitespace between tags
	normalized = re.sub(r'>\s+<', '><', normalized)
	normalized = re.sub(r'>\s+([^<])', r'>\1', normalized)
	normalized = re.sub(r'([^>])\s+<', r'\1<', normalized)
	
	# Normalize trailing whitespace
	normalized = re.sub(r'\s+$', '', normalized, flags=re.MULTILINE)
	
	# Normalize empty lines
	normalized = re.sub(r'\n{3,}', '\n\n', normalized)
	
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
	
	curated = [
		'GB001/GB001-formatted.html',
		'ES114/ES114-formatted.html',
		'CA001/CA001-formatted.html',
		'CA003/CA003-formatted.html',
		'LM401/LM401-formatted.html',
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
			
			# Skip if it contains skip patterns and is short (likely just metadata)
			if any(pattern in text for pattern in skip_patterns):
				if len(text) < 100:  # Short = likely just metadata
					continue
				# If longer, might be actual content with metadata mention - include it
			
			# Skip conditional salutation text
			if re.search(r'\(or if\s+\[.*\]\s+(and/or|present)\)', text, re.IGNORECASE):
				continue
			
			# This looks like actual content - include it
			formatted.append(f"Paragraph {idx + 1}: {text[:500]}")
		elif block.get('type') == 'table':
			rows = block.get('rows', [])
			# Extract table content
			table_text = []
			for row in rows[:5]:  # Limit rows
				cells = row.get('cells', [])
				row_text = ' | '.join([''.join([r.get('text', '') for r in c.get('runs', [])]) for c in cells[:3]])
				if row_text.strip():
					table_text.append(row_text[:100])
			if table_text:
				formatted.append(f"Table {idx + 1}: {' | '.join(table_text)}")
	
	return '\n'.join(formatted[:30])  # Limit to first 30 blocks

def build_prompt(ir, few_shot_examples, user_instruction=None):
	"""Build the complete prompt for OpenAI"""
	system_prompt = load_system_prompt()
	
	# Format IR content
	ir_content = format_ir_for_prompt(ir)
	
	# Build few-shot examples section
	few_shot_text = "\n## Example Outputs\n\n"
	for idx, ex in enumerate(few_shot_examples[:3]):  # Limit to 3 examples
		few_shot_text += f"### Example {idx + 1}: {ex['name']}\n```html\n{ex['html']}\n```\n\n"
	
	# Build user message
	# Note: Using regular string concatenation instead of f-string to avoid issues with {If()} syntax
	user_message = """Convert the following document content into formatted HTML following the style guide and examples.

CRITICAL RULES:
- Extract ONLY the actual document text content
- IGNORE variable definitions like "[H002] Company Address Line 1" - those are metadata
- IGNORE conditional logic text like "(or if [H581] and/or [H582] present)" - do NOT include this
- IGNORE instructions like "If [M065] ≥ 'July 29, 1999' then print:" - convert to proper {If()} syntax
- NEVER include conditional salutation logic - ALWAYS use <div>Dear {[Salutation]},</div>

Document Content:
""" + ir_content + """

"""
	
	if user_instruction:
		user_message += f"Additional Instruction: {user_instruction}\n\n"
	
	user_message += """Generate the HTML template following these EXACT rules:
1. Extract ONLY actual document content - ignore variable definitions, conditional text, and instructions
2. Use exact variable format {[TAG]} and remove last 2 chars from tags ending in E6/E8/etc. (e.g., L001E8 → {[L001]}, M029E6 → {[M029]})
3. Use {[plsMatrix.*]} for ALL company variables (CompanyLongName, CompanyShortName, CSPhoneNumber, HoursOfOperation, etc.)
4. Use {Compress({[M567]}|{[M583]}|{[M568]})} for property addresses
5. ALWAYS use <div>Dear {[Salutation]},</div> for salutations - NEVER include conditional salutation logic
6. Start with <div>{Insert(H003 TagHeader)}</div> or <div>{Insert(Flat Branch Header)}</div>
7. Use {[L001]} for date and {[mailingAddress]} for mailing address
8. Convert conditional logic properly: "If [M065] ≥ 'July 29, 1999' then print:" becomes {If('{[M065]}' &gt;= 'July 29, 1999')}
9. Follow the structure and spacing patterns from examples EXACTLY
10. Return ONLY the HTML, no explanations, no markdown code blocks, no conditional text

HTML Output:"""
	
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
				# Use gpt-3.5-turbo for lower cost (much cheaper than gpt-4o)
				# Cost: ~$0.001-0.002 per document vs $0.01-0.05 for gpt-4o
				model_name = "gpt-3.5-turbo"
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
					max_tokens=4000
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

