from http.server import BaseHTTPRequestHandler
import json
import os
import traceback
import hashlib

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
	import re
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
	prompt_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'prompts', 'system-prompt.txt')
	try:
		with open(prompt_path, 'r', encoding='utf-8') as f:
			return f.read()
	except Exception:
		# Fallback prompt if file not found
		return """You are an expert HTML template generator for mortgage servicing documents. 
Generate HTML templates that match the exact formatting style shown in examples.
Use {[TAG]} format for variables, {[plsMatrix.*]} for company variables.
Remove last 2 characters from tag variables ending in digits/letters.
Always use {Compress({[M567]}|{[M583]}|{[M568]})} for property addresses.
Use <div>Dear {[Salutation]},</div> for salutations.
Return ONLY valid HTML, no explanations."""

def load_few_shot_examples():
	"""Load few-shot examples from formatted HTML files"""
	examples_dir = os.path.join(os.path.dirname(__file__), '..', 'formatter examples')
	curated = [
		'GB001/GB001-formatted.html',
		'ES114/ES114-formatted.html',
		'CA001/CA001-formatted.html',
		'CA003/CA003-formatted.html',
		'LM401/LM401-formatted.html',
	]
	
	examples = []
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
	
	return examples

def format_ir_for_prompt(ir):
	"""Format IR data into a readable prompt format"""
	blocks = ir.get('blocks', [])
	formatted = []
	
	for idx, block in enumerate(blocks):
		if block.get('type') == 'paragraph':
			runs = block.get('runs', [])
			text = ''.join([r.get('text', '') for r in runs])
			if text.strip():
				formatted.append(f"Paragraph {idx + 1}: {text[:200]}")
		elif block.get('type') == 'table':
			rows = block.get('rows', [])
			formatted.append(f"Table {idx + 1}: {len(rows)} rows")
	
	return '\n'.join(formatted[:50])  # Limit to first 50 blocks

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
	user_message = f"""Convert the following document structure into formatted HTML following the style guide and examples.

Document Structure:
{ir_content}

"""
	
	if user_instruction:
		user_message += f"Additional Instruction: {user_instruction}\n\n"
	
	user_message += """Generate the HTML template following these rules:
1. Use exact variable format {[TAG]} and remove last 2 chars from tags ending in E6/E8/etc.
2. Use {[plsMatrix.*]} for all company variables
3. Use {Compress({[M567]}|{[M583]}|{[M568]})} for property addresses
4. Use <div>Dear {[Salutation]},</div> for salutations
5. Follow the structure and spacing patterns from examples
6. Return ONLY the HTML, no explanations or markdown

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
				return self._send(500, {'success': False, 'error': 'OpenAI library not available. Install with: pip install openai'})
			
			# Get OpenAI API key from environment
			api_key = os.environ.get('OPENAI_API_KEY')
			if not api_key:
				return self._send(500, {'success': False, 'error': 'OPENAI_API_KEY environment variable not set'})
			
			# Initialize OpenAI client
			client = openai.OpenAI(api_key=api_key)
			
			# Load few-shot examples
			few_shot_examples = load_few_shot_examples()
			
			# Build prompt
			system_prompt, user_message, few_shot_text = build_prompt(ir, few_shot_examples, user_instruction)
			
			# Combine system prompt with few-shot examples
			full_system_prompt = system_prompt + "\n\n" + few_shot_text
			
			# Call OpenAI
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
			err = {
				'success': False,
				'error': str(e),
				'trace': traceback.format_exc()
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

