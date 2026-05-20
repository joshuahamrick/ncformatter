from http.server import BaseHTTPRequestHandler
import json
import os
import re
import traceback

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
		messages_create_with_retries = None


def normalize_html(html):
	"""Minimal normalization — preserve newlines and formatting structure."""
	if not html or not isinstance(html, str):
		return ''
	normalized = html.replace('\r\n', '\n').replace('\r', '\n')
	normalized = re.sub(r'<br\s*/?>', '<br>', normalized, flags=re.IGNORECASE)
	return normalized.rstrip()


def _format_changes_for_prompt(changes):
	"""Convert the changes list into a clear, numbered prompt section."""
	if not changes:
		return '(no changes specified)'
	lines = []
	for ch in changes:
		num  = ch.get('id', '?')
		typ  = ch.get('type', 'change')
		desc = ch.get('description', '')
		loc  = ch.get('location', '')
		cur  = ch.get('currentValue', '')
		nxt  = ch.get('newValue', '')

		line = f'{num}. [{typ.upper()}]'
		if loc:  line += f' @ {loc}'
		line += f'\n   Description: {desc}'
		if cur: line += f'\n   Current: "{cur}"'
		if nxt: line += f'\n   New:     "{nxt}"'
		lines.append(line)
	return '\n\n'.join(lines)


APPLY_SYSTEM_PROMPT = """You are an expert at making precise, surgical edits to HTML mortgage letter templates.

Your ONLY job is to apply the exact approved changes listed — nothing more, nothing less.

ABSOLUTE RULES:
1. Apply ONLY the changes listed. Do NOT change anything else.
2. Preserve ALL whitespace, newlines, and indentation exactly as in the input.
3. Preserve ALL NcFormatter variable placeholders ({[TAG]}, {[plsMatrix.*]}, etc.) exactly.
4. Preserve ALL helper functions ({Compress(...)}, {Math(...)}, {Money(...)}, {If(...)}, {Insert(...)}, etc.) exactly.
5. Preserve ALL HTML structure, attributes, and styling — only touch what the change specifies.
6. If a change says to replace specific text, replace ONLY that exact text string.
7. If a change says to add spacing, add ONLY that spacing in ONLY that location.
8. If a change says to remove something, remove ONLY that exact element.
9. Do NOT reformat, re-indent, or restructure anything.
10. Return ONLY the complete updated HTML — no explanations, no markdown fences.

The existing template was carefully crafted. Treat it with respect."""


class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', '0'))
			post_data = self.rfile.read(content_length)
			data = json.loads(post_data.decode('utf-8') or '{}')

			current_html  = data.get('currentHtml', '')
			changes       = data.get('changes', [])
			context_notes = data.get('contextNotes', '')

			if not current_html:
				return self._send(400, {'error': 'currentHtml is required'})
			if not changes:
				return self._send(200, {'success': True, 'html': current_html, 'message': 'No changes to apply.'})

			if not ANTHROPIC_AVAILABLE:
				return self._send(500, {'error': 'Anthropic library not available'})

			api_key = os.environ.get('ANTHROPIC_API_KEY')
			if not api_key:
				return self._send(500, {'error': 'ANTHROPIC_API_KEY not set'})

			client = anthropic.Anthropic(api_key=api_key)

			html_size = len(current_html)
			if html_size // 3 > 120000:
				return self._send(400, {'error': f'HTML template is too large ({html_size} chars). Please use a smaller template.'})

			max_tokens = 8000
			if html_size > 50000:
				max_tokens = 16000
			elif html_size > 20000:
				max_tokens = 12000

			changes_text = _format_changes_for_prompt(changes)
			context_section = f'\nContext from user: {context_notes}' if context_notes else ''

			user_message = f"""Apply the following approved changes to the HTML template.{context_section}

=== APPROVED CHANGES TO APPLY ===
{changes_text}

=== CURRENT HTML TEMPLATE ===
{current_html}

REMINDER:
- Apply ONLY the changes listed above, one by one.
- Touch NOTHING else — not whitespace, not structure, not variables, not styling.
- The output must be the complete HTML with ONLY the listed changes applied.
- Preserve the exact newlines and formatting of the original.

Return ONLY the complete updated HTML:"""

			print(f'apply-update: html={html_size} chars, changes={len(changes)}, max_tokens={max_tokens}')

			try:
				if messages_create_with_retries is not None:
					response = messages_create_with_retries(
						client,
						model='claude-sonnet-4-20250514',
						max_tokens=max_tokens,
						system=APPLY_SYSTEM_PROMPT,
						messages=[{'role': 'user', 'content': user_message}],
						temperature=0,
					)
				else:
					response = client.messages.create(
						model='claude-sonnet-4-20250514',
						max_tokens=max_tokens,
						system=APPLY_SYSTEM_PROMPT,
						messages=[{'role': 'user', 'content': user_message}],
						temperature=0,
					)
			except Exception as api_err:
				print(f'Anthropic API error: {api_err}')
				traceback.print_exc()
				return self._send(500, {'error': f'AI error: {str(api_err)}'})

			html = response.content[0].text.strip()

			# Strip markdown code fences if present
			if html.startswith('```html'):
				html = html[7:]
				if html.endswith('```'):
					html = html[:-3]
				html = html.strip()
			elif html.startswith('```'):
				html = html[3:]
				if html.endswith('```'):
					html = html[:-3]
				html = html.strip()

			html = normalize_html(html)

			if not html:
				return self._send(500, {'error': 'AI returned empty HTML.'})

			return self._send(200, {
				'success': True,
				'html': html,
				'changesApplied': len(changes),
			})

		except json.JSONDecodeError as e:
			return self._send(400, {'error': f'Invalid JSON: {e}'})
		except Exception as e:
			traceback.print_exc()
			return self._send(500, {'error': str(e)})

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
		self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
