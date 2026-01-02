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
			
			if not isinstance(current_html, str):
				return self._send(400, {'success': False, 'error': 'currentHtml must be a string'})
			
			if not instruction:
				return self._send(400, {'success': False, 'error': 'No instruction provided'})
			
			if not isinstance(instruction, str):
				return self._send(400, {'success': False, 'error': 'instruction must be a string'})
			
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
			
			# Format IR for context (similar to generate-template)
			ir_context = ""
			if ir and isinstance(ir, dict) and 'blocks' in ir:
				blocks = ir.get('blocks', [])[:20]  # Limit to first 20 blocks for context
				ir_context = "\n\nDocument Content (for reference):\n"
				for idx, block in enumerate(blocks):
					if block.get('type') == 'paragraph':
						runs = block.get('runs', [])
						text = ''.join([r.get('text', '') for r in runs]).strip()
						if text and len(text) > 10:
							ir_context += f"Paragraph {idx + 1}: {text[:500]}\n"
					elif block.get('type') == 'table':
						rows = block.get('rows', [])
						ir_context += f"Table {idx + 1} ({len(rows)} rows)\n"
			
			# Check HTML size - if too large, we may need to handle it differently
			html_size = len(current_html)
			print(f"Patching HTML template: size={html_size} chars, instruction='{instruction[:100]}...'")
			
			# Estimate token count (roughly 4 chars per token)
			estimated_tokens = html_size // 4
			
			# For very large HTML files, we might exceed input token limits
			# GPT-4o has ~128k context window, but we need room for system prompt, instruction, and response
			if estimated_tokens > 100000:  # Very large - might exceed limits
				return self._send(400, {
					'success': False, 
					'error': f'HTML template is too large ({html_size} chars, ~{estimated_tokens} tokens). Please use a smaller template or break the change into smaller parts.'
				})
			
			# For very large HTML files, increase max_tokens for response
			max_tokens = 8000
			if html_size > 50000:  # Very large HTML
				max_tokens = 16000
			elif html_size > 20000:  # Large HTML
				max_tokens = 12000
			
			user_message = f"""Modify the following HTML template according to this instruction:

Instruction: {instruction}
{ir_context}

Current HTML:
```html
{current_html}
```

CRITICAL RULES:
1. Apply the instruction EXACTLY as requested
2. Maintain all variable placeholders ({[TAG]} format) - DO NOT change them
3. Maintain all helper functions (Money, Compress, DateAdd, Date, DateDiff, If, etc.) - DO NOT change their syntax
4. Maintain proper HTML structure (each element on its own line)
5. Preserve all styling (bold, underline, font-size, text-align)
6. If adding bullet points, format them as a table: <table width="100%"><tbody><tr><td width="3%" valign="top" style="text-align: center">•</td><td>Text</td></tr></tbody></table>
7. If fixing header structure, extract the EXACT structure from Document Content above
8. Return ONLY the complete modified HTML, no explanations, no markdown code blocks
9. If the HTML is very large, make sure to return the COMPLETE modified HTML, not just a portion

Return ONLY the modified HTML:"""
			
			# Call OpenAI - using gpt-4o for better quality (same as generate-template)
			print(f"Calling OpenAI API: model=gpt-4o, max_tokens={max_tokens}, message_length={len(user_message)}")
			response = client.chat.completions.create(
				model="gpt-4o",
				messages=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": user_message}
				],
				temperature=0,  # Deterministic
				max_tokens=max_tokens
			)
			print(f"OpenAI API call successful, response length: {len(response.choices[0].message.content)}")
			
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
			error_trace = traceback.format_exc()
			error_msg = str(e)
			error_type = type(e).__name__
			print(f"ERROR in patch-template: {error_type}: {error_msg}")
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
					self.send_header('Access-Control-Allow-Origin', '*')
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
			
			# Ensure payload can be serialized
			response_body = json.dumps(payload).encode('utf-8')
			self.wfile.write(response_body)
			print(f"Sent response: status={status}, body_length={len(response_body)}")
		except Exception as e:
			print(f"Error in _send: {e}")
			traceback.print_exc()
			# Try to send a basic error response
			try:
				self.send_response(500)
				self.send_header('Content-type', 'application/json')
				self.send_header('Access-Control-Allow-Origin', '*')
				self.end_headers()
				error_payload = {'success': False, 'error': f'Failed to send response: {str(e)}'}
				self.wfile.write(json.dumps(error_payload).encode('utf-8'))
			except:
				pass

