"""
Strip embedded font binaries from .docx uploads.

Word's "Embed fonts in the file" option can inflate a 1-page letter to 5+ MB.
NcFormatter only needs text/structure for IR extraction; embedded fonts are unused
and can push base64 payloads past Vercel's ~4.5 MB request limit.
"""
from __future__ import annotations

import io
import re
import zipfile

_EMBED_TAG_RE = re.compile(
	r"<w:embed(?:Regular|Bold|Italic|BoldItalic)\b[^>]*/>",
	re.IGNORECASE,
)
_FONT_REL_RE = re.compile(
	r'<Relationship\b[^>]*\bTarget="fonts/[^"]*"[^>]*/>',
	re.IGNORECASE,
)
_ODTTF_CONTENT_TYPE_RE = re.compile(
	r'<Default\b[^>]*\bExtension="odttf"[^>]*/>',
	re.IGNORECASE,
)
_FONT_PART_PREFIXES = ("word/fonts/",)


def strip_embedded_docx_fonts(file_bytes: bytes) -> tuple[bytes, bool, int]:
	"""
	Return (docx_bytes, stripped, bytes_saved).

	If no embedded fonts are present, returns the original bytes unchanged.
	"""
	if not file_bytes:
		return file_bytes, False, 0

	font_entries: list[tuple[zipfile.ZipInfo, bytes]] = []
	other_entries: list[tuple[zipfile.ZipInfo, bytes]] = []

	with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zin:
		for item in zin.infolist():
			data = zin.read(item.filename)
			if item.filename.startswith(_FONT_PART_PREFIXES):
				font_entries.append((item, data))
			else:
				other_entries.append((item, data))

	if not font_entries:
		return file_bytes, False, 0

	saved = sum(len(data) for _, data in font_entries)
	out = io.BytesIO()
	with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
		for item, data in other_entries:
			name = item.filename
			if name == "word/fontTable.xml":
				data = _EMBED_TAG_RE.sub("", data.decode("utf-8")).encode("utf-8")
			elif name == "word/_rels/fontTable.xml.rels":
				text = _FONT_REL_RE.sub("", data.decode("utf-8"))
				if text.strip():
					data = text.encode("utf-8")
				else:
					continue
			elif name == "[Content_Types].xml":
				data = _ODTTF_CONTENT_TYPE_RE.sub("", data.decode("utf-8")).encode("utf-8")
			zout.writestr(item, data)

	return out.getvalue(), True, saved
