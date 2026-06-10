/**
 * Strip embedded font binaries from .docx before API upload.
 * Word "Embed fonts in the file" can inflate a 1-page letter past Vercel's
 * ~4.5 MB request limit; stripping client-side keeps uploads small.
 */
(function (global) {
	'use strict';

	const EMBED_TAG_RE = /<w:embed(?:Regular|Bold|Italic|BoldItalic)\b[^>]*\/>/gi;
	const FONT_REL_RE = /<Relationship\b[^>]*\bTarget="fonts\/[^"]*"[^>]*\/>/gi;
	const FONT_CONTENT_TYPE_RE = /<Default\b[^>]*\bExtension="(?:odttf|ttf)"[^>]*\/>/gi;
	const FONT_PREFIX = 'word/fonts/';

	function hasEmbeddedFonts(zip) {
		return Object.keys(zip.files).some((name) => name.startsWith(FONT_PREFIX));
	}

	async function prepare(arrayBuffer) {
		if (!arrayBuffer || !global.JSZip) {
			return { bytes: new Uint8Array(arrayBuffer || 0), stripped: false, bytesSaved: 0 };
		}

		const zip = await global.JSZip.loadAsync(arrayBuffer);
		if (!hasEmbeddedFonts(zip)) {
			return { bytes: new Uint8Array(arrayBuffer), stripped: false, bytesSaved: 0 };
		}

		let bytesSaved = 0;
		for (const name of Object.keys(zip.files)) {
			if (name.startsWith(FONT_PREFIX)) {
				const entry = zip.files[name];
				if (entry && !entry.dir) {
					bytesSaved += (await entry.async('uint8array')).length;
				}
				delete zip.files[name];
			}
		}

		const fontTable = zip.file('word/fontTable.xml');
		if (fontTable) {
			const text = await fontTable.async('string');
			zip.file('word/fontTable.xml', text.replace(EMBED_TAG_RE, ''));
		}

		const fontRels = zip.file('word/_rels/fontTable.xml.rels');
		if (fontRels) {
			const text = (await fontRels.async('string')).replace(FONT_REL_RE, '');
			if (text.trim()) {
				zip.file('word/_rels/fontTable.xml.rels', text);
			} else {
				delete zip.files['word/_rels/fontTable.xml.rels'];
			}
		}

		const contentTypes = zip.file('[Content_Types].xml');
		if (contentTypes) {
			const text = await contentTypes.async('string');
			zip.file('[Content_Types].xml', text.replace(FONT_CONTENT_TYPE_RE, ''));
		}

		const bytes = await zip.generateAsync({
			type: 'uint8array',
			compression: 'DEFLATE',
			compressionOptions: { level: 6 },
		});

		return { bytes, stripped: true, bytesSaved };
	}

	function toBase64(bytes) {
		const chunk = 0x8000;
		let binary = '';
		for (let i = 0; i < bytes.length; i += chunk) {
			binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
		}
		return btoa(binary);
	}

	global.NcStripDocxFonts = { prepare, toBase64 };
})(typeof window !== 'undefined' ? window : globalThis);
