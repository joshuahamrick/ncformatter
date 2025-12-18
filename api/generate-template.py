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
	blocks = ir.get('blocks', [])
	formatted = []
	
	# Skip variable definition blocks - look for actual document content
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
		'Non-borrower'
	]
	
	for idx, block in enumerate(blocks):
		if block.get('type') == 'paragraph':
			runs = block.get('runs', [])
			text = ''.join([r.get('text', '') for r in runs])
			
			# Skip if this looks like a variable definition
			if any(pattern in text for pattern in skip_patterns):
				# Only include if it's part of actual content (has more than just the definition)
				if len(text) > 100:  # Likely actual content, not just definition
					formatted.append(f"Paragraph {idx + 1}: {text[:300]}")
			elif text.strip() and len(text.strip()) > 10:
				# Regular content
				formatted.append(f"Paragraph {idx + 1}: {text[:300]}")
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
	user_message = f"""Convert the following document content into formatted HTML following the style guide and examples.

IMPORTANT: Extract only the actual document text content. Ignore variable definitions like "[H002] Company Address Line 1" - those are metadata, not content.

Document Content:
{ir_content}

"""
	
	if user_instruction:
		user_message += f"Additional Instruction: {user_instruction}\n\n"
	
	user_message += """Generate the HTML template following these rules:
1. Extract ONLY the actual document content - ignore variable definitions like "[H002] Company Address Line 1"
2. Use exact variable format {[TAG]} and remove last 2 chars from tags ending in E6/E8/etc. (e.g., L001E8 → {[L001]})
3. Use {[plsMatrix.*]} for all company variables (CompanyLongName, CSPhoneNumber, etc.)
4. Use {Compress({[M567]}|{[M583]}|{[M568]})} for property addresses
5. Use <div>Dear {[Salutation]},</div> for salutations (NOT conditional logic)
6. Start with <div>{Insert(H003 TagHeader)}</div> or <div>{Insert(Flat Branch Header)}</div>
7. Follow the structure and spacing patterns from examples exactly
8. Return ONLY the HTML, no explanations, no markdown code blocks

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
				import_error = "OpenAI library not available. Install with: pip install openai"
				print(f"ERROR: {import_error}")
				return self._send(500, {'success': False, 'error': import_error})
			
			# Get OpenAI API key from environment
			api_key = os.environ.get('OPENAI_API_KEY')
			if not api_key:
				key_error = 'OPENAI_API_KEY environment variable not set. Please set it in Vercel project settings.'
				print(f"ERROR: {key_error}")
				return self._send(500, {'success': False, 'error': key_error})
			
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
				response = client.chat.completions.create(
					model="gpt-4o",  # Using gpt-4o for better quality
					messages=[
						{"role": "system", "content": full_system_prompt},
						{"role": "user", "content": user_message}
					],
					temperature=0,  # Deterministic
					max_tokens=4000
				)
				
				html = response.choices[0].message.content.strip()
			except Exception as api_error:
				error_msg = f"OpenAI API error: {str(api_error)}"
				print(error_msg)
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
			print(f"ERROR in generate-template: {error_msg}")
			print(f"Traceback: {error_trace}")
			# Return a user-friendly error message
			err = {
				'success': False,
				'error': error_msg,
				'trace': error_trace if 'VERCEL' not in os.environ else None  # Don't expose trace in production
			}
			return self._send(500, err)
	
	def do_OPTIONS(self):
		self.send_response(200)
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Headers', 'Content-Type')
		self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
		self.end_headers()
	
	def _send(self, status, payload):
		self.send_response(status)
		self.send_header('Content-type', 'application/json')
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Headers', 'Content-Type')
		self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
		self.end_headers()
		self.wfile.write(json.dumps(payload).encode('utf-8'))

