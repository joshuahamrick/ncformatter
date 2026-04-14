"""
Optional DOCX → PDF conversion for layout-accurate visual reference (tables, spacing).

Used when callers pass includeLayoutPdf=true on /api/process-doc.

Resolution order:
  1) SOFFICE_PATH or PATH: LibreOffice / soffice --headless (Linux server, local dev)
  2) Windows: Microsoft Word via pywin32 if installed (best Word fidelity)

Set SOFFICE_PATH to the full path of soffice.exe on Windows if not on PATH.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PDF_BYTES = int(os.environ.get("LAYOUT_PDF_MAX_BYTES", "2000000"))


def try_convert_docx_to_pdf(
	file_bytes: bytes,
	original_name: str,
	*,
	max_pdf_bytes: int | None = None,
) -> tuple[bytes | None, str | None]:
	"""
	Returns (pdf_bytes, error_message). pdf_bytes is None on failure.
	error_message is None on success, human-readable otherwise.
	"""
	max_b = max_pdf_bytes if max_pdf_bytes is not None else _DEFAULT_MAX_PDF_BYTES
	if not file_bytes:
		return None, "empty docx"
	stem = Path(original_name or "document.docx").stem or "document"

	with tempfile.TemporaryDirectory(prefix="ncf-docx2pdf-") as tmp:
		tmpdir = Path(tmp)
		docx_path = tmpdir / f"{stem}.docx"
		docx_path.write_bytes(file_bytes)

		pdf_path = tmpdir / f"{stem}.pdf"

		err = _convert_via_soffice(docx_path, pdf_path)
		if err:
			err2 = _convert_via_word_com(docx_path, pdf_path)
			if err2:
				return None, f"soffice: {err}; word: {err2}"

		if not pdf_path.is_file():
			return None, "conversion produced no pdf file"

		pdf_bytes = pdf_path.read_bytes()
		if len(pdf_bytes) > max_b:
			return None, f"pdf too large for inline response ({len(pdf_bytes)} bytes; max {max_b})"

		return pdf_bytes, None


def _convert_via_soffice(docx_path: Path, pdf_path: Path) -> str | None:
	exe = os.environ.get("SOFFICE_PATH") or shutil.which("soffice") or shutil.which("libreoffice")
	if not exe:
		return "soffice/libreoffice not found (set SOFFICE_PATH or install LibreOffice)"
	outdir = str(docx_path.parent)
	try:
		proc = subprocess.run(
			[exe, "--headless", "--norestore", "--nolockcheck", "--convert-to", "pdf", "--outdir", outdir, str(docx_path)],
			capture_output=True,
			text=True,
			timeout=int(os.environ.get("SOFFICE_TIMEOUT_SEC", "120")),
			check=False,
		)
	except subprocess.TimeoutExpired:
		return "soffice timed out"
	except OSError as e:
		return f"soffice failed to start: {e}"
	if proc.returncode != 0:
		msg = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
		return f"soffice failed: {msg[:500]}"
	if not pdf_path.is_file():
		return "soffice exited 0 but pdf missing"
	return None


def _convert_via_word_com(docx_path: Path, pdf_path: Path) -> str | None:
	if os.name != "nt":
		return "word com only on windows"
	try:
		import win32com.client  # type: ignore
	except ImportError:
		return "pywin32 not installed"
	word = None
	try:
		word = win32com.client.Dispatch("Word.Application")
		word.Visible = False
		doc = word.Documents.Open(str(docx_path.resolve()), ReadOnly=True)
		try:
			# 17 = wdExportFormatPDF
			doc.ExportAsFixedFormat(str(pdf_path.resolve()), ExportFormat=17)
		finally:
			doc.Close(False)
	finally:
		if word is not None:
			word.Quit()
	if not pdf_path.is_file():
		return "word com produced no pdf"
	return None
