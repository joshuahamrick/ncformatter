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
			if all_bold:
				markers.append('BOLD')
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
	"""Extract readable line-by-line text from HTML."""
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
	"""Normalize a line for diffing."""
	if not line:
		return ''
	s = line.strip()
	s = re.sub(r'^\[[^\]]*\]\s*', '', s)
	s = re.sub(r'\([^)]{2,100}\)', '', s)
	s = re.sub(r'\{?\[[^\]]+\]\}?', '__TAG__', s)
	s = re.sub(r'#[A-Za-z][\w]*#', '__TAG__', s)
	s = re.sub(r'\{Font\([^)]+\)\}', '', s, flags=re.IGNORECASE)
	s = re.sub(r'\{Header\([^)]+\)\}', '', s, flags=re.IGNORECASE)
	s = re.sub(r'\{If\([^}]+\)\}', '__COND__', s, flags=re.IGNORECASE)
	s = re.sub(r'\{End If\}', '', s, flags=re.IGNORECASE)
	s = re.sub(r'\[BLANK LINE\]', '__BLANK__', s, flags=re.IGNORECASE)
	s = re.sub(r'&nbsp;', ' ', s, flags=re.IGNORECASE)
	s = re.sub(r'\s+', ' ', s).strip().lower()
	return s


def _truncate(val, limit=150):
	if not val:
		return ''
	val = str(val).replace('\n', ' ')
	return val if len(val) <= limit else val[: limit - 3] + '...'


def _diff_hint_lines(old_lines, new_lines, *, label):
	"""Return human-readable diff hint strings (not apply-able change objects)."""
	norm_old = [_normalize_compare_line(l) for l in old_lines]
	norm_new = [_normalize_compare_line(l) for l in new_lines]
	hints = []
	for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, norm_old, norm_new).get_opcodes():
		if tag == 'equal':
			continue
		if tag == 'replace':
			old_chunk = old_lines[i1:i2]
			new_chunk = new_lines[j1:j2]
			for idx in range(max(len(old_chunk), len(new_chunk))):
				old_val = old_chunk[idx] if idx < len(old_chunk) else ''
				new_val = new_chunk[idx] if idx < len(new_chunk) else ''
				if _normalize_compare_line(old_val) == _normalize_compare_line(new_val):
					continue
				if old_val and new_val:
					hints.append(f'{label}: "{_truncate(old_val, 90)}" → "{_truncate(new_val, 90)}"')
				elif new_val:
					hints.append(f'{label}: ADD "{_truncate(new_val, 90)}"')
				elif old_val:
					hints.append(f'{label}: REMOVE "{_truncate(old_val, 90)}"')
		elif tag == 'delete':
			for old_val in old_lines[i1:i2]:
				if old_val:
					hints.append(f'{label}: REMOVE "{_truncate(old_val, 90)}"')
		elif tag == 'insert':
			for new_val in new_lines[j1:j2]:
				if new_val:
					hints.append(f'{label}: ADD "{_truncate(new_val, 90)}"')
	return hints


def _build_diff_hints(old_word_ir, new_word_ir, current_html, new_preview_html):
	"""Build deterministic diff hints for the AI (descriptions only)."""
	sections = []
	total = 0

	if old_word_ir and new_word_ir:
		old_lines = _ir_to_text_summary(old_word_ir).split('\n')
		new_lines = _ir_to_text_summary(new_word_ir).split('\n')
		word_hints = _diff_hint_lines(old_lines, new_lines, label='Word source')
		if word_hints:
			sections.append(
				'SOURCE CHANGES (previous Word → new Word):\n'
				+ '\n'.join(f'  • {h}' for h in word_hints[:35])
				+ (f'\n  ... and {len(word_hints) - 35} more' if len(word_hints) > 35 else '')
			)
			total += len(word_hints)

	if new_preview_html and current_html:
		cur_lines = _html_to_text_summary(current_html).split('\n')
		prev_lines = _html_to_text_summary(new_preview_html).split('\n')
		html_hints = _diff_hint_lines(cur_lines, prev_lines, label='Confirmed HTML vs new preview')
		if html_hints:
			sections.append(
				'CONTENT DELTA (confirmed HTML → fresh format of new Word):\n'
				+ '\n'.join(f'  • {h}' for h in html_hints[:35])
				+ (f'\n  ... and {len(html_hints) - 35} more' if len(html_hints) > 35 else '')
			)
			total += len(html_hints)

	if not sections:
		sections.append('(no pre-computed content differences detected)')

	return '\n\n'.join(sections), total


