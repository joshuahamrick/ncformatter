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

try:
	from api.docx_to_pdf import try_convert_docx_to_pdf
except ImportError:
	try:
		from docx_to_pdf import try_convert_docx_to_pdf
	except ImportError:
		try_convert_docx_to_pdf = None

try:
	from api.layout_raster import try_pdf_first_page_png
except ImportError:
	try:
		from layout_raster import try_pdf_first_page_png
	except ImportError:
		try_pdf_first_page_png = None


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

	# Detect paragraph border (bottom border = horizontal rule separator)
	para_border_bottom = None
	try:
		pPr_elem = paragraph._p.find(qn('w:pPr'))
		if pPr_elem is not None:
			pBdr = pPr_elem.find(qn('w:pBdr'))
			if pBdr is not None:
				bottom_el = pBdr.find(qn('w:bottom'))
				if bottom_el is not None:
					val = bottom_el.get(qn('w:val'), '')
					if val not in ('nil', 'none', ''):
						para_border_bottom = True
	except Exception:
		pass

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
		'hangingIndentPt': None,
		'borderBottom': para_border_bottom,
	}
	hanging = getattr(paragraph.paragraph_format, 'hanging_indent', None)
	if hanging is not None:
		try:
			para_ir['hangingIndentPt'] = float(getattr(hanging, 'pt', hanging))
		except Exception:
			para_ir['hangingIndentPt'] = None
	return para_ir


def _border_style(elem):
	"""Return a compact border descriptor string from a w:top/bottom/left/right element, or None."""
	if elem is None:
		return None
	val = elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') or ''
	sz  = elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sz') or ''
	color = elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}color') or ''
	if val in ('nil', 'none', ''):
		return 'none'
	parts = [val]
	if sz:
		try:
			parts.append(f'{int(sz)/8:.2g}pt')
		except Exception:
			parts.append(sz)
	if color and color.lower() not in ('auto', 'ffffff', ''):
		parts.append(f'#{color}')
	return ' '.join(parts)


def _table_border_summary(tblPr_elem):
	"""Summarise table-level border settings from w:tblPr XML element."""
	if tblPr_elem is None:
		return None
	ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	tblBorders = tblPr_elem.find(f'{{{ns}}}tblBorders')
	if tblBorders is None:
		return None
	sides = {}
	for side in ('top', 'bottom', 'left', 'right', 'insideH', 'insideV'):
		el = tblBorders.find(f'{{{ns}}}{side}')
		s = _border_style(el)
		if s:
			sides[side] = s
	if not sides:
		return None
	# Classify: all outer = 'box', all none = 'none', has inner = 'grid', else 'mixed'
	outer = {sides.get(k) for k in ('top','bottom','left','right')}
	inner = {sides.get(k) for k in ('insideH','insideV')}
	outer_vis = all(v and v != 'none' for v in [sides.get(k) for k in ('top','bottom','left','right') if sides.get(k)])
	inner_vis = any(v and v != 'none' for v in [sides.get('insideH'), sides.get('insideV')] if v)
	has_any = any(v and v != 'none' for v in sides.values())
	if not has_any:
		kind = 'none'
	elif outer_vis and inner_vis:
		kind = 'grid'
	elif outer_vis and not inner_vis:
		kind = 'box'
	elif not outer_vis and inner_vis:
		kind = 'inner-only'
	else:
		kind = 'mixed'
	return {'kind': kind, 'sides': sides}


def _cell_border_summary(tcPr_elem):
	"""Summarise cell-level border overrides from w:tcPr element."""
	if tcPr_elem is None:
		return None
	ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	tcBorders = tcPr_elem.find(f'{{{ns}}}tcBorders')
	if tcBorders is None:
		return None
	sides = {}
	for side in ('top', 'bottom', 'left', 'right'):
		el = tcBorders.find(f'{{{ns}}}{side}')
		s = _border_style(el)
		if s:
			sides[side] = s
	return sides if sides else None


def _tcw_pct(tcPr_elem, table_width_twips):
	"""Return approximate column width percentage from w:tcW, or None."""
	if tcPr_elem is None:
		return None
	ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	tcW = tcPr_elem.find(f'{{{ns}}}tcW')
	if tcW is None:
		return None
	w_type = tcW.get(f'{{{ns}}}type') or ''
	w_val = tcW.get(f'{{{ns}}}w') or ''
	try:
		val = int(w_val)
	except Exception:
		return None
	if w_type == 'pct':
		return round(val / 50, 1)  # 50ths of a percent
	if w_type in ('dxa', '') and table_width_twips and table_width_twips > 0:
		return round(val / table_width_twips * 100, 1)
	return None


