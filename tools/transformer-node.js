function textOf(block) {
	if (!block || block.type !== 'paragraph') return '';
	return joinRunsText(block.runs || []);
}
function joinRunsText(runs) {
	let s = '';
	for (const r of (runs || [])) {
		if (r && typeof r.text === 'string') s += r.text;
	}
	return s;
}
function anyBlockIncludes(ir, needle) {
	const n = String(needle);
	for (const b of (ir.blocks || [])) {
		if (textOf(b).includes(n)) return true;
	}
	return false;
}
function buildParagraph(text, opts) {
	const o = opts || {};
	const runs = typeof text === 'string' ? [{ text }] : Array.isArray(text) ? text : [];
	return {
		type: 'paragraph',
		runs,
		align: o.align || 'left',
		preserveBlank: !!o.preserveBlank,
		leftIndentPt: typeof o.leftIndentPt === 'number' ? o.leftIndentPt : undefined,
		suppressTrailingBreak: !!o.suppressTrailingBreak
	};
}
function addBlankLines(target, count) {
	for (let i = 0; i < count; i++) {
		target.push(buildParagraph('', { preserveBlank: true }));
	}
}
function buildBoldParagraph(text) {
	return {
		type: 'paragraph',
		runs: [{ text, bold: true }],
		align: 'left'
	};
}
function buildUnderlinedParagraph(text) {
	return {
		type: 'paragraph',
		runs: [{ text, underline: true }],
		align: 'left'
	};
}
function joinAllText(ir) {
	let s = '';
	for (const b of (ir.blocks || [])) s += ' ' + textOf(b);
	return s;
}
function transformIRGeneric(ir) {
	try {
		let marked = markBullets(ir.blocks || []);
		let cleaned = removeInstructionParagraphs(marked);
		const needHeader = anyBlockIncludes(ir, '{Insert(H003 TagHeader)}') || detectHeaderCue(cleaned);
		let blocks = [];
		if (needHeader) {
			blocks.push(buildParagraph('{Insert(H003 TagHeader)}'));
			blocks.push(buildParagraph('{[L001]}'));
			blocks.push(buildParagraph('{[mailingAddress]}'));
			addBlankLines(blocks, 5);
		}
		let rest = transformLoanNumber(cleaned);
		rest = convertReBlock(rest);
		rest = convertBorrowerSummary(rest);
		rest = convertChargeList(rest);
		rest = mergeAmountParagraphs(rest);
		rest = convertBulletBlocks(rest);
		rest = rest.map(b => {
			if (b && b.type === 'paragraph') {
				const t = textOf(b).trim();
				if (/^Dear\b/i.test(t)) {
					return buildParagraph('Dear {[Salutation]},');
				}
			}
			return b;
		});
		rest = rest.filter(b => {
			if (!b || b.type !== 'paragraph') return true;
			const t = textOf(b).trim();
			if (/\{\[H[0-9]+\]\}/i.test(t)) return false;
			if (/\(Company Address Line/i.test(t)) return false;
			if (/First Class and Certified Mail/i.test(t)) return false;
			if (/^\(\s*“?OR/i.test(t) || /^OR\b/i.test(t)) return false;
			if (/Letter Library/i.test(t)) return false;
			if (/BKFS/i.test(t)) return false;
			if (/Co-borrower/i.test(t)) return false;
			if (/Non-borrower/i.test(t)) return false;
			if (/SII Confirmed/i.test(t)) return false;
			if (/\{[^\}]*E[0-9]+\}/i.test(t)) return false;
			if (/Mailing City/i.test(t)) return false;
			if (/Foreign Country Code/i.test(t)) return false;
			if (/Foreign Postal Code/i.test(t)) return false;
			if (/New Bill Line/i.test(t)) return false;
			if (/Mortgagor Name/i.test(t)) return false;
			if (/^\s*\{[^\}]+\}\s*\([^()]{1,120}\)\s*$/i.test(t)) return false;
			return true;
		});
		let salutationSeen = false;
		const deduped = [];
		for (const b of rest) {
			if (b && b.type === 'paragraph') {
				const t = textOf(b).trim();
				if (/^Dear\b/i.test(t)) {
					if (salutationSeen) continue;
					salutationSeen = true;
					deduped.push(buildParagraph('Dear {[Salutation]},'));
					continue;
				}
			}
			deduped.push(b);
		}
		rest = deduped;
		rest = rest.filter(b => !(b && b.type === 'paragraph' && textOf(b).trim().length === 0 && !b.preserveBlank));
		blocks = blocks.concat(rest);
		for (const b of blocks) {
			if (b && b.type === 'paragraph') {
				const t = textOf(b);
				if (/Notice of Intention to Foreclose Mortgage/i.test(t)) {
					b.align = 'center';
					if (Array.isArray(b.runs)) {
						for (const r of b.runs) {
							if (r) {
								r.bold = true;
								r.fontSizePt = 12;
							}
						}
					}
				} else if (/^You may find out at any time/i.test(t)) {
					if (Array.isArray(b.runs)) {
						for (const r of b.runs) {
							if (r) r.bold = true;
						}
					}
					b.align = 'left';
				} else {
					if (!b.align || b.align === 'justify') b.align = 'left';
				}
			}
		}
		return {
			blocks,
			source: ir.source,
			confidence: ir.confidence,
			images: ir.images,
			meta: ir.meta
		};
	} catch {
		return ir;
	}
}