def _filter_applicable_changes(changes, current_html):
	"""Keep only changes whose currentValue exists verbatim in the confirmed HTML."""
	if not current_html:
		return changes
	filtered = []
	dropped = 0
	for ch in changes:
		cv = (ch.get('currentValue') or '').strip()
		nv = (ch.get('newValue') or '').strip()
		typ = (ch.get('type') or 'text').lower()

		if typ == 'addition' and not cv and nv:
			filtered.append(ch)
			continue
		if typ == 'removal' and cv and cv in current_html:
			filtered.append(ch)
			continue
		if cv and cv in current_html:
			filtered.append(ch)
			continue
		if not cv and not nv:
			continue
		dropped += 1

	if dropped:
		print(f'analyze-update: dropped {dropped} change(s) with currentValue not found in HTML')
	return filtered


def _trim_for_context(text, max_chars=50000):
	if len(text) <= max_chars:
		return text
	head = int(max_chars * 0.6)
	tail = max_chars - head - 80
	return text[:head] + '\n\n... [middle truncated] ...\n\n' + text[-tail:]


ANALYZE_SYSTEM_PROMPT = """You are an expert at surgical version updates for NcFormatter HTML mortgage letter templates.

You receive THREE key inputs:
1. CONFIRMED HTML — production-approved template. This is what you EDIT. Preserve its structure, tags, helpers, and unchanged paragraphs exactly.
2. NEW FORMATTED PREVIEW — fresh HTML generated from the new Word document. This shows what the new letter CONTENT should say, but you must NOT replace the whole template with it.
3. DIFF HINTS — pre-computed line differences. Use these as your checklist.

YOUR JOB: Produce the smallest set of localized edits to CONFIRMED HTML so its content matches the NEW PREVIEW — but only where content actually changed. Keep confirmed formatting/structure for unchanged sections.

RULES:
1. Every change MUST have currentValue copied VERBATIM from CONFIRMED HTML (exact substring, ≤150 chars). If you cannot find an exact substring, skip that change or describe location more precisely.
2. newValue is the replacement substring in CONFIRMED HTML style (preserve {[tags]}, helpers, inline styles from the confirmed template).
3. IGNORE differences that are only formatting noise between confirmed HTML and new preview (extra <br>, font-size on wrapper divs, reordered attributes) when the literal text is unchanged.
4. When Word source diff hints are provided, prioritize changes that appear in BOTH Word diff and HTML-vs-preview diff.
5. Do NOT rewrite the whole document. Typical updates are 1–15 small edits.
6. Do NOT change {[TAG]} names unless the new preview uses a different tag for the same field.

CHANGE TYPES: text, spacing, addition, removal, formatting, structure, tag

Return valid JSON only:
{
  "summary": "...",
  "changes": [
    {
      "id": 1,
      "type": "text",
      "location": "section name",
      "description": "what changed",
      "currentValue": "exact substring from CONFIRMED HTML",
      "newValue": "replacement substring"
    }
  ],
  "reply": ""
}

Return empty changes ONLY if diff hints show no genuine content changes."""


