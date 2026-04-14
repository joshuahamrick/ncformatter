"""
Rasterize first page of a PDF to PNG for Claude vision (table/spacing reference).

Optional dependency: pypdfium2 + Pillow. If missing, callers get (None, reason).
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PNG = int(os.environ.get("LAYOUT_PNG_MAX_BYTES", "1500000"))
_MAX_EDGE = int(os.environ.get("LAYOUT_PNG_MAX_EDGE", "1400"))


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
