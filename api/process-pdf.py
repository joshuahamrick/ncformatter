from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import traceback

try:
	from pdfminer.high_level import extract_pages
	from pdfminer.layout import LTTextContainer, LTTextLine
	PDF_AVAILABLE = True
except Exception:
	PDF_AVAILABLE = False

try:
	from api.layout_raster import try_pdf_first_page_png
except ImportError:
	try:
		from layout_raster import try_pdf_first_page_png
	except ImportError:
		try_pdf_first_page_png = None


def _group_lines_to_paragraphs(lines):
	paragraphs = []
	buf = []
	for text in lines:
		if text.strip() == '':
			if buf:
				paragraphs.append(' '.join(buf))
				buf = []
		else:
			buf.append(text)
	if buf:
		paragraphs.append(' '.join(buf))
	return paragraphs


def _extract_ir_from_pdf(file_bytes):
	blocks = []
	try:
		fh = io.BytesIO(file_bytes)
		for page_layout in extract_pages(fh):
			# collect lines with approximate top y for ordering
			line_items = []
			for element in page_layout:
				if isinstance(element, LTTextContainer):
					for text_line in element:
						if isinstance(text_line, LTTextLine):
							s = text_line.get_text() or ''
							# normalize newlines out of line
							s = s.replace('\r', '').replace('\n', '')
							if s.strip():
								bbox = text_line.bbox  # (x0, y0, x1, y1)
								line_items.append((s, bbox[3]))
			# sort by y desc to preserve reading order
			line_items.sort(key=lambda t: (-t[1]))
			lines = [t[0] for t in line_items]
			paragraphs = _group_lines_to_paragraphs(lines)
			for p in paragraphs:
				run = {'text': p}
				para = {
					'type': 'paragraph',
					'runs': [run],
					'align': 'left',
					'leadingSpaces': None,
					'styleName': None,
					'isListItem': False,
					'listLevel': None,
					'listMarker': None,
					'spacingBeforePt': None,
					'spacingAfterPt': None,
					'lineHeightMultiple': None
				}
				blocks.append(para)
			# page break between pages
			blocks.append({'type': 'pageBreak'})
		# remove trailing pageBreak if exists
		if blocks and blocks[-1].get('type') == 'pageBreak':
			blocks.pop()
	except Exception as e:
		raise
	return {
		'blocks': blocks,
		'source': 'pdf',
		'confidence': 0.75,
		'images': []
	}


class handler(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			content_length = int(self.headers.get('Content-Length', '0'))
			post_data = self.rfile.read(content_length)
			data = json.loads(post_data.decode('utf-8') or '{}')
			file_data = data.get('fileData')
			file_name = data.get('fileName', 'document.pdf')
			if not file_data:
				return self._send(400, {'success': False, 'error': 'No file data provided'})
			if not PDF_AVAILABLE:
				return self._send(500, {'success': False, 'error': 'pdfminer.six library not available'})
			file_bytes = base64.b64decode(file_data)
			ir = _extract_ir_from_pdf(file_bytes)
			payload = {'success': True, 'fileName': file_name, 'ir': ir}

			# Optional layout reference: file is already PDF — no LibreOffice needed.
			# IR from pdfminer is plain text (no bold/tables); PNG helps Claude match layout.
			if data.get('includeLayoutPdf'):
				payload['layoutPdfBase64'] = base64.b64encode(file_bytes).decode('ascii')
				payload['layoutPdfMime'] = 'application/pdf'
				if try_pdf_first_page_png is not None:
					png_bytes, png_err = try_pdf_first_page_png(file_bytes)
					if png_bytes is not None:
						payload['layoutPngBase64'] = base64.b64encode(png_bytes).decode('ascii')
					elif png_err:
						payload['layoutPngError'] = png_err
				else:
					payload['layoutPngError'] = 'layout raster not available'

			return self._send(200, payload)
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

