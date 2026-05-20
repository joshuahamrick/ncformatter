from http.server import BaseHTTPRequestHandler
import json
import os
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


def _ir_to_text_summary(ir):
	"""Convert an IR dict to a human-readable text summary for the prompt."""
	if not ir or not isinstance(ir, dict):
		return '(no document content)'
	blocks = ir.get('blocks', [])
	lines = []
	for block in blocks:
		btype = block.get('type', '')
		if btype == 'paragraph':
			runs = block.get('runs', [])
			text = ''.join(r.get('text', '') for r in runs).strip()
			if text:
				align = block.get('align', '')
				bold_count = sum(1 for r in runs if r.get('bold'))
				prefix = '[BOLD] ' if bold_count and bold_count == len([r for r in runs if r.get('text', '').strip()]) else ''
				align_note = f' [{align.upper()}]' if align and align != 'left' else ''
				lines.append(f'{prefix}{text}{align_note}')
		elif btype == 'table':
			rows = block.get('rows', [])
			lines.append(f'[TABLE: {len(rows)} rows]')
			for row in rows[:8]:
				cells = row.get('cells', [])
				cell_texts = []
				for cell in cells:
					cell_paras = cell.get('paragraphs', [])
					cell_text = ' | '.join(
						''.join(r.get('text', '') for r in p.get('runs', [])).strip()
						for p in cell_paras
					).strip()
					cell_texts.append(cell_text)
				lines.append('  ' + ' || '.join(cell_texts))
	return '\n'.join(lines) if lines else '(document appears empty)'


ANALYZE_SYSTEM_PROMPT = """You are an expert at comparing HTML mortgage letter templates with Word document sources.

Your job is to identify the MINIMAL, LOCALIZED set of changes needed to update an existing HTML template to match an updated Word document.

CRITICAL PRINCIPLES:
1. The existing HTML template is correct — only identify genuine differences that must change.
2. Be EXTREMELY CONSERVATIVE. If in doubt, do NOT flag it as a change.
3. Never suggest reformatting, restructuring, or restyling existing content.
4. Never suggest changes to HTML syntax, variable placeholders ({[TAG]}), or helper functions.
5. A text change means ONLY that specific text changed — nothing else.
6. A spacing change means ONLY that specific spacing changed — nothing else.
7. Ignore minor whitespace differences within unchanged paragraphs.
8. Preserve all NcFormatter-specific syntax exactly as-is.

CHANGE TYPES you may use:
- "text" — a specific word, phrase, or sentence changed
- "spacing" — blank lines or spacing between sections changed
- "addition" — entirely new content added
- "removal" — existing content removed
- "structure" — a section was reorganized (use sparingly)
- "tag" — an NcFormatter variable or helper function reference changed

RESPONSE FORMAT — always respond with valid JSON:
{
  "summary": "One or two sentences describing what changed overall.",
  "changes": [
    {
      "id": 1,
      "type": "text",
      "location": "Where in the template (e.g. 'paragraph 3', 'RE: table', 'closing section')",
      "description": "Clear, concise description of what needs to change",
      "currentValue": "The exact current text/value in the HTML (short — max ~150 chars)",
      "newValue": "The new text/value that should replace it (short — max ~150 chars)"
    }
  ],
  "reply": "A brief conversational message to the user (only needed if responding to chat; otherwise omit or use empty string)"
}

If the user is having a conversation to refine the plan, update the changes list accordingly and include a helpful reply.
If there are no meaningful differences, return an empty changes array and explain in the summary."""