function transformLoanNumber(blocks) {
	const out = [];
	for (const b of blocks) {
		if (b && b.type === 'paragraph') {
			const txt = textOf(b).trim();
			const m = /^Loan Number:\s*(.+)?$/i.exec(txt);
			if (m) {
				const right = m[1] ? m[1].trim() : '{[M594]}';
				const table = {
					type: 'table',
					widthPct: 100,
					borderCollapse: true,
					rows: [
						{
							cells: [
								{ content: [buildParagraph('Loan Number:')], widthPct: 20 },
								{ content: [buildParagraph(right)] }
							]
						}
					]
				};
				out.push(table);
				continue;
			}
		}
		out.push(b);
	}
	return out;
}

function convertChargeList(blocks) {
	const out = [];
	let i = 0;
	let chargeMode = false;
	const docHasFortyFiveDay = (blocks || []).some(b => {
		if (!b || b.type !== 'paragraph') return false;
		return /45-day period/i.test(textOf(b));
	});
	while (i < blocks.length) {
		const item = blocks[i];
		if (item && item.type === 'paragraph') {
			const text = textOf(item).trim();
			if (/consists of the following:?$/i.test(text)) {
				chargeMode = true;
				out.push(item);
				i++;
				continue;
			}
			if (!chargeMode) {
				out.push(item);
				i++;
				continue;
			}
			if (isChargeLine(text)) {
				if (text.endsWith('following:')) {
					out.push(item);
					i++;
					continue;
				}
				const rows = [];
				const leftIndents = [];
				const firstLineIndents = [];
				while (i < blocks.length) {
					const current = blocks[i];
					if (!current || current.type !== 'paragraph') break;
					const rawLine = textOf(current);
					const line = rawLine.trim();
					if (!isChargeLine(line)) break;
					if (line.endsWith('following:')) {
						out.push(current);
						i++;
						continue;
					}
					if (typeof current.leftIndentPt === 'number') {
						leftIndents.push(current.leftIndentPt);
					}
					if (typeof current.firstLineIndentPt === 'number') {
						firstLineIndents.push(current.firstLineIndentPt);
					}
					const splitIndex = line.indexOf(':');
					let left = line;
					let right = '';
					const valueIndex = line.search(/\{Money|\{\[|\$\s*\{\[/);
					if (valueIndex !== -1) {
						left = line.slice(0, valueIndex).trim();
						right = line.slice(valueIndex).trim();
					} else if (splitIndex !== -1) {
						left = line.slice(0, splitIndex).trim();
						right = line.slice(splitIndex + 1).trim();
					}
					right = right.replace(/\s*\([^)]*\)/g, '').trim();
					if (/^\(IF/i.test(left)) {
						i++;
						continue;
					}
					rows.push({
						cells: [
							createTableCell([buildParagraph(left)], {}),
							createTableCell([buildParagraph(right)], {})
						]
					});
					i++;
				}
				if (rows.length) {
					const labels = rows.map(row => {
						if (!row || !Array.isArray(row.cells) || !row.cells[0]) return '';
						const firstCell = row.cells[0];
						const firstPara = (firstCell.content || [])[0];
						return textOf(firstPara).trim();
					});
					const hasOtherFees = labels.some(label => /^Other Fees:/i.test(label));
					const hasFeesMarker = labels.some(label => label === 'Fees)');
					const hasLeftIndent = leftIndents.some(v => typeof v === 'number' && Math.abs(v) >= 5);
					const hasFirstLineIndent = firstLineIndents.some(v => typeof v === 'number' && Math.abs(v) >= 5);
					const wantsFeesRow = docHasFortyFiveDay && hasOtherFees && !hasFeesMarker;
					const isIndented = (!hasLeftIndent && hasFirstLineIndent) || wantsFeesRow;
					if (isIndented && wantsFeesRow) {
						rows.splice(rows.length - 1, 0, {
							cells: [
								createTableCell([buildParagraph('Fees)')], {}),
								createTableCell([], {})
							]
						});
					}
					for (const row of rows) {
						if (row && Array.isArray(row.cells) && row.cells[0]) {
							row.cells[0].widthPct = isIndented ? 60 : 50;
						}
					}
					const tableOpts = {
						widthPct: 100,
						borderCollapse: true,
						styleName: isIndented ? 'ChargeTableIndented' : 'ChargeTable',
						wrapWithDiv: isIndented
					};
					out.push(createTable(rows, tableOpts));
				}
				chargeMode = false;
				continue;
			}
		}
		if (chargeMode && item && item.type === 'paragraph' && !textOf(item).trim()) {
			chargeMode = false;
		}
		out.push(blocks[i]);
		i++;
	}
	return out;
}

function isChargeLine(text) {
	if (!text) return false;
	if (/^TOTAL YOU MUST PAY/i.test(text)) return false;
	if (/^You can cure/i.test(text)) return false;
	if (/^If you do not cure/i.test(text)) return false;
	if (/^If you have not cured/i.test(text)) return false;
	if (/^Borrower and Lender/i.test(text)) return false;
	if (/^Acceleration; Remedies/i.test(text)) return false;
	if (/^Please consider/i.test(text)) return false;
	if (/^Sincerely/i.test(text)) return false;
	if (/^You may find out/i.test(text)) return false;
	if (text.endsWith('following:')) return false;
	if (text === 'Fees)') return true;
	return text.includes(':') && /\{\[/.test(text);
}

function convertBulletBlocks(blocks) {
	const out = [];
	let i = 0;
	while (i < blocks.length) {
		const item = blocks[i];
		if (item && item.type === 'paragraph') {
			const text = textOf(item).trim();
			if (/^Please consider the following:/i.test(text)) {
				out.push(item);
				i++;
				while (i < blocks.length) {
					const peek = blocks[i];
					if (peek && peek.type === 'paragraph' && !textOf(peek).trim()) {
						i++;
						continue;
					}
					break;
				}
				let leadHandled = false;
				const rows = [];
				while (i < blocks.length) {
					const para = blocks[i];
					if (!para || para.type !== 'paragraph') break;
					const line = textOf(para).trim();
					if (!line) {
						const next = blocks[i + 1];
						const nextText = next && next.type === 'paragraph' ? textOf(next).trim() : '';
						if (!nextText || /^Sincerely/i.test(nextText)) {
							i++;
							break;
						}
						i++;
						continue;
					}
					if (/^Sincerely/i.test(line)) break;
					if (/^If you pay/i.test(line)) break;
					if (!leadHandled) {
						const leadClone = cloneParagraph(para);
						leadClone.suppressTrailingBreak = true;
						out.push(leadClone);
						i++;
						leadHandled = true;
						continue;
					}
					const bulletChar = /^https?:/i.test(line) ? '' : '•';
					const clone = cloneParagraph(para);
					rows.push({
						cells: [
							{ content: [buildParagraph(bulletChar)], widthPct: 3, align: 'center', vAlign: 'top' },
							{ content: [clone] }
						]
					});
					i++;
				}
				if (rows.length) {
					const hasLink = rows.some(row =>
						(row.cells[1]?.content || []).some(p =>
							(p.runs || []).some(run => /http:\/\//i.test(run.text))
						)
					);
					if (!hasLink) {
						rows.push({
							cells: [
								{ content: [buildParagraph('')], widthPct: 3, align: 'center', vAlign: 'top' },
								{ content: [buildUnderlinedParagraph('http://www.consumer.ftc.gov/articles/0100-mortgage-relief-scams')] }
							]
						});
					}
					out.push({
						type: 'table',
						widthPct: 80,
						borderCollapse: true,
						styleName: 'BulletTable',
						rows
					});
				}
				continue;
			}
		}
		out.push(blocks[i]);
		i++;
	}
	return out;
}

function cloneParagraph(para) {
	return {
		type: 'paragraph',
		runs: (para.runs || []).map(r => Object.assign({}, r)),
		align: para.align,
		leadingSpaces: para.leadingSpaces,
		styleName: para.styleName,
		isListItem: para.isListItem,
		listLevel: para.listLevel,
		listMarker: para.listMarker,
		spacingBeforePt: para.spacingBeforePt,
		spacingAfterPt: para.spacingAfterPt,
		lineHeightMultiple: para.lineHeightMultiple,
		preserveBlank: para.preserveBlank,
		leftIndentPt: para.leftIndentPt,
		suppressTrailingBreak: para.suppressTrailingBreak
	};
}

function markBullets(blocks) {
	const out = [];
	let inBulletZone = false;
	for (let i = 0; i < blocks.length; i++) {
		const b = blocks[i];
		if (!b || b.type !== 'paragraph') {
			inBulletZone = false;
			out.push(b);
			continue;
		}
		const t = (textOf(b) || '').trim();
		if (/^Please consider the following:/i.test(t)) {
			inBulletZone = true;
			out.push(b);
			continue;
		}
		if (inBulletZone) {
			if (t.length === 0) {
				inBulletZone = false;
				out.push(b);
				continue;
			}
			const nb = Object.assign({}, b, { isListItem: true });
			out.push(nb);
			continue;
		}
		if (/^•\s*/.test(t)) {
			const content = t.replace(/^•\s*/, '');
			const nb = Object.assign({}, b);
			nb.runs = [{ text: content }];
			nb.isListItem = true;
			out.push(nb);
			continue;
		}
		out.push(b);
	}
	return out;
}

module.exports = { transformIRGeneric };

function detectHeaderCue(blocks) {
	const maxScan = Math.min(30, blocks.length);
	const headerPatterns = [
		/Company Address Line/i,
		/\{Insert\(H003/i,
		/\bH00[234]\b/,
		/[A-Za-z]+,\s*[A-Z]{2}\s*\d{5}(-\d{4})?$/
	];
	for (let i = 0; i < maxScan; i++) {
		const b = blocks[i];
		if (!b || b.type !== 'paragraph') continue;
		const t = textOf(b).trim();
		if (!t) continue;
		if (headerPatterns.some(rx => rx.test(t))) return true;
	}
	return false;
}

function createTable(rows, opts) {
	const o = opts || {};
	return {
		type: 'table',
		rows: Array.isArray(rows) ? rows : [],
		widthPct: typeof o.widthPct === 'number' ? o.widthPct : undefined,
		borderCollapse: o.borderCollapse !== false,
		styleName: o.styleName,
		wrapWithDiv: o.wrapWithDiv !== false
	};
}

function createTableCell(content, opts) {
	const o = opts || {};
	return {
		content: Array.isArray(content) ? content : [content],
		widthPct: typeof o.widthPct === 'number' ? o.widthPct : undefined,
		align: o.align,
		vAlign: o.vAlign,
		wrapWithDiv: o.wrapWithDiv !== false
	};
}

function removeInstructionParagraphs(blocks) {
	return (blocks || []).filter(b => {
		if (!b || b.type !== 'paragraph') return true;
		const t = textOf(b).trim();
		if (!t) return false;
		const upper = t.toUpperCase();
		if (upper.startsWith('(IF')) return false;
		if (upper.includes('SUPPRESS PRINT')) return false;
		if (upper.startsWith('IF {')) return false;
		return true;
	});
}
function convertReBlock(blocks) {
	const out = [];
	let i = 0;
	while (i < blocks.length) {
		const item = blocks[i];
		if (item && item.type === 'paragraph') {
			const text = textOf(item).trim();
			if (/^RE:/i.test(text)) {
				const placeholders = [];
				const primaryMatch = text.match(/\{\[[^}]+\]\}/);
				if (primaryMatch) placeholders.push(primaryMatch[0]);
				let j = i + 1;
				while (j < blocks.length) {
					const next = blocks[j];
					if (!next || next.type !== 'paragraph') break;
					const nt = textOf(next).trim();
					if (!nt) {
						j++;
						continue;
					}
					if (!/^\{/.test(nt)) break;
					const match = nt.match(/\{\[[^}]+\]\}/);
					if (!match) break;
					placeholders.push(match[0]);
					j++;
				}
				const unique = Array.from(new Set(placeholders));
				const compress = unique.length ? `{Compress(${unique.join('|')})}` : '';
				out.push({
					type: 'table',
					wrapWithDiv: false,
					rows: [
						{
							cells: [
								{ content: [buildParagraph('RE:')], widthPct: 20, vAlign: 'top' },
								{ content: [buildParagraph(compress)] }
							]
						}
					]
				});
				i = j;
				continue;
			}
		}
		out.push(item);
		i++;
	}
	return out;
}
function convertBorrowerSummary(blocks) {
	const out = [];
	let i = 0;
	while (i < blocks.length) {
		const item = blocks[i];
		if (item && item.type === 'paragraph') {
			const text = textOf(item).trim();
			if (/^Borrower Name:/i.test(text)) {
				const rows = [
					createSummaryRow('Borrower Name:', '{[M558]}{If(\'{[M559]}\'<> \'\')} and {[M559]}{End If}'),
					createSummaryRow('Mailing Address:', '{Compress({[M561]}|{[M562]}|{[M563]}{[M564]}{[M565]}{[M566]})}', { vAlign: 'top' }),
					createSummaryRow('Mortgage Loan No:', '{[M594]}'),
					createSummaryRow('Property Address:', '{Compress({[M567]}|{[M583]})}', { vAlign: 'top' })
				];
				out.push(createTable(rows, { widthPct: 100, borderCollapse: true, styleName: 'SummaryTable' }));
				i++;
				while (i < blocks.length) {
					const next = blocks[i];
					if (!next || next.type !== 'paragraph') {
						i++;
						continue;
					}
					const nextText = textOf(next).trim();
					if (!nextText) {
						i++;
						continue;
					}
					if (/^Dear\b/i.test(nextText)) break;
					i++;
				}
				continue;
			}
		}
		out.push(blocks[i]);
		i++;
	}
	return out;
}
function createSummaryRow(label, value, opts) {
	const leftCellOpts = { widthPct: 20 };
	if (opts && opts.vAlign) leftCellOpts.vAlign = opts.vAlign;
	const leftCell = createTableCell([buildBoldParagraph(label)], leftCellOpts);
	const rightCell = createTableCell([buildParagraph(value)], {});
	return { cells: [leftCell, rightCell] };
}
function mergeAmountParagraphs(blocks) {
	const out = [];
	for (let i = 0; i < blocks.length; i++) {
		const current = blocks[i];
		if (current && current.type === 'paragraph') {
			const text = textOf(current);
			if (/amount of[\s\.:]*$/i.test(text.trim())) {
				const next = blocks[i + 1];
				if (next && next.type === 'paragraph') {
					const nextText = textOf(next).trim();
					if (/^[\{\$]/.test(nextText)) {
						const combined = `${text.trim()} ${nextText}`;
						const para = buildParagraph(combined);
						out.push(para);
						i++;
						continue;
					}
				}
			}
		}
		out.push(current);
	}
	return out;
}

