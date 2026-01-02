from http.server import BaseHTTPRequestHandler
import json
import os
import traceback

try:
	import openai
	OPENAI_AVAILABLE = True
except ImportError:
	OPENAI_AVAILABLE = False

# Import normalization - MINIMAL normalization that PRESERVES formatting
def normalize_html(html):
	"""Minimal normalization - preserve newlines and formatting structure"""
	if not html or not isinstance(html, str):
		return ''
	
	normalized = html
	
	# Normalize line endings only
	normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
	
	# Normalize <br> tags only (standardize format, but keep them)
	import re
	normalized = re.sub(r'<br\s*/?>', '<br>', normalized, flags=re.IGNORECASE)
	
	# DO NOT remove newlines or collapse whitespace - preserve formatting structure
	# Only normalize trailing whitespace at end of file
	normalized = normalized.rstrip()
	
	return normalized

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
Use {{[TAG]}} format for variables, {{[plsMatrix.*]}} for company variables.
Remove last 2 characters from tag variables ending in digits/letters.
Always use {{Compress({{[M567]}}|{{[M583]}}|{{[M568]}})}} for property addresses.
Use <div>Dear {{[Salutation]}},</div> for salutations.
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
			
			# Estimate token count (roughly 4 chars per token for HTML)
			# But HTML tags compress well, so estimate more conservatively
			estimated_tokens = html_size // 3  # More conservative estimate
			
			# For very large HTML files, we might exceed input token limits
			# GPT-4o has ~128k context window, but we need room for system prompt, instruction, and response
			# Let's be more lenient - only reject if it's clearly too large
			if estimated_tokens > 120000:  # Very large - might exceed limits
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

CRITICAL FORMATTING RULES - PRESERVE EXACT STRUCTURE:
1. **PRESERVE ALL NEWLINES AND INDENTATION**: The HTML must maintain the exact same formatting structure as the input:
   - Each <div> tag MUST be on its own line
   - Each <br> tag MUST be on its own line
   - Each <table>, <tr>, <td> MUST be on its own line with proper indentation
   - DO NOT collapse everything into one line
   - DO NOT remove newlines between elements
   - Look at the Current HTML above - it has proper newlines and formatting. You MUST preserve this exact structure.

2. Apply the instruction EXACTLY as requested

3. Maintain all variable placeholders ({{[TAG]}} format) - DO NOT change them

4. Maintain all helper functions (Money, Compress, DateAdd, Date, DateDiff, Math, If, etc.) - DO NOT change their syntax

5. Preserve all styling (bold, underline, font-size, text-align)

6. CRITICAL BULLET POINTS: If adding or fixing bullet points (especially after section headers like "Next Steps:", "Forbearance Plan Terms:", etc.), format them as a table:
   <table width="100%"><tbody>
   <tr>
     <td width="3%" valign="top" style="text-align: center">•</td>
     <td>First bullet point text</td>
   </tr>
   <tr>
     <td width="3%" valign="top" style="text-align: center">•</td>
     <td>Second bullet point text</td>
   </tr>
   </tbody></table>
   - Each bullet point MUST be in its own <tr> row
   - Each row MUST be on its own line with proper indentation
   - After section headers ending with ":", ALWAYS check for bullet points that follow

7. HEADER LOGIC (if fixing header structure):
   - DEFAULT: Use <div>{{Insert(H003 TagHeader)}}</div> unless NMLS is mentioned
   - If Document Content mentions NMLS/NMLSID → Use: <div>{{Header(NMLSID)}}</div>
   - Only use <div>{{[tagHeader]}}</div> if Document Content explicitly shows tagHeader without H003

8. LOAN NUMBER AND RE: TABLE: Most letters MUST include a table with Loan Number and RE: after mailing address and before salutation. Extract the EXACT structure from Document Content.

9. Return ONLY the complete modified HTML, no explanations, no markdown code blocks

10. If the HTML is very large, make sure to return the COMPLETE modified HTML, not just a portion