def _table_width_twips(tblPr_elem):
	if tblPr_elem is None:
		return None
	ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	tblW = tblPr_elem.find(f'{{{ns}}}tblW')
	if tblW is None:
		return None
	try:
		return int(tblW.get(f'{{{ns}}}w') or '0') or None
	except Exception:
		return None


def _vmerge_info(tcPr_elem):
	"""Returns 'restart' (first merged cell), 'continue', or None."""
	if tcPr_elem is None:
		return None
	ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	vm = tcPr_elem.find(f'{{{ns}}}vMerge')
	if vm is None:
		return None
	val = vm.get(f'{{{ns}}}val') or ''
	return 'restart' if val == 'restart' else 'continue'


def _gridspan(tcPr_elem):
	"""Return column span (int >= 1)."""
	if tcPr_elem is None:
		return 1
	ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	gs = tcPr_elem.find(f'{{{ns}}}gridSpan')
	if gs is None:
		return 1
	try:
		return max(1, int(gs.get(f'{{{ns}}}val') or '1'))
	except Exception:
		return 1


def _cell_valign(tcPr_elem):
	if tcPr_elem is None:
		return None
	ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	vAlign = tcPr_elem.find(f'{{{ns}}}vAlign')
	if vAlign is None:
		return None
	v = vAlign.get(f'{{{ns}}}val') or ''
	return v if v in ('top', 'center', 'bottom') else None


def _extract_table_ir(table):
	ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	tblPr = table._tbl.find(f'{{{ns}}}tblPr')
	tbl_width = _table_width_twips(tblPr)
	tbl_borders = _table_border_summary(tblPr)
	tbl_style = None
	if tblPr is not None:
		ts = tblPr.find(f'{{{ns}}}tblStyle')
		if ts is not None:
			tbl_style = ts.get(f'{{{ns}}}val')

	rows_ir = []
	for row in table.rows:
		cells_ir = []
		# Build a deduplicated list of (cell_element, cell_object) pairs for this row
		seen_ids = set()
		row_cells = []
		for cell in row.cells:
			cid = id(cell._tc)
			if cid in seen_ids:
				continue
			seen_ids.add(cid)
			row_cells.append(cell)

		for cell in row_cells:
			tcPr = cell._tc.find(f'{{{ns}}}tcPr')
			content = []
			seen_para = set()
			for para in cell.paragraphs:
				key = id(para)
				if key in seen_para:
					continue
				seen_para.add(key)
				content.append(_extract_paragraph_ir(para))

			col_span = _gridspan(tcPr)
			vmerge = _vmerge_info(tcPr)
			cell_borders = _cell_border_summary(tcPr)
			valign = _cell_valign(tcPr)
			width_pct = _tcw_pct(tcPr, tbl_width)

			cell_ir = {
				'content': content,
				'widthPct': width_pct,
				'align': None,
				'vAlign': valign,
				'colSpan': col_span if col_span > 1 else None,
				'vMerge': vmerge,
				'header': False,
				'borders': cell_borders,
			}
			cells_ir.append(cell_ir)
		rows_ir.append({'cells': cells_ir})

	return {
		'type': 'table',
		'rows': rows_ir,
		'widthPct': 100,
		'borderCollapse': True,
		'styleName': tbl_style,
		'tableBorders': tbl_borders,
	}


def _wingdings_to_symbol(char, font_name):
	"""
	Map a Wingdings/Symbol private-use-area character to the {Symbol(X)} notation
	used by NcConnect templates.
	
	Word stores Wingdings characters in the Unicode private use area (U+F0xx).
	The actual character displayed depends on the font, but for NcConnect's
	{Symbol(X)} function, X is the Latin-1 equivalent (subtract 0xF000).
	"""
	if not char:
		return None
	c = char[0]
	code = ord(c)
	# Wingdings private use area: U+F000–U+F0FF maps to Latin-1 equivalent
	if 0xF000 <= code <= 0xF0FF:
		latin1_char = chr(code - 0xF000)
		return '{Symbol(' + latin1_char + ')}'
	# Already a standard symbol character
	standard_bullets = {'\u2022', '\u25cf', '\u25cb', '\u25a0', '\u25aa', '\u2013', '\u2014'}
	if c in standard_bullets:
		return '{Symbol(' + c + ')}'
	# Plain text marker (e.g. 'o', '-', '*')
	if c.isascii() and not c.isdigit():
		return c
	return None


