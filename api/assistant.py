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
		messages_create_with_retries = None  # type: ignore


def _read_file(paths):
	"""Try a list of paths and return the first one that works."""
	for path in paths:
		try:
			with open(path, 'r', encoding='utf-8') as f:
				return f.read()
		except Exception:
			pass
	return None


def load_knowledge_base():
	"""Load formatting rules and documentation for the assistant bot."""
	base_dir = os.path.dirname(os.path.abspath(__file__))
	root_dir = os.path.join(base_dir, '..')
	cwd = os.getcwd()

	parts = []

	# Formatting rules (system-prompt.txt)
	content = _read_file([
		os.path.join(root_dir, 'ai', 'prompts', 'system-prompt.txt'),
		os.path.join(cwd, 'ai', 'prompts', 'system-prompt.txt'),
		'ai/prompts/system-prompt.txt',
	])
	if content:
		parts.append("## FORMATTING RULES\n\n" + content)

	# Document formatting checklist
	content = _read_file([
		os.path.join(root_dir, 'DOCUMENT_FORMATTING_CHECKLIST.md'),
		os.path.join(cwd, 'DOCUMENT_FORMATTING_CHECKLIST.md'),
		'DOCUMENT_FORMATTING_CHECKLIST.md',
	])
	if content:
		parts.append("## DOCUMENT FORMATTING CHECKLIST\n\n" + content)

	# Pull in a few key formatted examples for reference
	example_files = [
		('LM155', 'formatter examples/LM155/LM155-formatted.html'),
		('LM250', 'formatter examples/LM250/LM250-formatted.html'),
		('ES027', 'formatter examples/ES027/ES027-ai-output.html'),
		('CA017', 'formatter examples/CA017/CA017-formatted.html'),
	]
	example_parts = []
	for label, rel_path in example_files:
		content = _read_file([
			os.path.join(root_dir, rel_path),
			os.path.join(cwd, rel_path),
			rel_path,
		])
		if content:
			example_parts.append(f"### {label}\n```html\n{content[:3000]}\n```")
	if example_parts:
		parts.append("## FORMATTED EXAMPLE REFERENCES\n\n" + "\n\n".join(example_parts))

	return "\n\n---\n\n".join(parts)


_KNOWLEDGE_BASE_CACHE = None


def get_knowledge_base():
	global _KNOWLEDGE_BASE_CACHE
	if _KNOWLEDGE_BASE_CACHE is None:
		_KNOWLEDGE_BASE_CACHE = load_knowledge_base()
	return _KNOWLEDGE_BASE_CACHE


def build_system_prompt():
	kb = get_knowledge_base()
	return f"""You are a helpful formatting assistant built into the NcFormatter mortgage document templating system. Programmers use you to ask questions about:

- Template functions: {{Symbol()}}, {{Money()}}, {{Date()}}, {{DateAdd()}}, {{DateDiff()}}, {{Compress()}}, {{Math()}}, {{Number()}}, {{Upper()}}, {{Lower()}}, {{Replace()}}, {{PadLeft()}}, {{IsNumber()}}, {{If()}}, {{Else If()}}, {{End If}}, etc.
- Variable syntax: {{[TAG]}}, plsMatrix. prefix, which variables need it
- Conditional logic: how to write {{If()}} blocks, date comparisons, NOT IN / IN patterns
- HTML structure: spacing, <br> rules, bold/italic nesting, table layouts, list patterns
- How to write specific sections: headers, RE tables, closing signatures, bullet lists
- What's wrong with a given block of template code

You have access to the complete formatting rules, the document formatting checklist, and several real formatted example letters for reference.

When answering:
- Be direct and concise
- Always show code in fenced code blocks
- When the user pastes template/HTML code and asks what's wrong, compare it carefully against the rules and call out each issue specifically
- Reference real examples by letter code when helpful (e.g. "same pattern as LM155")
- If a question is about a specific function, explain what it does and show the correct syntax with an example

{kb}"""


class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', 0))
			body = self.rfile.read(content_length)
			data = json.loads(body)

			messages = data.get('messages', [])
			if not messages:
				self._send_json(400, {'error': 'No messages provided'})
				return

			if not ANTHROPIC_AVAILABLE:
				self._send_json(500, {'error': 'Anthropic library not available on server'})
				return

			api_key = os.environ.get('ANTHROPIC_API_KEY')
			if not api_key:
				self._send_json(500, {'error': 'ANTHROPIC_API_KEY not configured'})
				return

			client = anthropic.Anthropic(api_key=api_key)
			system_prompt = build_system_prompt()

			if messages_create_with_retries:
				response = messages_create_with_retries(
					client,
					model='claude-sonnet-4-20250514',
					max_tokens=2048,
					system=system_prompt,
					messages=messages
				)
			else:
				response = client.messages.create(
					model='claude-sonnet-4-20250514',
					max_tokens=2048,
					system=system_prompt,
					messages=messages
				)

			reply = response.content[0].text
			self._send_json(200, {'reply': reply})

		except Exception as e:
			self._send_json(500, {'error': traceback.format_exc()})

	def do_OPTIONS(self):
		self.send_response(200)
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Headers', 'Content-Type')
		self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
		self.end_headers()

	def _send_json(self, code, payload):
		self.send_response(code)
		self.send_header('Content-type', 'application/json')
		self.send_header('Access-Control-Allow-Origin', '*')
		self.end_headers()
		self.wfile.write(json.dumps(payload).encode('utf-8'))

	def log_message(self, format, *args):
		pass
