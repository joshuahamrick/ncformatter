"""
Rasterize PDF pages to PNG for Claude vision (table/spacing reference).

Optional dependency: pypdfium2 + Pillow. If missing, callers get (None, reason).
"""
from __future__ import annotations

import io
import logging
import os
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PNG = int(os.environ.get("LAYOUT_PNG_MAX_BYTES", "1500000"))
_MAX_EDGE = int(os.environ.get("LAYOUT_PNG_MAX_EDGE", "1400"))
# Per-page max edge for multi-page rendering — smaller so all pages fit in token budget
_MULTIPAGE_MAX_EDGE = int(os.environ.get("LAYOUT_PNG_MULTIPAGE_EDGE", "900"))
_MULTIPAGE_MAX_PAGES = int(os.environ.get("LAYOUT_PNG_MAX_PAGES", "10"))


def try_pdf_first_page_png(
	pdf_bytes: bytes,
	*,
	max_png_bytes: Optional[int] = None,
) -> Tuple[Optional[bytes], Optional[str]]:
	"""Return (png_bytes, error). png_bytes is None when raster is skipped or fails."""
	max_b = max_png_bytes if max_png_bytes is not None else _DEFAULT_MAX_PNG
	if not pdf_bytes:
		return None, "empty pdf"
	try:
		import pypdfium2 as pdfium  # type: ignore
	except ImportError:
		return None, "pypdfium2 not installed"
	try:
		from PIL import Image  # type: ignore
	except ImportError:
		return None, "Pillow not installed"

	try:
		doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
		if len(doc) < 1:
			return None, "pdf has no pages"
		page = doc[0]
		scale = float(os.environ.get("LAYOUT_PNG_RENDER_SCALE", "1.75"))
		bitmap = page.render(scale=scale)
		pil_image = bitmap.to_pil()
		w, h = pil_image.size
		edge = max(w, h)
		if edge > _MAX_EDGE:
			r = _MAX_EDGE / float(edge)
			try:
				resample = Image.Resampling.LANCZOS
			except AttributeError:
				resample = Image.LANCZOS
			pil_image = pil_image.resize((int(w * r), int(h * r)), resample)
		buf = io.BytesIO()
		pil_image.save(buf, format="PNG", optimize=True)
		png = buf.getvalue()
		if len(png) > max_b:
			return None, f"png too large ({len(png)} bytes; max {max_b})"
		return png, None
	except Exception as e:
		logger.exception("pdf first page raster failed")
		return None, str(e)[:200]


def try_pdf_all_pages_png_list(
	pdf_bytes: bytes,
	*,
	max_pages: Optional[int] = None,
	max_edge: Optional[int] = None,
	max_bytes_per_page: int = 500000,
) -> Tuple[List[bytes], Optional[str]]:
	"""Render every page of a PDF to PNG and return a list of PNG bytes.

	Returns (png_list, error). png_list may be shorter than the document page
	count if some pages fail or exceed max_bytes_per_page; error is set when
	all pages fail.  Always call try_convert_docx_to_pdf first.
	"""
	mp = max_pages if max_pages is not None else _MULTIPAGE_MAX_PAGES
	me = max_edge if max_edge is not None else _MULTIPAGE_MAX_EDGE

	if not pdf_bytes:
		return [], "empty pdf"
	try:
		import pypdfium2 as pdfium  # type: ignore
	except ImportError:
		return [], "pypdfium2 not installed"
	try:
		from PIL import Image  # type: ignore
	except ImportError:
		return [], "Pillow not installed"

	results: List[bytes] = []
	last_err: Optional[str] = None
	try:
		doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
		n = min(len(doc), mp)
		if n < 1:
			return [], "pdf has no pages"
		scale = float(os.environ.get("LAYOUT_PNG_RENDER_SCALE", "1.5"))
		for i in range(n):
			try:
				page = doc[i]
				bitmap = page.render(scale=scale)
				pil_image = bitmap.to_pil()
				w, h = pil_image.size
				edge = max(w, h)
				if edge > me:
					r = me / float(edge)
					try:
						resample = Image.Resampling.LANCZOS
					except AttributeError:
						resample = Image.LANCZOS
					pil_image = pil_image.resize((int(w * r), int(h * r)), resample)
				buf = io.BytesIO()
				pil_image.save(buf, format="PNG", optimize=True)
				png = buf.getvalue()
				if len(png) <= max_bytes_per_page:
					results.append(png)
				else:
					last_err = f"page {i+1} png too large ({len(png)} bytes)"
			except Exception as page_err:
				last_err = f"page {i+1} render failed: {str(page_err)[:100]}"
	except Exception as e:
		logger.exception("pdf all-pages raster failed")
		return [], str(e)[:200]

	if not results:
		return [], last_err or "no pages rendered"
	return results, None