def _resolve_list_types(doc, blocks):
	"""
	Resolve whether list items are bullet or numbered by reading numbering.xml.
	Also extracts the actual bullet character (e.g. {Symbol(ü)} for Wingdings ü)
	and stores it in listBulletChar on each block.
	"""
	import zipfile
	import re as _re

	# Characters that always mean 'bullet' regardless of numFmt
	bullet_chars = {'\uf0b7', '\u2022', '\u25cf', '\u25cb', '\u25a0', '\u25aa', '-', '\u2013', '\u2014'}

	try:
		numbering_xml = None
		temp = io.BytesIO()
		doc.save(temp)
		temp.seek(0)
		with zipfile.ZipFile(temp, 'r') as z:
			if 'word/numbering.xml' in z.namelist():
				with z.open('word/numbering.xml') as f:
					numbering_xml = f.read().decode('utf-8')

		if not numbering_xml:
			for b in blocks:
				if b.get('type') == 'paragraph' and b.get('isListItem'):
					b['listType'] = 'bullet'
			return

		num_to_abstract = {}
		for m in _re.finditer(
			r'<w:num\s+w:numId="(\d+)"[^>]*>.*?<w:abstractNumId\s+w:val="(\d+)"',
			numbering_xml, _re.DOTALL
		):
			num_to_abstract[m.group(1)] = m.group(2)

		# Per-abstractNum, per-level: store (fmt, lvlText, font)
		# Key: (abs_id, ilvl_str)  Value: dict with fmt/lvlText/font
		abstract_level_info = {}
		for m in _re.finditer(
			r'<w:abstractNum\s+w:abstractNumId="(\d+)"[^>]*>(.*?)</w:abstractNum>',
			numbering_xml, _re.DOTALL
		):
			abs_id = m.group(1)
			body = m.group(2)
			for lvl_m in _re.finditer(r'<w:lvl\s+w:ilvl="(\d+)"[^>]*>(.*?)</w:lvl>', body, _re.DOTALL):
				ilvl = lvl_m.group(1)
				lvl_body = lvl_m.group(2)

				fmt_m = _re.search(r'<w:numFmt\s+w:val="([^"]+)"', lvl_body)
				fmt = fmt_m.group(1) if fmt_m else ''

				txt_m = _re.search(r'<w:lvlText\s+w:val="([^"]*)"', lvl_body)
				lvl_text = txt_m.group(1) if txt_m else ''

				# Font override for the level (rFonts inside lvl/pPr or lvl/rPr)
				font_m = _re.search(r'<w:rFonts[^/]*/?>.*?(?=</w:)', lvl_body, _re.DOTALL)
				if not font_m:
					font_m = _re.search(r'<w:rFonts\s+[^>]+>', lvl_body)
				lvl_font = ''
				if font_m:
					fn_m = _re.search(r'w:ascii="([^"]+)"', font_m.group(0))
					if fn_m:
						lvl_font = fn_m.group(1)

				# If lvlText is a symbol character, override numFmt to 'bullet'
				if lvl_text and lvl_text[0] in bullet_chars:
					fmt = 'bullet'
				elif lvl_text and ord(lvl_text[0]) >= 0xF000:
					# Private-use-area (Wingdings/Symbol) → treat as bullet
					fmt = 'bullet'

				abstract_level_info[(abs_id, ilvl)] = {
					'fmt': fmt,
					'lvlText': lvl_text,
					'font': lvl_font,
				}

		# Re-scan doc paragraphs to map text → (numId, ilvl)
		from docx.oxml.ns import qn
		para_texts_to_numinfo = {}
		for para in doc.paragraphs:
			pPr = para._p.find(qn('w:pPr'))
			if pPr is not None:
				numPr = pPr.find(qn('w:numPr'))
				if numPr is not None:
					numId_elem = numPr.find(qn('w:numId'))
					ilvl_elem = numPr.find(qn('w:ilvl'))
					if numId_elem is not None:
						num_id = numId_elem.get(qn('w:val'), '')
						ilvl = ilvl_elem.get(qn('w:val'), '0') if ilvl_elem is not None else '0'
						text = ''.join(run.text for run in para.runs if run.text)
						para_texts_to_numinfo[text.strip()] = (num_id, ilvl)

		for b in blocks:
			if b.get('type') != 'paragraph' or not b.get('isListItem'):
				continue
			text = ''.join(r.get('text', '') for r in b.get('runs', [])).strip()
			num_id, ilvl = para_texts_to_numinfo.get(text, ('', '0'))
			info = None
			if num_id and num_id in num_to_abstract:
				abs_id = num_to_abstract[num_id]
				info = abstract_level_info.get((abs_id, ilvl))
				# Fall back to level 0 info if exact level not found
				if info is None:
					info = abstract_level_info.get((abs_id, '0'))

			if info:
				fmt = info['fmt']
				lvl_text = info['lvlText']
				lvl_font = info['font']

				if fmt == 'bullet' or fmt not in ('decimal', 'lowerLetter', 'upperLetter', 'lowerRoman', 'upperRoman'):
					b['listType'] = 'bullet'
				else:
					b['listType'] = 'numbered'

				# Determine the actual bullet character for the template
				bullet_char = _wingdings_to_symbol(lvl_text, lvl_font)
				if bullet_char:
					b['listBulletChar'] = bullet_char
			else:
				b['listType'] = 'bullet'
	except Exception:
		for b in blocks:
			if b.get('type') == 'paragraph' and b.get('isListItem'):
				b['listType'] = 'bullet'


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
	# Resolve list types (bullet vs numbered) from numbering definitions
	_resolve_list_types(doc, blocks)
	
	# Extract document-level default font and size
	# Check docDefaults first, then fall back to "Body Text" and "Normal" paragraph styles
	default_font = None
	default_font_size_pt = None
	try:
		styles_elem = doc.element.find(qn('w:styles'))
		if styles_elem is not None:
			# 1. Try docDefaults
			doc_defaults = styles_elem.find(qn('w:docDefaults'))
			if doc_defaults is not None:
				rPrDefault = doc_defaults.find('.//' + qn('w:rPrDefault'))
				if rPrDefault is not None:
					rPr = rPrDefault.find(qn('w:rPr'))
					if rPr is not None:
						rFonts = rPr.find(qn('w:rFonts'))
						if rFonts is not None:
							default_font = (
								rFonts.get(qn('w:ascii')) or
								rFonts.get(qn('w:hAnsi')) or
								rFonts.get(qn('w:cs'))
							)
						sz = rPr.find(qn('w:sz'))
						if sz is not None:
							val = sz.get(qn('w:val'))
							if val:
								try:
									default_font_size_pt = int(val) / 2
								except Exception:
									pass
			# 2. If docDefaults didn't give us font, check "Body Text" then "Normal" styles
			if not default_font:
				for style_name_check in ('Body Text', 'Normal'):
					for style_elem in styles_elem.findall(qn('w:style')):
						name_elem = style_elem.find(qn('w:name'))
						if name_elem is not None and name_elem.get(qn('w:val')) == style_name_check:
							rPr = style_elem.find('.//' + qn('w:rPr'))
							if rPr is not None:
								rFonts = rPr.find(qn('w:rFonts'))
								sz = rPr.find(qn('w:sz'))
								if rFonts is not None:
									f = (rFonts.get(qn('w:ascii')) or
										 rFonts.get(qn('w:hAnsi')) or
										 rFonts.get(qn('w:cs')))
									if f and f not in ('Times New Roman', 'Calibri'):
										default_font = f
								if sz is not None and not default_font_size_pt:
									val = sz.get(qn('w:val'))
									if val:
										try:
											default_font_size_pt = int(val) / 2
										except Exception:
											pass
							if default_font:
								break
					if default_font:
						break
	except Exception:
		pass

	# Store header texts in meta for header detection
	return {
		'blocks': blocks,
		'source': 'docx',
		'confidence': 1.0,
		'images': [],
		'meta': {
			'headerTexts': header_texts,
			'textBoxes': text_box_blocks,
			'defaultFont': default_font,
			'defaultFontSizePt': default_font_size_pt,
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

			payload = {'success': True, 'fileName': file_name, 'ir': ir}

			# Optional layout PDF (for browser screenshot / multimodal compare). Runs after PII gate.
			if data.get('includeLayoutPdf') and try_convert_docx_to_pdf is not None:
				pdf_bytes, pdf_err = try_convert_docx_to_pdf(file_bytes, file_name)
				if pdf_bytes is not None:
					payload['layoutPdfBase64'] = base64.b64encode(pdf_bytes).decode('ascii')
					payload['layoutPdfMime'] = 'application/pdf'
					if try_pdf_first_page_png is not None:
						png_bytes, png_err = try_pdf_first_page_png(pdf_bytes)
						if png_bytes is not None:
							payload['layoutPngBase64'] = base64.b64encode(png_bytes).decode('ascii')
						elif png_err:
							payload['layoutPngError'] = png_err
				else:
					payload['layoutPdfError'] = pdf_err or 'unknown conversion error'

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

