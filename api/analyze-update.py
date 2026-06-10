from http.server import BaseHTTPRequestHandler
import difflib
import html as html_module
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


def _ir_to_text_summary(ir):
	"""Convert an IR dict to a detailed text summary for comparison."""
	if not ir or not isinstance(ir, dict):
		return '(no document content)'
	blocks = ir.get('blocks', [])
	lines = []
	for block in blocks:
		btype = block.get('type', '')
		if btype == 'paragraph':
			runs = block.get('runs', [])
			text = ''.join(r.get('text', '') for r in runs).strip()

			if not text:
				lines.append('[BLANK LINE]')
				continue

			markers = []
			align = block.get('align', '')
			if align and align not in ('left', ''):
				markers.append(align.upper())

			all_bold = all(r.get('bold') for r in runs if r.get('text', '').strip())
			all_italic = all(r.get('italic') for r in runs if r.get('text', '').strip())
			all_underline = all(r.get('underline') for r in runs if r.get('text', '').strip())
			any_bold = any(r.get('bold') for r in runs if r.get('text', '').strip())
			if all_bold:
				markers.append('BOLD')
			if all_italic:
				markers.append('ITALIC')
			if all_underline:
				markers.append('UNDERLINE')
			elif any_bold:
				markers.append('PARTIAL-BOLD')

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


def _html_to_text_summary(html):
	"""Extract readable line-by-line text from the confirmed HTML template."""
	if not html or not isinstance(html, str):
		return '(no html content)'

	text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.IGNORECASE | re.DOTALL)
	text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
	text = re.sub(r'<br\s*/?>', '\n[BLANK LINE]\n', text, flags=re.IGNORECASE)
	text = re.sub(r'</(?:div|p|li|tr|td|th|h[1-6])>', '\n', text, flags=re.IGNORECASE)
	text = re.sub(r'<[^>]+>', '', text)
	text = html_module.unescape(text)
	text = text.replace('\r\n', '\n').replace('\r', '\n')

	lines = []
	for raw in text.split('\n'):
		line = re.sub(r'\s+', ' ', raw).strip()
		if line:
			lines.append(line)
	return '\n'.join(lines) if lines else '(html appears empty)'


def _normalize_compare_line(line):
	"""Normalize a line for diffing — ignore dev comments and formatting noise."""
	if not line:
		return ''
	s = line.strip()
	s = re.sub(r'^\[[^\]]*\]\s*', '', s)
	s = re.sub(r'\([^)]{2,100}\)', '', s)
	s = re.sub(r'\{?\[[^\]]+\]\}?', '__TAG__', s)
	s = re.sub(r'#[A-Za-z][\w]*#', '__TAG__', s)
	s = re.sub(r'\{If\([^}]+\)\}', '__COND__', s, flags=re.IGNORECASE)
	s = re.sub(r'\{End If\}', '', s, flags=re.IGNORECASE)
	s = re.sub(r'\[BLANK LINE\]', '__BLANK__', s, flags=re.IGNORECASE)
	s = re.sub(r'\s+', ' ', s).strip().lower()
	return s


def _truncate(val, limit=150):
	if not val:
		return ''
	val = str(val).replace('\n', ' ')
	return val if len(val) <= limit else val[: limit - 3] + '...'


def _precompute_line_diff(old_lines, new_lines, *, source_label):
	"""Return candidate change dicts from a line-level diff."""
	norm_old = [_normalize_compare_line(l) for l in old_lines]
	norm_new = [_normalize_compare_line(l) for l in new_lines]

	changes = []
	cid = 1
	for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, norm_old, norm_new).get_opcodes():
		if tag == 'equal':
			continue

		if tag == 'replace':
			old_chunk = old_lines[i1:i2]
			new_chunk = new_lines[j1:j2]
			pairs = max(len(old_chunk), len(new_chunk))
			for idx in range(pairs):
				old_val = old_chunk[idx] if idx < len(old_chunk) else ''
				new_val = new_chunk[idx] if idx < len(new_chunk) else ''
				if not old_val and not new_val:
					continue
				if _normalize_compare_line(old_val) == _normalize_compare_line(new_val):
					continue
				changes.append({
					'id': cid,
					'type': 'text' if old_val and new_val else ('addition' if new_val else 'removal'),
					'location': f'{source_label} line {i1 + idx + 1}',
					'description': (
						f'Word source changed ({source_label}): '
						f'"{_truncate(old_val, 80)}" → "{_truncate(new_val, 80)}"'
					),
					'currentValue': _truncate(old_val),
					'newValue': _truncate(new_val),
					'_precomputed': True,
				})
				cid += 1

		elif tag == 'delete':
			for idx, old_val in enumerate(old_lines[i1:i2]):
				if not old_val:
					continue
				changes.append({
					'id': cid,
					'type': 'removal',
					'location': f'{source_label} line {i1 + idx + 1}',
					'description': f'Removed from {source_label}: "{_truncate(old_val, 80)}"',
					'currentValue': _truncate(old_val),
					'newValue': '',
					'_precomputed': True,
				})
				cid += 1

		elif tag == 'insert':
			for idx, new_val in enumerate(new_lines[j1:j2]):
				if not new_val:
					continue
				changes.append({
					'id': cid,
					'type': 'addition',
					'location': f'{source_label} line {j1 + idx + 1}',
					'description': f'Added in {source_label}: "{_truncate(new_val, 80)}"',
					'currentValue': '',
					'newValue': _truncate(new_val),
					'_precomputed': True,
				})
				cid += 1

	return changes