class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', '0'))
			post_data = self.rfile.read(content_length)
			data = json.loads(post_data.decode('utf-8') or '{}')

			current_html = data.get('currentHtml', '')
			word_doc_ir = data.get('wordDocIR')
			old_word_doc_ir = data.get('oldWordDocIR')
			new_preview_html = data.get('newPreviewHtml', '')
			context_notes = data.get('contextNotes', '')
			messages = data.get('messages', [])
			current_changes = data.get('currentChanges', [])
			current_summary = data.get('currentSummary', '')

			if not current_html:
				return self._send(400, {'error': 'currentHtml is required'})
			if not word_doc_ir:
				return self._send(400, {'error': 'wordDocIR is required'})
			if not new_preview_html:
				return self._send(400, {
					'error': 'newPreviewHtml is required — generate a formatted preview from the new Word document first.'
				})

			if not ANTHROPIC_AVAILABLE:
				return self._send(500, {'error': 'Anthropic library not available'})

			api_key = os.environ.get('ANTHROPIC_API_KEY')
			if not api_key:
				return self._send(500, {'error': 'ANTHROPIC_API_KEY not set'})

			client = anthropic.Anthropic(api_key=api_key)

			diff_hints, hint_count = _build_diff_hints(
				old_word_doc_ir, word_doc_ir, current_html, new_preview_html
			)

			confirmed_preview = _trim_for_context(current_html)
			new_fmt_preview = _trim_for_context(new_preview_html)
			confirmed_text = _trim_for_context(_html_to_text_summary(current_html), 20000)
			new_fmt_text = _trim_for_context(_html_to_text_summary(new_preview_html), 20000)

			old_section = ''
			if old_word_doc_ir:
				old_section = f"""
=== PREVIOUS WORD (plain text) ===
{_trim_for_context(_ir_to_text_summary(old_word_doc_ir), 15000)}
"""

			initial_user_msg = f"""Surgically update the CONFIRMED HTML to incorporate content changes from the new Word document.

=== USER NOTES ===
{context_notes if context_notes else '(none)'}

=== PRE-COMPUTED DIFF HINTS ===
{diff_hints}

=== CONFIRMED HTML (EDIT THIS — production approved) ===
{confirmed_preview}

=== CONFIRMED HTML — plain text extract ===
{confirmed_text}

=== NEW FORMATTED PREVIEW (reference only — from new Word via formatter) ===
{new_fmt_preview}

=== NEW PREVIEW — plain text extract ===
{new_fmt_text}
{old_section}
TASK:
- Compare CONFIRMED HTML to NEW FORMATTED PREVIEW.
- Use diff hints as your checklist ({hint_count} hint(s)).
- Output surgical edits to CONFIRMED HTML only.
- Each currentValue MUST be copied verbatim from CONFIRMED HTML above."""

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
						'content': 'Update the changes list. Each currentValue must exist verbatim in CONFIRMED HTML. Return valid JSON.',
					})
				else:
					api_messages[-1]['content'] += (
						'\n\nUpdate the changes list. Each currentValue must exist verbatim in CONFIRMED HTML. Return valid JSON.'
					)
			else:
				api_messages = [{'role': 'user', 'content': initial_user_msg}]

			print(
				f'analyze-update: confirmed={len(current_html)} preview={len(new_preview_html)} '
				f'hints={hint_count} old_word={bool(old_word_doc_ir)} chat={len(messages)}'
			)

			try:
				if messages_create_with_retries is not None:
					response = messages_create_with_retries(
						client,
						model='claude-sonnet-4-6',
						max_tokens=8192,
						system=ANALYZE_SYSTEM_PROMPT,
						messages=api_messages,
						temperature=0,
					)
				else:
					response = client.messages.create(
						model='claude-sonnet-4-6',
						max_tokens=8192,
						system=ANALYZE_SYSTEM_PROMPT,
						messages=api_messages,
						extra_body={'temperature': 0},
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

			for i, ch in enumerate(changes):
				ch.setdefault('id', i + 1)
				ch.setdefault('type', 'text')
				ch.setdefault('location', '')
				ch.setdefault('description', '')
				ch.setdefault('currentValue', '')
				ch.setdefault('newValue', '')

			changes = _filter_applicable_changes(changes, current_html)

			if not changes and hint_count > 0 and not messages:
				summary = (
					f'Detected {hint_count} content difference(s) between your confirmed HTML and the '
					f'new formatted preview, but could not map them to exact HTML substrings automatically. '
					f'Use the chat below to point to specific passages (e.g. "update the paragraph about returned payments").'
				)

			return self._send(200, {
				'success': True,
				'changes': changes,
				'summary': summary,
				'reply': reply,
				'diffHintCount': hint_count,
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
