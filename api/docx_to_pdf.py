"""
Optional DOCX → PDF conversion for layout-accurate visual reference (tables, spacing).

Used when callers pass includeLayoutPdf=true on /api/process-doc.

Resolution order:
  - Windows: Microsoft Word (pywin32) first, then local LibreOffice soffice.
  - Linux/macOS: local LibreOffice soffice, then optional remote Gotenberg (LibreOffice in Docker).

Remote (print-accurate on Vercel): set GOTENBERG_URL to a running
  https://gotenberg.dev/ instance, e.g. https://your-gotenberg.fly.dev
  POST {GOTENBERG_URL}/forms/libreoffice/convert with multipart field "files".

Optional: SOFFICE_PATH, GOTENBERG_BASIC_AUTH (user:pass), GOTENBERG_BEARER_TOKEN.
"""
from __future__ import annotations

import base64
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

		errors: list[str] = []

		if os.name == "nt":
			err_w = _convert_via_word_com(docx_path, pdf_path)
			if pdf_path.is_file():
				pass
			elif err_w:
				errors.append(f"word: {err_w}")
				err_s = _convert_via_soffice(docx_path, pdf_path)
				if not pdf_path.is_file() and err_s:
					errors.append(f"soffice: {err_s}")
		else:
			err_s = _convert_via_soffice(docx_path, pdf_path)
			if not pdf_path.is_file() and err_s:
				errors.append(err_s)

		if not pdf_path.is_file():
			err_g = _convert_via_gotenberg(file_bytes, stem, pdf_path)
			if err_g is not None and err_g != "":
				errors.append(f"gotenberg: {err_g}")

		if not pdf_path.is_file():
			msg = "; ".join(errors) if errors else "conversion produced no pdf file"
			return None, msg

		pdf_bytes = pdf_path.read_bytes()
		if len(pdf_bytes) > max_b:
			return None, f"pdf too large for inline response ({len(pdf_bytes)} bytes; max {max_b})"

		return pdf_bytes, None


def _convert_via_gotenberg(file_bytes: bytes, stem: str, pdf_path: Path) -> str | None:
	"""
	POST the .docx to a Gotenberg service; write PDF to pdf_path on success.
	Returns None on success, "" if GOTENBERG_URL is not configured (skip), else error message.
	"""
	base = (os.environ.get("GOTENBERG_URL") or "").strip().rstrip("/")
	if not base:
		return ""
	try:
		import requests
	except ImportError as e:
		return f"requests not installed ({e}); add requests to requirements.txt for GOTENBERG_URL"

	url = f"{base}/forms/libreoffice/convert"
	filename = f"{stem}.docx"
	files = {
		"files": (
			filename,
			file_bytes,
			"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		)
	}
	headers: dict[str, str] = {}
	ba = (os.environ.get("GOTENBERG_BASIC_AUTH") or "").strip()
	if ba:
		headers["Authorization"] = "Basic " + base64.b64encode(ba.encode("utf-8")).decode("ascii")
	token = (os.environ.get("GOTENBERG_BEARER_TOKEN") or "").strip()
	if token:
		headers["Authorization"] = f"Bearer {token}"
	timeout = int(os.environ.get("GOTENBERG_TIMEOUT_SEC", "120"))
	try:
		resp = requests.post(
			url,
			files=files,
			headers=headers or None,
			timeout=timeout,
		)
	except requests.RequestException as e:
		logger.exception("gotenberg request failed")
		return str(e)[:400]

	if resp.status_code != 200:
		body = (resp.text or "")[:500]
		return f"HTTP {resp.status_code}: {body}"

	data = resp.content
	if not data.startswith(b"%PDF"):
		return "response is not a PDF"

	pdf_path.write_bytes(data)
	return None


def _resolve_soffice_executable() -> str | None:
	explicit = os.environ.get("SOFFICE_PATH")
	if explicit and os.path.isfile(explicit):
		return explicit
	for cand in (shutil.which("soffice"), shutil.which("libreoffice")):
		if cand:
			return cand
	if os.name == "nt":
		program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
		program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
		for base in (program_files, program_files_x86):
			p = Path(base) / "LibreOffice" / "program" / "soffice.exe"
			if p.is_file():
				return str(p)
	return None


def _convert_via_soffice(docx_path: Path, pdf_path: Path) -> str | None:
	exe = _resolve_soffice_executable()
	if not exe:
		hint = ""
		if os.environ.get("VERCEL"):
			hint = (
				"Vercel has no bundled LibreOffice. For print-accurate .docx→PDF, deploy "
				"Gotenberg (Docker) and set env GOTENBERG_URL to its base URL (see .env.example). "
				"Alternatively upload a PDF exported from Word."
			)
		else:
			hint = (
				"Install LibreOffice, add soffice to PATH, or set SOFFICE_PATH. "
				"Or set GOTENBERG_URL to a remote Gotenberg instance."
			)
		return hint
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