def _build_precomputed_diff(old_word_ir, new_word_ir, current_html):
	"""Build deterministic diff hints for the AI."""
	sections = []
	all_changes = []

	new_lines = _ir_to_text_summary(new_word_ir).split('\n')

	if old_word_ir:
		old_lines = _ir_to_text_summary(old_word_ir).split('\n')
		word_changes = _precompute_line_diff(old_lines, new_lines, source_label='previous Word → new Word')
		all_changes.extend(word_changes)
		if word_changes:
			lines = ['PRE-COMPUTED WORD DOCUMENT DIFF (previous → new):']
			for ch in word_changes[:40]:
				lines.append(
					f"  • [{ch['type']}] {ch['description']}"
				)
			if len(word_changes) > 40:
				lines.append(f'  ... and {len(word_changes) - 40} more')
			sections.append('\n'.join(lines))
		else:
			sections.append('PRE-COMPUTED WORD DOCUMENT DIFF: no line-level changes detected between previous and new Word files.')

	html_lines = _html_to_text_summary(current_html).split('\n')
	html_changes = _precompute_line_diff(html_lines, new_lines, source_label='confirmed HTML → new Word')
	# Only add HTML→Word hints when no old Word doc (old Word diff is more reliable)
	if not old_word_ir and html_changes:
		all_changes.extend(html_changes)
		lines = ['PRE-COMPUTED HTML vs NEW WORD DIFF:']
		for ch in html_changes[:30]:
			lines.append(f"  • [{ch['type']}] {ch['description']}")
		if len(html_changes) > 30:
			lines.append(f'  ... and {len(html_changes) - 30} more')
		sections.append('\n'.join(lines))

	return '\n\n'.join(sections), all_changes


def _trim_for_context(text, max_chars=50000):
	if len(text) <= max_chars:
		return text
	head = int(max_chars * 0.65)
	tail = max_chars - head - 80
	return text[:head] + '\n\n... [middle truncated] ...\n\n' + text[-tail:]


ANALYZE_SYSTEM_PROMPT = """You are an expert at surgical version updates for NcFormatter HTML mortgage letter templates.

WORKFLOW:
1. The CONFIRMED HTML TEMPLATE is production-approved — preserve its structure, formatting, tags, and variable placeholders.
2. The NEW WORD DOCUMENT is the client's updated source — your job is to find what changed and map those changes onto the HTML.
3. When a PREVIOUS WORD DOCUMENT is provided, treat the pre-computed diff (previous → new Word) as the PRIMARY source of truth for what changed.
4. You are NOT reformatting the letter from scratch. Apply only the delta.

CORE RULES:
1. Be THOROUGH — include every genuine content change. Never return an empty changes list if the pre-computed diff section lists changes.
2. Be SURGICAL — each change is one localized HTML edit. Never suggest rewriting the whole template.
3. IGNORE differences that are only representation noise:
   - Word dev comments in parentheses like "(Mortgagor Name)" when HTML already has {[M558]} or similar
   - HTML <div>/<br> structure vs Word [BLANK LINE] markers when spacing is equivalent
   - Formatting marker prefixes like [BOLD] in Word extract vs <b> tags in HTML
4. DO flag: wording changes, added/removed sentences or paragraphs, spacing changes, table cell content changes, new/renamed placeholders, conditional block changes.
5. For each change, currentValue must be an exact substring that exists in the HTML template (≤150 chars). newValue is what that substring should become.
6. If pre-computed diff shows a Word-only change, locate the matching passage in the HTML and propose the minimal HTML edit.

CHANGE TYPES: text, spacing, addition, removal, formatting, structure, tag

RESPONSE FORMAT — valid JSON only:
{
  "summary": "Brief summary of changes",
  "changes": [
    {
      "id": 1,
      "type": "text",
      "location": "section in template",
      "description": "what and why",
      "currentValue": "exact HTML substring",
      "newValue": "replacement substring"
    }
  ],
  "reply": ""
}

Return empty changes ONLY if pre-computed diffs AND manual comparison show zero genuine content changes."""