11. **FORMATTING EXAMPLE**: The output should look like this (with proper newlines):
<div>{{Insert(H003 TagHeader)}}</div>
<br>
<div>{{[L001]}}</div>
<div>{{[mailingAddress]}}</div>
<br><br><br><br><br>
<table width="100%"><tbody><tr>
  <td width="20%" valign="top">Loan Number:</td>
  <td>{{[M594]}}</td>
</tr><tr>
  <td width="20%" valign="top">RE:</td>
  <td>{{Compress({{[M567]}}|{{[M583]}}|{{[M568]}})}}</td>
</tr></tbody></table>
<br>
<div>Dear {{[Salutation]}},</div>
<br>

NOT like this (all on one line):
<div>{{Insert(H003 TagHeader)}}</div><br><div>{{[L001]}}</div><div>{{[mailingAddress]}}</div>...

Return ONLY the modified HTML with proper newlines and formatting:"""
			
			# Call OpenAI - using gpt-4o for better quality (same as generate-template)
			system_prompt_length = len(system_prompt)
			user_message_length = len(user_message)
			total_estimated_tokens = (system_prompt_length + user_message_length) // 3
			
			print(f"Calling OpenAI API: model=gpt-4o")
			print(f"  System prompt: {system_prompt_length} chars (~{system_prompt_length//3} tokens)")
			print(f"  User message: {user_message_length} chars (~{user_message_length//3} tokens)")
			print(f"  Total input: ~{total_estimated_tokens} tokens")
			print(f"  Max output tokens: {max_tokens}")
			
			if total_estimated_tokens > 120000:
				return self._send(400, {
					'success': False,
					'error': f'Request is too large (~{total_estimated_tokens} tokens). The HTML template or instruction is too large to process.'
				})
			
			try:
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
			except Exception as api_error:
				error_msg = f"OpenAI API error: {str(api_error)}"
				print(f"ERROR: {error_msg}")
				print(f"API Error type: {type(api_error).__name__}")
				traceback.print_exc()
				return self._send(500, {'success': False, 'error': error_msg})
			
			if not response or not response.choices or len(response.choices) == 0:
				return self._send(500, {'success': False, 'error': 'Empty response from OpenAI API'})
			
			html = response.choices[0].message.content.strip()
			
			if not html:
				return self._send(500, {'success': False, 'error': 'Empty HTML returned from OpenAI API'})
			
			# Remove markdown code blocks if present
			if html.startswith('```html'):
				html = html.replace('```html', '').replace('```', '').strip()
			elif html.startswith('```'):
				html = html.replace('```', '').strip()
			
			# MINIMAL normalization - preserve formatting structure
			# Only normalize line endings, don't remove newlines or collapse whitespace
			html = normalize_html(html)
			
			return self._send(200, {
				'success': True,
				'html': html
			})
			
		except json.JSONDecodeError as e:
			error_msg = f"Invalid JSON in request: {str(e)}"
			print(f"ERROR: {error_msg}")
			return self._send(400, {'success': False, 'error': error_msg})
		except Exception as e:
			error_trace = traceback.format_exc()
			error_msg = str(e)
			error_type = type(e).__name__
			print(f"ERROR in patch-template: {error_type}: {error_msg}")
			print(f"Traceback: {error_trace}")
			# Return a user-friendly error message - ALWAYS include the error message
			try:
				# Build a helpful error message
				user_error_msg = f"{error_type}: {error_msg}"
				
				# Add more context for common errors
				if 'API' in error_type or 'openai' in error_msg.lower():
					user_error_msg = f"OpenAI API Error: {error_msg}. Please check that OPENAI_API_KEY is set correctly."
				elif 'token' in error_msg.lower() or 'limit' in error_msg.lower():
					user_error_msg = f"Token Limit Error: {error_msg}. The HTML template may be too large to process."
				elif 'JSON' in error_type:
					user_error_msg = f"Invalid Request: {error_msg}. Please check the request format."
				
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

