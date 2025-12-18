from http.server import BaseHTTPRequestHandler
import json
import os
import traceback

try:
	import openai
	OPENAI_AVAILABLE = True
except ImportError:
	OPENAI_AVAILABLE = False

# Import normalization
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
		return """You are an expert HTML template generator for mortgage servicing documents. 
Generate HTML templates that match the exact formatting style shown in examples."""

class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', '0'))
			post_data = self.rfile.read(content_length)
			
			data = json.loads(post_data.decode('utf-8') or '{}')
			current_html = data.get('currentHtml')
			instruction = data.get('instruction')
			ir = data.get('ir')
			
			if not current_html:
				return self._send(400, {'success': False, 'error': 'No current HTML provided'})
			
			if not instruction:
				return self._send(400, {'success': False, 'error': 'No instruction provided'})
			
			if not OPENAI_AVAILABLE:
				return self._send(500, {'success': False, 'error': 'OpenAI library not available'})
			
			# Get OpenAI API key
			api_key = os.environ.get('OPENAI_API_KEY')
			if not api_key:
				return self._send(500, {'success': False, 'error': 'OPENAI_API_KEY environment variable not set'})
			
			# Initialize OpenAI client
			client = openai.OpenAI(api_key=api_key)
			
			# Build prompt for patching
			system_prompt = load_system_prompt()
			
			user_message = f"""Modify the following HTML template according to this instruction:

Instruction: {instruction}

Current HTML:
```html
{current_html}
```

Apply the instruction while maintaining:
1. All variable placeholders ({[TAG]} format)
2. All helper functions (Money, Compress, DateAdd, etc.)
3. The overall structure and style
4. Proper formatting (tables, divs, spacing)

Return ONLY the modified HTML, no explanations:"""
			
			# Call OpenAI - using gpt-3.5-turbo for lower cost
			response = client.chat.completions.create(
				model="gpt-3.5-turbo",
				messages=[
					{"role": "system", "content": system_prompt},
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
			
			return self._send(200, {
				'success': True,
				'html': html
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