class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', '0'))
			post_data = self.rfile.read(content_length)
			data = json.loads(post_data.decode('utf-8') or '{}')

			current_html = data.get('currentHtml', '')
			word_doc_ir = data.get('wordDocIR')
			old_word_doc_ir = data.get('oldWordDocIR')
			context_notes = data.get('contextNotes', '')
			messages = data.get('messages', [])
			current_changes = data.get('currentChanges', [])
			current_summary = data.get('currentSummary', '')

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

			new_doc_text = _ir_to_text_summary(word_doc_ir)
			old_doc_text = _ir_to_text_summary(old_word_doc_ir) if old_word_doc_ir else None
			html_text = _html_to_text_summary(current_html)
			precomputed_section, precomputed_changes = _build_precomputed_diff(
				old_word_doc_ir, word_doc_ir, current_html
			)

			html_preview = _trim_for_context(current_html)
			new_doc_preview = _trim_for_context(new_doc_text, 30000)
			html_text_preview = _trim_for_context(html_text, 25000)

			old_section = ''
			if old_doc_text:
				old_section = f"""
=== PREVIOUS WORD DOCUMENT (last approved client source) ===
{_trim_for_context(old_doc_text, 30000)}
"""

			initial_user_msg = f"""Update the CONFIRMED HTML TEMPLATE to incorporate changes from the NEW WORD DOCUMENT.

The HTML template is already approved in production. Make the smallest possible set of edits — do NOT rewrite or restructure the template.

=== CONTEXT / NOTES FROM USER ===
{context_notes if context_notes else '(none provided)'}

=== {precomputed_section or '(no pre-computed diff)'} ===

=== CONFIRMED HTML TEMPLATE (full source — apply edits here) ===
{html_preview}

=== HTML TEMPLATE — PLAIN TEXT EXTRACT (for locating passages) ===
{html_text_preview}
{old_section}
=== NEW WORD DOCUMENT (client's updated source) ===
{new_doc_preview}

TASK:
1. Use the pre-computed diff (if any) as your checklist of Word-level changes.
2. For each real change, find the matching location in the HTML template.
3. Output surgical, localized HTML edits only — preserve all unchanged content exactly."""

			if messages:
				prior_analysis = {
					'summary': current_summary,
					'changes': current_changes,
					'reply': '',
				}
				synthetic_assistant = (
					'Here is my initial analysis:\n\n'
					+ json.dumps(prior_analysis, indent=2, ensure_ascii=False)
				)
				api_messages = [
					{'role': 'user', 'content': initial_user_msg},
					{'role': 'assistant', 'content': synthetic_assistant},
				]
				for msg in messages:
					api_messages.append({'role': msg['role'], 'content': msg['content']})
				if api_messages[-1]['role'] != 'user':
					api_messages.append({
						'role': 'user',
						'content': 'Please update the proposed changes list based on the conversation above and return valid JSON.',
					})
				else:
					api_messages[-1]['content'] += (
						'\n\nPlease update the changes list based on my feedback above and return valid JSON.'
					)
			else:
				api_messages = [{'role': 'user', 'content': initial_user_msg}]

			has_old = bool(old_word_doc_ir)
			print(
				f'analyze-update: html={len(current_html)} chars, '
				f'new_ir_blocks={len(word_doc_ir.get("blocks", []))}, '
				f'old_word={has_old}, precomputed={len(precomputed_changes)}, '
				f'chat_msgs={len(messages)}'
			)

			try:
				if messages_create_with_retries is not None:
					response = messages_create_with_retries(
						client,
						model='claude-sonnet-4-20250514',
						max_tokens=8192,
						system=ANALYZE_SYSTEM_PROMPT,
						messages=api_messages,
						temperature=0,
					)
				else:
					response = client.messages.create(
						model='claude-sonnet-4-20250514',
						max_tokens=8192,
						system=ANALYZE_SYSTEM_PROMPT,
						messages=api_messages,
						temperature=0,
					)
			except Exception as api_err:
				print(f'Anthropic API error: {api_err}')
				traceback.print_exc()
				return self._send(500, {'error': f'AI error: {str(api_err)}'})

			raw = response.content[0].text.strip()

			if raw.startswith('```'):
				raw = raw.split('```', 2)[-1] if raw.count('```') >= 2 else raw
				raw = raw.replace('```json', '').replace('```', '').strip()

			try:
				result = json.loads(raw)
			except json.JSONDecodeError:
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
			reply = result.get('reply', '')

			# Fallback: if AI returned no changes but deterministic diff found some,
			# seed the response so the user can review and refine via chat.
			if not changes and precomputed_changes and not messages:
				changes = [
					{k: v for k, v in ch.items() if not k.startswith('_')}
					for ch in precomputed_changes[:25]
				]
				summary = (
					f'Found {len(precomputed_changes)} line-level change(s) between '
					f'{"previous and new Word documents" if has_old else "the HTML template and new Word document"}. '
					'Review each change and use chat to map them to exact HTML edits if needed.'
				)

			for i, ch in enumerate(changes):
				ch.setdefault('id', i + 1)
				ch.setdefault('type', 'text')
				ch.setdefault('location', '')
				ch.setdefault('description', '')
				ch.setdefault('currentValue', '')
				ch.setdefault('newValue', '')
				ch.pop('_precomputed', None)

			return self._send(200, {
				'success': True,
				'changes': changes,
				'summary': summary,
				'reply': reply,
				'precomputedChangeCount': len(precomputed_changes),
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
