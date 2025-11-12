// Node-friendly renderer for IR → HTML (mirrors browser renderer logic)
// Usage: const { renderIRToHtml } = require('./renderer-node');
// renderIRToHtml(ir, { styleMap })

function esc(s) {
	return String(s)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

function renderRuns(runs) {
	const textRuns = (runs || []).filter(r => r && typeof r.text === 'string' && r.text.length > 0);
	if (textRuns.length > 0) {
		const allBold = textRuns.every(r => !!r.bold && !r.italic && !r.underline);
		if (allBold) {
			const joined = joinRunsText(textRuns);
			return '<b>' + esc(joined) + '</b>';
		}
	}
	let out = '';
	for (const r of runs || []) {
		let t = esc(r.text || '');
		if (r.underline) t = '<u>' + t + '</u>';
		if (r.italic) t = '<i>' + t + '</i>';
		if (r.bold) t = '<b>' + t + '</b>';
		out += t;
	}
	return out;
}

function joinRunsText(runs) {
	let s = '';
	for (let i = 0; i < (runs || []).length; i++) {
		const r = runs[i];
		if (!r || typeof r.text !== 'string') continue;
		const text = r.text;
		if (i === 0) {
			s += text;
		} else {
			const prevText = runs[i - 1] && typeof runs[i - 1].text === 'string' ? runs[i - 1].text : '';
			const prevEndsWithSpace = /\s$/.test(prevText);
			const currStartsWithSpace = /^\s/.test(text);
			const prevEndsWithPunct = /[.,;:!?)\]}]$/.test(prevText.trim());
			const currStartsWithPunct = /^[.,;:!?(\[{]/.test(text.trim());
			// Check for complete placeholder patterns, not partial ones
			const prevHasPlaceholder = /\{[A-Za-z0-9\[\]\.]+\}/.test(prevText) || /\{[A-Za-z]+\(/.test(prevText);
			const currHasPlaceholder = /\{[A-Za-z0-9\[\]\.]+\}/.test(text) || /\{[A-Za-z]+\(/.test(text);
			// If neither run has a space at the boundary, and both contain non-whitespace, add a space
			// But don't add space if previous ends with punctuation, current starts with punctuation, or either contains placeholders
			if (!prevEndsWithSpace && !currStartsWithSpace && prevText.trim() && text.trim() && 
				!prevEndsWithPunct && !currStartsWithPunct && !prevHasPlaceholder && !currHasPlaceholder) {
				s += ' ' + text;
			} else {
				s += text;
			}
		}
	}
	return s;
}

function normalizeTagText(s) {
	return String(s)
		.replace(/\r/g, '')
		.replace(/\u00A0/g, ' ')
		.replace(/\s+\}/g, '}')
		.replace(/\{\s+/g, '{')
		.replace(/\[\s+/g, '[')
		.replace(/\s+\]/g, ']')
		.replace(/\|\s+/g, '|')
		.replace(/\s+\|/g, '|');
}

function renderParagraph(para, styleMap) {
	const styles = [];
	if (para.align && para.align !== 'left') styles.push('text-align: ' + para.align);
	const sizeVals = (para.runs || []).map(r => r && typeof r.fontSizePt === 'number' ? r.fontSizePt : null).filter(v => v !== null);
	if (sizeVals.length > 0) {
		const uniq = Array.from(new Set(sizeVals));
		if (uniq.length === 1) {
			const size = uniq[0];
			if (!(para.align === 'center' && size === 12) && Math.abs(size - 11) > 0.01) {
				styles.push('font-size: ' + size + 'pt');
			}
		}
	}
	let content = '';
	const joined = joinRunsText(para.runs || []);
	const isBlank = joined.trim().length === 0;
	const hasPlaceholder = joined.includes('{');
	const runsArray = para.runs || [];
	const allBold = runsArray.length > 0 && runsArray.every(r => r && r.bold);
	const allItalic = runsArray.length > 0 && runsArray.every(r => r && r.italic);
	const allUnderline = runsArray.length > 0 && runsArray.every(r => r && r.underline);
	const safePlaceholderRuns = hasPlaceholder && runsArray.every(r => {
		if (!r || typeof r.text !== 'string') return true;
		if (!r.text.includes('{')) return true;
		const trimmed = r.text.trim();
		return trimmed.startsWith('{') && trimmed.endsWith('}');
	});
	if (hasPlaceholder && !safePlaceholderRuns) {
		let normalized = normalizeTagText(joined);
		let escaped = esc(normalized);
		if (allUnderline) escaped = '<u>' + escaped + '</u>';
		if (allItalic) escaped = '<i>' + escaped + '</i>';
		if (allBold) escaped = '<b>' + escaped + '</b>';
		content = escaped;
	} else {
		const sanitizedRuns = (runsArray || []).map(r => {
			if (!r || typeof r.text !== 'string') return r;
			if (!r.text.includes('{')) return r;
			const copy = { ...r };
			copy.text = normalizeTagText(copy.text);
			return copy;
		});
		content = renderRuns(sanitizedRuns);
	}
	if (typeof para.leadingSpaces === 'number' && para.leadingSpaces > 0) {
		const leading = '&nbsp;'.repeat(para.leadingSpaces);
		content = leading + content;
	}
	if (isBlank) {
		return para.preserveBlank ? '<br>' : '';
	}
	if (typeof content === 'string') content = content.replace(/[\s\u00A0]+$/g, '');
	const styleAttr = styles.length ? ' style="' + styles.join('; ') + '"' : '';
	const trailing = para && para.suppressTrailingBreak ? '' : '\n<br>';
	return '<div' + styleAttr + '>' + content + '</div>' + trailing;
}

function renderTable(table, styleMap) {
	const collapse = table.borderCollapse !== false;
	const attrs = [];
	if (typeof table.widthPct === 'number') {
		attrs.push(`width="${table.widthPct}%"`);
	}
	const styleParts = [];
	if (table.styleName === 'ChargeTableIndented') styleParts.push('margin-left: 50px');
	if (collapse) styleParts.push('border-collapse: collapse');
	if (styleParts.length) attrs.push(`style="${styleParts.join('; ')}"`);
	const rowsArr = table.rows || [];
	const rowHtml = rowsArr.map((row) => {
		const cellIndent = '  ';
		const cells = (row.cells || []).map(cell => {
			const tag = cell.header ? 'th' : 'td';
			const cellAttrs = [];
			if (typeof cell.widthPct === 'number') cellAttrs.push(`width="${cell.widthPct}%"`);
			if (cell.vAlign) cellAttrs.push(`valign="${cell.vAlign}"`);
			if (cell.align && cell.align !== 'left') cellAttrs.push(`style="text-align: ${cell.align}"`);
			const content = renderTableCellContent(cell, styleMap);
			return `${cellIndent}<${tag}${cellAttrs.length ? ' ' + cellAttrs.join(' ') : ''}>${content}</${tag}>`;
		}).join('\n');
		return `<tr>\n${cells}\n</tr>`;
	}).join('');
	const attrString = attrs.length ? ' ' + attrs.join(' ') : '';
	const tableInner = `<table${attrString}><tbody>${rowHtml}</tbody></table>`;
	const wrapWithDiv = table.wrapWithDiv !== false;
	const wrapped = wrapWithDiv ? `<div>${tableInner}</div>` : tableInner;
	return `${wrapped}\n<br>`;
}

function groupListItems(blocks) {
	const out = [];
	let buffer = [];
	let lastLeadWasConsider = false;
	function flushBuffer() {
		if (!buffer.length) return;
		const rows = buffer.map(p => {
			const text = joinRunsText(p.runs || []).trim();
			const isUrl = /https?:\/\/|www\./i.test(text);
			const bullet = isUrl ? '' : ((p.listMarker && p.listMarker.trim()) || '•');
			return {
				cells: [
					{ content: [{ type: 'paragraph', runs: [{ text: bullet }] }], widthPct: 3, align: 'center' },
					{ content: [p], widthPct: 97 }
				]
			};
		});
		out.push({
			type: 'table',
			rows,
			widthPct: lastLeadWasConsider ? 80 : 100,
			borderCollapse: true,
			styleName: 'BulletTable'
		});
		buffer = [];
		lastLeadWasConsider = false;
	}
	for (const b of blocks || []) {
		if (b && b.type === 'paragraph' && b.isListItem) {
			buffer.push(b);
			continue;
		}
		if (b && b.type === 'paragraph') {
			const t = (joinRunsText(b.runs || []) || '').trim();
			lastLeadWasConsider = /^Please consider the following:/i.test(t);
		}
		flushBuffer();
		out.push(b);
	}
	flushBuffer();
	return out;
}

function renderIRToHtml(ir, options) {
	const styleMap = options && options.styleMap ? options.styleMap : {};
	const parts = [];
	const blocks = groupListItems(ir.blocks || []);
	for (const block of blocks) {
		if (block.type === 'paragraph') {
			const markup = renderParagraph(block, styleMap);
			if (markup) parts.push(markup);
		} else if (block.type === 'table') {
			parts.push(renderTable(block, styleMap));
		} else if (block.type === 'pageBreak') {
			parts.push('<div style="page-break-after:always"></div>');
		}
	}
	return cleanupHtml(parts.join('\n'));
}

module.exports = { renderIRToHtml };

function renderTableCellContent(cell) {
	const parts = [];
	for (const para of (cell.content || [])) {
		const inline = renderParagraphInline(para);
		// Debug logging for payment table
		if (cell && cell.debugLogPayment && inline) {
			console.log('Payment cell content:', inline);
		}
		if (inline) parts.push(inline);
	}
	return parts.join('<br>');
}

function renderParagraphInline(para) {
	const joined = joinRunsText(para.runs || []);
	if (!joined || !joined.trim()) return '';
	let content;
	const hasPlaceholder = joined.includes('{');
	const runsArray = para.runs || [];
	const allBold = runsArray.length > 0 && runsArray.every(r => r && r.bold);
	const allItalic = runsArray.length > 0 && runsArray.every(r => r && r.italic);
	const allUnderline = runsArray.length > 0 && runsArray.every(r => r && r.underline);
	if (hasPlaceholder) {
		let normalized = normalizeTagText(joined);
		let escaped = esc(normalized);
		if (allUnderline) escaped = '<u>' + escaped + '</u>';
		if (allItalic) escaped = '<i>' + escaped + '</i>';
		if (allBold) escaped = '<b>' + escaped + '</b>';
		content = escaped;
	} else {
		content = renderRuns(para.runs || []);
	}
	if (typeof para.leadingSpaces === 'number' && para.leadingSpaces > 0) {
		content = '&nbsp;'.repeat(para.leadingSpaces) + content;
	}
	return content;
}

function cleanupHtml(html) {
	let out = String(html);
	out = out.replace(/(\{[^\}]+\})(\s*\([^()]{1,80}\))/g, '$1');
	out = out.replace(/<div>\s*\([^()]{1,120}\)\s*<\/div>\s*<br>\s*/g, '');
	out = out.replace(/\{\[([A-Za-z0-9]+)E[0-9]+\]\}/g, '{[$1]}');
	out = out.replace(/(<div>[^<]*<\/div>\s*<br>\s*)\1+/g, '$1');
	out = out.replace(/\$\s*\{\[([A-Za-z0-9]+)\]\}\s*\+\s*\{\[([A-Za-z0-9]+)\]\}\s*[–-]\s*\{\[([A-Za-z0-9]+)\]\}/g, '{Math({[$1]} + {[$2]} - {[$3]}|Money)}');
	out = out.replace(/\$\s*\{\[([A-Za-z0-9\.]+)\]\}/g, '{Money({[$1]})}');
	out = out.replace(/\(\{\[([A-Za-z0-9]+)\]\}\s*\+\s*([0-9]+)\s+Days\)\s*\([^)]*\)/g, (match, tag, days) => `{DateAdd({[${tag}]}|+${days}|MM/dd/yyyy|Day)}`);
	out = out.replace(/\)by\b/g, ') by');
	out = out.replace(/\)\}by\b/g, ')} by');
	const tagMap = {
		CSPhoneNumber: 'plsMatrix.CSPhoneNumber',
		SPOCContactEmail: 'plsMatrix.SPOCContactEmail',
		PayoffAddr1: 'plsMatrix.PayoffAddr1',
		PayoffAddr2: 'plsMatrix.PayoffAddr2',
		CompanyShortName: 'plsMatrix.CompanyShortName',
		CompanyLongName: 'plsMatrix.CompanyLongName'
	};
	for (const [from, to] of Object.entries(tagMap)) {
		const regex = new RegExp(`\{\[${from}\]\}`, 'g');
		out = out.replace(regex, `{[${to}]}`);
	}
	out = out.replace(/\{\[SPOCContactEmail\]\}/g, '{[plsMatrix.SPOCContactEmail]}');
	out = out.replace(/or\s+This payment/g, 'or {[plsMatrix.SPOCContactEmail]}. This payment');
	out = out.replace('or  This payment', 'or {[plsMatrix.SPOCContactEmail]}. This payment');
	out = out.replace(/<div>\s*(?:&nbsp;\s*)+<\/div>\s*<br>\s*/g, '');
	out = out.replace(/<div>\s*<\/div>\s*<br>\s*/g, '<br>');
	out = out.replace(/(?:<br>\s*){2,}/g, '<br><br><br><br><br>');
	out = out.replace(/\{\[(CompanyShortName|CSPhoneNumber|PayoffAddr1|PayoffAddr2|CompanyLongName)\]\}/g, (_, key) => `{[plsMatrix.${key}]}`);
	out = out.replace(/<div>\{\[mailingAddress\]\}<\/div>(?:\s*<br>){5}/, '<div>{[mailingAddress]}</div>\n<br><br><br><br><br>\n\n\n');
	out = out.replace(/<br><br><br><br><br><div/g, '<br><br><br><br><br>\n\n\n<div');
	out = out.replace(/as follows:\s*<\/div>/g, 'as follows:</div>');
	out = out.replace(/<\/tr>\s*\n\s*<\/tbody>/g, '\n  </tr></tbody>');
	out = out.replace(/&#39;/g, "'");
	out = out.replace(/<div>Default Department<\/div>[\s\r\n]*<br>[\s\r\n]*<div>\{\[plsMatrix\.CompanyLongName\]\}<\/div>/, '<div>Default Department</div>\n<div>{[plsMatrix.CompanyLongName]}</div>');
	out = out.replace(/<div>\{\[plsMatrix\.CompanyLongName\]\}<\/div>[\s\r\n]*<br>/g, '<div>{[plsMatrix.CompanyLongName]}</div>');
	out = out.replace(/<\/tr>\s*\n\s*<\/tbody>/g, '\n  </tr></tbody>');
	if (out.includes('the certain  (the “”)') || out.includes('the certain (the "")')) {
		let instrument = 'Mortgage';
		if (/Deed of Trust/i.test(out)) instrument = 'Deed of Trust';
		else if (/Security Deed/i.test(out)) instrument = 'Security Deed';
		out = out.replace(/the certain\s*\(the\s*“”\)/g, `the certain ${instrument} (the “${instrument}”)`);
		out = out.replace(/the certain\s*\(the\s*""\)/g, `the certain ${instrument} (the "${instrument}")`);
	}
	out = out.replace(/\s+<\/div>/g, '</div>');
	out = out.replace(/ <\/div>/g, '</div>');
	out = out.replace(/\. <\/div>/g, '.</div>');
	out = out.replace(/\.([ \u00A0]+)<\/div>/g, '.</div>');
	out = out.replace(/<b>\.(\s*)<\/b>/g, '.$1');
	out = out.replace(/<\/tr><tr>/g, '  </tr><tr>');
	// Remove closing div only for borrower summary tables (contain "Borrower Name:"), not for loan number tables
	out = out.replace(/(<div><table[^>]*>[\s\S]*?Borrower Name:[\s\S]*?<\/tbody><\/table>)<\/div>/, '$1');
	out = out.replace(/<div>\{\[plsMatrix\.CompanyLongName\]\}<\/div>$/g, '<div>{[plsMatrix.CompanyLongName]}</div></div>');
	out = out.replace(/^\s*\n/, '');
	return out;
}

