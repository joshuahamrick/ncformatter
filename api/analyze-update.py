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
	"""Convert an IR dict to a detailed text summary for comparison.
	Preserves blank lines, formatting markers, and table structure so
	the AI can detect spacing and content differences accurately."""
	if not ir or not isinstance(ir, dict):
		return '(no document content)'
	blocks = ir.get('blocks', [])
	lines = []
	for i, block in enumerate(blocks):
		btype = block.get('type', '')
		if btype == 'paragraph':
			runs = block.get('runs', [])
			text = ''.join(r.get('text', '') for r in runs).strip()

			if not text:
				# Preserve blank paragraphs — they represent spacing
				lines.append('[BLANK LINE]')
				continue

			# Collect formatting markers
			markers = []
			align = block.get('align', '')
			if align and align not in ('left', ''):
				markers.append(align.upper())

			# Run-level formatting
			all_bold      = all(r.get('bold')      for r in runs if r.get('text', '').strip())
			all_italic    = all(r.get('italic')    for r in runs if r.get('text', '').strip())
			all_underline = all(r.get('underline') for r in runs if r.get('text', '').strip())
			any_bold      = any(r.get('bold')      for r in runs if r.get('text', '').strip())
			if all_bold:      markers.append('BOLD')
			if all_italic:    markers.append('ITALIC')
			if all_underline: markers.append('UNDERLINE')
			elif any_bold:    markers.append('PARTIAL-BOLD')

			# Font size (first run that has one)
			for r in runs:
				sz = r.get('fontSize') or r.get('font_size')
				if sz:
					markers.append(f'{sz}pt')
					break

			prefix = f'[{", ".join(markers)}] ' if markers else ''
			lines.append(f'{prefix}{text}')

		elif btype == 'table':
			rows = block.get('rows', [])
			lines.append(f'[TABLE: {len(rows)} rows]')
			for row in rows[:20]:
				cells = row.get('cells', [])
				cell_texts = []
				for cell in cells:
					cell_paras = cell.get('paragraphs', [])
					cell_text = ' / '.join(
						''.join(r.get('text', '') for r in p.get('runs', [])).strip()
						for p in cell_paras
						if ''.join(r.get('text', '') for r in p.get('runs', [])).strip()
					).strip()
					cell_texts.append(cell_text or '(empty)')
				lines.append('  ROW: ' + ' | '.join(cell_texts))

		elif btype == 'textbox':
			tb_rows = block.get('rows', [])
			tb_text = ' '.join(
				''.join(r.get('text', '') for r in row.get('runs', [])).strip()
				for row in tb_rows
				if ''.join(r.get('text', '') for r in row.get('runs', [])).strip()
			)
			if tb_text:
				lines.append(f'[TEXTBOX] {tb_text}')

	return '\n'.join(lines) if lines else '(document appears empty)'


ANALYZE_SYSTEM_PROMPT = """You are an expert at comparing HTML mortgage letter templates with updated Word document sources.

Your job is to carefully read both documents and produce an accurate, complete list of every difference that needs to be applied to the HTML template.

CORE RULES:
1. Be THOROUGH — find every genuine difference between the two versions. Do not skip or dismiss changes.
2. Be LOCALIZED — each change entry should describe one specific, targeted edit. Do not bundle multiple changes into one.
3. Do NOT suggest changes to HTML syntax, tag structure, or NcFormatter variable placeholders ({[TAG]}, {[plsMatrix.*]}, {Compress(...)}, etc.) unless those tags themselves actually changed in the new document.
4. Do NOT suggest cosmetic reformatting of unchanged content.
5. DO flag: text wording changes, added/removed sentences or paragraphs, spacing changes (blank lines added or removed), table content changes, formatting changes (bold/italic added or removed).
6. The Word document shows [BLANK LINE] markers — compare these carefully against the HTML's <br> tags to find spacing differences.
7. When text contains NcFormatter placeholders, compare the surrounding literal text and the placeholder names — either may have changed.

CHANGE TYPES:
- "text" — a word, phrase, or sentence changed
- "spacing" — blank lines / <br> tags added or removed
- "addition" — new paragraph, sentence, or section added
- "removal" — existing paragraph, sentence, or section removed
- "formatting" — bold, italic, underline, alignment changed
- "structure" — section reordered or reorganized
- "tag" — an NcFormatter placeholder or helper function changed

RESPONSE FORMAT — always return valid JSON, nothing else:
{
  "summary": "One or two sentences describing the overall nature of the changes.",
  "changes": [
    {
      "id": 1,
      "type": "text",
      "location": "Where in the template (e.g. 'opening paragraph', 'RE table', 'closing sentence')",
      "description": "Clear description of what needs to change and why",
      "currentValue": "Exact current text from the HTML (≤150 chars)",
      "newValue": "New text it should become (≤150 chars)"
    }
  ],
  "reply": "Conversational response to the user — only include if replying to a chat message, otherwise leave empty string"
}

If the documents are genuinely identical, return an empty changes array and say so clearly in the summary."""


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
