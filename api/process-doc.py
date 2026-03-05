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

try:
	from api.pii_scanner import scan_ir_for_pii, build_error_response, log_audit_event
except ImportError:
	try:
		from pii_scanner import scan_ir_for_pii, build_error_response, log_audit_event
	except ImportError:
		scan_ir_for_pii = None
		build_error_response = None
		log_audit_event = None


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
	import re
	from docx.oxml.ns import qn
	
	# Extract ALL runs including those inside hyperlinks
	# paragraph.runs misses hyperlink content because w:hyperlink wraps w:r elements
	p_element = paragraph._p
	
	for child in p_element.iterchildren():
		tag = child.tag.rsplit('}', 1)[-1]
		
		if tag == 'r':
			# Normal run
			_append_run_from_element(child, runs, paragraph)
		elif tag == 'hyperlink':
			# Hyperlink - extract runs inside it, mark as underline (it's a link)
			for sub_run in child.iterchildren():
				sub_tag = sub_run.tag.rsplit('}', 1)[-1]
				if sub_tag == 'r':
					_append_run_from_element(sub_run, runs, paragraph, is_hyperlink=True)
	
	return runs


def _append_run_from_element(r_element, runs, paragraph, is_hyperlink=False):
	"""Extract run data from a w:r XML element and append to runs list."""
	from docx.oxml.ns import qn
	
	# Get text from all w:t elements in this run
	text_parts = []
	for t_elem in r_element.iterchildren():
		t_tag = t_elem.tag.rsplit('}', 1)[-1]
		if t_tag == 't':
			text_parts.append(t_elem.text or '')
	
	text = ''.join(text_parts)
	if not text:
		return
	
	# Extract formatting from rPr (run properties)
	rPr = r_element.find(qn('w:rPr'))
	
	is_bold = False
	is_italic = False
	is_underline = is_hyperlink  # Hyperlinks are treated as underlined
	font_size_pt = None
	font_name = None
	
	if rPr is not None:
		# Bold: <w:b/> or <w:b w:val="true"/>
		b_elem = rPr.find(qn('w:b'))
		if b_elem is not None:
			val = b_elem.get(qn('w:val'))
			is_bold = val is None or val.lower() in ('true', '1', 'on')
		
		# Italic: <w:i/>
		i_elem = rPr.find(qn('w:i'))
		if i_elem is not None:
			val = i_elem.get(qn('w:val'))
			is_italic = val is None or val.lower() in ('true', '1', 'on')
		
		# Underline: <w:u w:val="single"/>
		u_elem = rPr.find(qn('w:u'))
		if u_elem is not None:
			val = u_elem.get(qn('w:val'))
			if val and val.lower() != 'none':
				is_underline = True
		
		# Font size: <w:sz w:val="22"/> (half-points)
		sz_elem = rPr.find(qn('w:sz'))
		if sz_elem is not None:
			try:
				half_pts = int(sz_elem.get(qn('w:val')))
				font_size_pt = half_pts / 2.0
			except (ValueError, TypeError):
				pass
		
		# Font name: <w:rFonts w:ascii="Arial"/>
		rFonts = rPr.find(qn('w:rFonts'))
		if rFonts is not None:
			font_name = rFonts.get(qn('w:ascii'))
	
	runs.append({
		'text': text,
		'bold': is_bold,
		'italic': is_italic,
		'underline': is_underline,
		'fontSizePt': font_size_pt,
		'fontFamily': font_name,
		'isHyperlink': is_hyperlink
	})


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
	# CRITICAL: Accept all tracked changes first
	# Documents with track changes have content in <w:ins> tags that python-docx doesn't read
	from docx.oxml.ns import qn
	
	# Remove all deletions and unwrap insertions
	for element in list(doc.element.body.iter()):
		if element.tag == qn('w:del'):
			element.getparent().remove(element)
		elif element.tag == qn('w:ins'):
			parent = element.getparent()
			index = list(parent).index(element)
			for child in list(element):
				parent.insert(index, child)
				index += 1
			parent.remove(element)
	
	# Save and reload to ensure python-docx re-parses
	temp_bytes = io.BytesIO()
	doc.save(temp_bytes)
	temp_bytes.seek(0)
	doc = Document(temp_bytes)
	
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
	
	# Extract text box content first (floating text boxes are not in body flow)
	# They appear as w:txbxContent inside drawing/shape elements
	text_box_blocks = []
	seen_textbox_texts = set()
	for txbx in doc.element.body.iter(qn('w:txbxContent')):
		rows = []
		for p_elem in txbx.iter(qn('w:p')):
			text = ''.join(t.text or '' for t in p_elem.iter(qn('w:t')))
			text = text.strip()
			if not text:
				continue
			# Deduplicate (Word sometimes duplicates text boxes for compatibility)
			if text in seen_textbox_texts:
				continue
			seen_textbox_texts.add(text)
			# Build a simple paragraph IR for each line in the text box
			runs = []
			for r_elem in p_elem.iter(qn('w:r')):
				t_text = ''.join(t.text or '' for t in r_elem.iter(qn('w:t')))
				if not t_text:
					continue
				rPr = r_elem.find(qn('w:rPr'))
				is_bold = False
				if rPr is not None:
					b = rPr.find(qn('w:b'))
					if b is not None:
						val = b.get(qn('w:val'))
						is_bold = val is None or val.lower() in ('true', '1', 'on')
				runs.append({'text': t_text, 'bold': is_bold, 'italic': False, 'underline': False, 'fontSizePt': None, 'fontFamily': None, 'isHyperlink': False})
			if runs:
				rows.append({
					'type': 'paragraph',
					'runs': runs,
					'align': 'left',
					'leadingSpaces': None,
					'styleName': None,
					'isListItem': False,
					'listLevel': None,
					'listMarker': None,
					'spacingBeforePt': None,
					'spacingAfterPt': None,
					'lineHeightMultiple': None,
					'leftIndentPt': None,
					'firstLineIndentPt': None,
					'hangingIndentPt': None
				})
		if rows:
			text_box_blocks.append({
				'type': 'textbox',
				'rows': rows
			})
	
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
			'headerTexts': header_texts,
			'textBoxes': text_box_blocks
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

			# PII early-gate: scan the IR before returning it to the client
			pii_scan = None
			if scan_ir_for_pii is not None:
				pii_scan = scan_ir_for_pii(ir)
				if pii_scan.has_pii or pii_scan.severity == 'BLOCKED':
					error_msg = build_error_response(pii_scan)
					if log_audit_event:
						log_audit_event('DOC_BLOCKED', file_name, pii_scan, error_msg[:120] if error_msg else '')
					return self._send(403, {
						'success': False,
						'error': error_msg or 'Document blocked by PII policy scanner.',
						'pii_scan': pii_scan.to_dict()
					})

			if log_audit_event:
				log_audit_event('DOC_PROCESSED', file_name, pii_scan, 'IR extraction successful')

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