class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', '0'))
			post_data = self.rfile.read(content_length)
			data = json.loads(post_data.decode('utf-8') or '{}')

			current_html     = data.get('currentHtml', '')
			word_doc_ir      = data.get('wordDocIR')
			context_notes    = data.get('contextNotes', '')
			messages         = data.get('messages', [])  # chat history
			current_changes  = data.get('currentChanges', [])
			current_summary  = data.get('currentSummary', '')

			if not current_html:
				return self._send(400, {'error': 'currentHtml is required'})
			if not word_doc_ir:
				return self._send(400, {'error': 'wordDocIR is required'})

			if not ANTHROPIC_AVAILABLE:
				return self._send(500, {'error': 'Anthropic library not available'})

			api_key = os.environ.get('ANTHROPIC_API_KEY')
			if not api_key:
				return self._send(500, {'error': 'ANTHROPIC_API_KEY not set'})

			client = anthropic.Anthropic(api_key=api_key)

			doc_text = _ir_to_text_summary(word_doc_ir)

			# Trim HTML for context (keep it manageable)
			html_preview = current_html
			if len(html_preview) > 40000:
				html_preview = html_preview[:40000] + '\n... [truncated for length]'

			# Build the initial analysis message
			initial_user_msg = f"""Compare the following EXISTING HTML TEMPLATE with the NEW WORD DOCUMENT content and identify the minimal set of changes needed.

=== CONTEXT / NOTES FROM USER ===
{context_notes if context_notes else '(none provided)'}

=== EXISTING HTML TEMPLATE (current version on file) ===
{html_preview}

=== NEW WORD DOCUMENT CONTENT (extracted text from updated document) ===
{doc_text}

Identify ONLY the specific, localized changes needed to update the HTML template to match the new Word document. Be conservative — only flag genuine differences."""

			# Build message list for API call
			if messages:
				# Conversation mode: reconstruct context with a synthetic first-turn assistant reply
				# so the model knows what the prior analysis was.
				prior_analysis = {
					'summary': current_summary,
					'changes': current_changes,
					'reply':   ''
				}
				synthetic_assistant = (
					'Here is my initial analysis:\n\n'
					+ json.dumps(prior_analysis, indent=2, ensure_ascii=False)
				)
				api_messages = [
					{'role': 'user',      'content': initial_user_msg},
					{'role': 'assistant', 'content': synthetic_assistant},
				]
				for msg in messages:
					api_messages.append({'role': msg['role'], 'content': msg['content']})
				# Ensure the last turn is a user turn requesting updated JSON
				if api_messages[-1]['role'] != 'user':
					api_messages.append({
						'role': 'user',
						'content': 'Please update the proposed changes list based on the conversation above and return valid JSON.'
					})
				else:
					api_messages[-1]['content'] += (
						'\n\nPlease update the changes list based on my feedback above and return valid JSON.'
					)
			else:
				api_messages = [{'role': 'user', 'content': initial_user_msg}]

			print(f'analyze-update: html={len(current_html)} chars, ir_blocks={len(word_doc_ir.get("blocks", []))}, chat_msgs={len(messages)}')

			try:
				if messages_create_with_retries is not None:
					response = messages_create_with_retries(
						client,
						model='claude-sonnet-4-20250514',
						max_tokens=4096,
						system=ANALYZE_SYSTEM_PROMPT,
						messages=api_messages,
						temperature=0,
					)
				else:
					response = client.messages.create(
						model='claude-sonnet-4-20250514',
						max_tokens=4096,
						system=ANALYZE_SYSTEM_PROMPT,
						messages=api_messages,
						temperature=0,
					)
			except Exception as api_err:
				print(f'Anthropic API error: {api_err}')
				traceback.print_exc()
				return self._send(500, {'error': f'AI error: {str(api_err)}'})

			raw = response.content[0].text.strip()

			# Strip markdown code fences if present
			if raw.startswith('```'):
				raw = raw.split('```', 2)[-1] if raw.count('```') >= 2 else raw
				raw = raw.replace('```json', '').replace('```', '').strip()

			try:
				result = json.loads(raw)
			except json.JSONDecodeError:
				# Try to extract JSON from the text
				import re
				json_match = re.search(r'\{[\s\S]*\}', raw)
				if json_match:
					try:
						result = json.loads(json_match.group())
					except Exception:
						result = {'summary': raw[:500], 'changes': [], 'reply': ''}
				else:
					result = {'summary': raw[:500], 'changes': [], 'reply': ''}

			changes = result.get('changes', [])
			summary = result.get('summary', '')
			reply   = result.get('reply', '')

			# Ensure each change has required fields
			for i, ch in enumerate(changes):
				ch.setdefault('id', i + 1)
				ch.setdefault('type', 'text')
				ch.setdefault('location', '')
				ch.setdefault('description', '')
				ch.setdefault('currentValue', '')
				ch.setdefault('newValue', '')

			return self._send(200, {
				'success': True,
				'changes': changes,
				'summary': summary,
				'reply':   reply,
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
