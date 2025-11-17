from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import traceback

try:
	from docx import Document
	from docx.enum.text import WD_ALIGN_PARAGRAPH
	DOCX_AVAILABLE = True
except ImportError:
	DOCX_AVAILABLE = False


def _align_to_str(alignment):
	if alignment == WD_ALIGN_PARAGRAPH.CENTER:
		return 'center'
	if alignment == WD_ALIGN_PARAGRAPH.RIGHT:
		return 'right'
	if alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
		return 'justify'
	return 'left'


def _extract_runs(paragraph):
	runs = []
	for run in paragraph.runs:
		text = run.text or ''
		runs.append({
			'text': text,
			'bold': bool(run.bold),
			'italic': bool(run.italic),
			'underline': bool(run.underline),
			# font.size may be None
			'fontSizePt': float(run.font.size.pt) if getattr(run.font, 'size', None) and run.font.size is not None else None,
			'fontFamily': run.font.name if getattr(run.font, 'name', None) else None
		})
	return runs


def _detect_list_info(paragraph):
	"""
	Attempts to detect if a paragraph is part of a list and its level.
	python-docx does not expose numbering API directly; we inspect XML lightly.
	"""
	is_list = False
	level = None
	marker = None
	try:
		p = paragraph._p
		pPr = p.pPr
		if pPr is not None and pPr.numPr is not None:
			is_list = True
			# ilvl is the list indentation level
			if pPr.numPr.ilvl is not None:
				try:
					level = int(pPr.numPr.ilvl.val)
				except Exception:
					level = 0
			else:
				level = 0
			# We cannot know exact marker from Word reliably; leave None
			marker = None
	except Exception:
		pass
	return is_list, level, marker


def _extract_paragraph_ir(paragraph):
	runs = _extract_runs(paragraph)
	full_text = ''.join(r.get('text') or '' for r in runs)

	# leading spaces count
	leading_spaces = 0
	for ch in full_text:
		if ch == ' ':
			leading_spaces += 1
		else:
			break

	is_list, level, marker = _detect_list_info(paragraph)

	para_ir = {
		'type': 'paragraph',
		'runs': runs,
		'align': _align_to_str(paragraph.paragraph_format.alignment),
		'leadingSpaces': leading_spaces if leading_spaces > 0 else None,
		'styleName': paragraph.style.name if getattr(paragraph, 'style', None) else None,
		'isListItem': is_list,
		'listLevel': level,
		'listMarker': marker,
		'spacingBeforePt': float(paragraph.paragraph_format.space_before.pt) if paragraph.paragraph_format.space_before else None,
		'spacingAfterPt': float(paragraph.paragraph_format.space_after.pt) if paragraph.paragraph_format.space_after else None,
		'lineHeightMultiple': None,
		'leftIndentPt': float(paragraph.paragraph_format.left_indent.pt) if getattr(paragraph.paragraph_format, 'left_indent', None) else None,
		'firstLineIndentPt': float(paragraph.paragraph_format.first_line_indent.pt) if getattr(paragraph.paragraph_format, 'first_line_indent', None) else None,
		'hangingIndentPt': None
	}
	hanging = getattr(paragraph.paragraph_format, 'hanging_indent', None)
	if hanging is not None:
		try:
			para_ir['hangingIndentPt'] = float(getattr(hanging, 'pt', hanging))
		except Exception:
			para_ir['hangingIndentPt'] = None
	return para_ir


def _extract_table_ir(table):
	rows_ir = []
	for row in table.rows:
		cells_ir = []
		for cell in row.cells:
			# Each cell content: extract paragraphs as IRParagraphs
			content = []
			# Deduplicate paragraph references due to python-docx table cell structure
			seen = set()
			for para in cell.paragraphs:
				key = id(para)
				if key in seen:
					continue
				seen.add(key)
				content.append(_extract_paragraph_ir(para))
			cells_ir.append({
				'content': content,
				'widthPct': None,
				'align': None,
				'header': False
			})
		rows_ir.append({'cells': cells_ir})
	return {
		'type': 'table',
		'rows': rows_ir,
		'widthPct': 100,
		'borderCollapse': True,
		'styleName': None
	}


def _build_ir_document(doc):
	blocks = []
	# Extract headers first (for NMLID detection)
	# Headers are in doc.sections[].header (and first_page_header, even_page_header, etc.)
	header_texts = []
	try:
		for section in doc.sections:
			# Check all header types: default header, first page header, even page header
			headers_to_check = []
			if hasattr(section, 'header'):
				headers_to_check.append(section.header)
			if hasattr(section, 'first_page_header'):
				headers_to_check.append(section.first_page_header)
			if hasattr(section, 'even_page_header'):
				headers_to_check.append(section.even_page_header)
			
			for header in headers_to_check:
				try:
					for para in header.paragraphs:
						text = ''.join(run.text for run in para.runs if run.text)
						if text.strip():
							header_texts.append(text)
				except Exception:
					continue
	except Exception:
		pass  # Headers might not be accessible, continue without them
	
	# Iterate block items in document order: paragraphs and tables
	# python-docx doesn't provide a direct unified iterator; iterate through document._body
	for element in doc.element.body.iterchildren():
		tag = element.tag.rsplit('}', 1)[-1]
		if tag == 'p':
			# map to Paragraph object
			for para in doc.paragraphs:
				if para._p is element:
					blocks.append(_extract_paragraph_ir(para))
					break
		elif tag == 'tbl':
			for tbl in doc.tables:
				if tbl._tbl is element:
					blocks.append(_extract_table_ir(tbl))
					break
	# Images are not handled at this pass; can be added later if needed
	# Store header texts in meta for header detection
	return {
		'blocks': blocks,
		'source': 'docx',
		'confidence': 1.0,
		'images': [],
		'meta': {
			'headerTexts': header_texts
		}
	}


class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', '0'))
			post_data = self.rfile.read(content_length)

			data = json.loads(post_data.decode('utf-8') or '{}')
			file_data = data.get('fileData')
			file_name = data.get('fileName', 'document.docx')

			if not file_data:
				return self._send(400, {'success': False, 'error': 'No file data provided'})
			if not DOCX_AVAILABLE:
				return self._send(500, {'success': False, 'error': 'python-docx library not available'})

			file_bytes = base64.b64decode(file_data)
			doc = Document(io.BytesIO(file_bytes))

			ir = _build_ir_document(doc)
			return self._send(200, {'success': True, 'fileName': file_name, 'ir': ir})
		except Exception as e:
			err = {
				'success': False,
				'error': f'{str(e)}',
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

