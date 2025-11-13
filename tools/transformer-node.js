function textOf(block) {
	if (!block || block.type !== 'paragraph') return '';
	return joinRunsText(block.runs || []);
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
			// Don't treat { or [ as punctuation - they're placeholder starts, we want spaces before them
			const currStartsWithPunct = /^[.,;:!?)]/.test(text.trim());
			const currStartsWithPlaceholder = /^\{/.test(text.trim());
			// Never add space if previous ends with { or [ or current starts with ] or } (placeholder boundaries)
			// Also check if previous contains { or [ without closing } (incomplete placeholder)
			const prevEndsWithPlaceholderStart = /[\{\[]$/.test(prevText);
			const prevHasIncompletePlaceholder = /[\{\[]/.test(prevText) && !/\}/.test(prevText);
			const currStartsWithPlaceholderEnd = /^[\]}]/.test(text);
			const currHasIncompletePlaceholder = /[\]}]/.test(text) && !/^\{/.test(text);
			// Don't add space if previous ends with } and current starts with punctuation (e.g., {Math(...)}.)
			const prevEndsWithPlaceholderClose = /\}$/.test(prevText.trim());
			// Check for complete placeholder patterns, not partial ones
			const prevHasPlaceholder = /\{[A-Za-z0-9\[\]\.]+\}/.test(prevText) || /\{[A-Za-z]+\(/.test(prevText);
			const currHasPlaceholder = /\{[A-Za-z0-9\[\]\.]+\}/.test(text) || /\{[A-Za-z]+\(/.test(text);
			// If neither run has a space at the boundary, and both contain non-whitespace, add a space
			// But don't add space if previous ends with punctuation, current starts with punctuation, or either contains placeholders
			// Also never add space at placeholder boundaries
			const currStartsWithPunctAfterPlaceholder = prevEndsWithPlaceholderClose && /^[.,;:!?]/.test(text.trim());
			// Add space before placeholders unless previous ends with punctuation or placeholder boundary
			const shouldAddSpaceBeforePlaceholder = currStartsWithPlaceholder && !prevEndsWithPunct && 
				!prevEndsWithPlaceholderStart && !prevHasIncompletePlaceholder;
			// Add space after punctuation when followed by a word (e.g., "{[L001]}, your" not "{[L001]},your")
			const prevIsJustPunct = /^[.,;:!?]+$/.test(prevText.trim());
			const currStartsWithWord = /^[a-zA-Z]/.test(text.trim());
			const shouldAddSpaceAfterPunct = prevIsJustPunct && currStartsWithWord;
			if (!prevEndsWithSpace && !currStartsWithSpace && prevText.trim() && text.trim() && 
				((!prevEndsWithPunct && !currStartsWithPunct && 
				!prevEndsWithPlaceholderStart && !currStartsWithPlaceholderEnd &&
				!prevHasIncompletePlaceholder && !currHasIncompletePlaceholder &&
				!currStartsWithPunctAfterPlaceholder) || shouldAddSpaceBeforePlaceholder || shouldAddSpaceAfterPunct)) {
				s += ' ' + text;
			} else {
				s += text;
			}
		}
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
		rest = stripPlaceholderAnnotations(rest);
		rest = normalizeAmountSummaryBlocks(rest);
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
			if (/^\(\s*"?OR/i.test(t) || /^OR\b/i.test(t)) return false;
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
			if (/^\s*(\{[^\}]+\}\s*)+$/i.test(t)) return false;
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
				} else if (/^Default Department$/i.test(t) || /\{\[.*CompanyLongName.*\]\}/i.test(t)) {
					b.suppressTrailingBreak = true;
					b.align = 'left';
				} else {
					if (!b.align || b.align === 'justify') b.align = 'left';
				}
			}
			trimParagraphTrailingWhitespace(b);
		}
		const hasCompanyLine = blocks.some(b => b && b.type === 'paragraph' && /CompanyLongName/i.test(textOf(b)));
		if (!hasCompanyLine) {
			const footerIdx = blocks.findIndex(b => b && b.type === 'paragraph' && /^Default Department$/i.test(textOf(b)));
			const companyPara = buildParagraph('{[plsMatrix.CompanyLongName]}');
			companyPara.suppressTrailingBreak = true;
			companyPara.align = 'left';
			if (footerIdx >= 0) {
				blocks.splice(footerIdx + 1, 0, companyPara);
			} else {
				blocks.push(companyPara);
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
					wrapWithDiv: true,
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
					const mentionsDays = findUpcomingDayReference(blocks, i);
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
					const wantsFeesRow = mentionsDays && hasOtherFees && !hasFeesMarker;
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
						leadClone.isListItem = false;
						leadClone.leftIndentPt = undefined;
						leadClone.firstLineIndentPt = undefined;
						leadClone.hangingIndentPt = undefined;
						leadClone.suppressTrailingBreak = true;
						out.push(leadClone);
						i++;
						leadHandled = true;
						continue;
					}
					const bulletChar = /^https?:/i.test(line) ? '' : '•';
					const clone = cloneParagraph(para);
					clone.isListItem = false;
					clone.leftIndentPt = undefined;
					clone.firstLineIndentPt = undefined;
					clone.hangingIndentPt = undefined;
					clone.suppressTrailingBreak = false;
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
						const lastRow = rows[rows.length - 1];
						const cell = lastRow && lastRow.cells ? lastRow.cells[1] : null;
						if (cell) {
							const paras = cell.content || (cell.content = []);
							let target = paras.length ? paras[paras.length - 1] : null;
							if (!target) {
								target = buildParagraph('');
								paras.push(target);
							}
							if (target.runs && target.runs.length) {
								const lastRun = target.runs[target.runs.length - 1];
								if (lastRun && typeof lastRun.text === 'string' && !/\s$/.test(lastRun.text)) {
									lastRun.text += ' ';
								}
							}
							target.runs = (target.runs || []).concat([{ text: 'http://www.consumer.ftc.gov/articles/0100-mortgage-relief-scams' }]);
						}
					}
					out.push(createTable(rows, { widthPct: 100, borderCollapse: true, styleName: 'BulletTable' }));
				}
				continue;
			}
		}
		out.push(blocks[i]);
		i++;
	}
	return out;
}
function findUpcomingDayReference(blocks, startIndex) {
	for (let idx = startIndex; idx < blocks.length && idx < startIndex + 6; idx++) {
		const candidate = blocks[idx];
		if (!candidate || candidate.type !== 'paragraph') break;
		const text = textOf(candidate).trim();
		if (!text) break;
		if (/^TOTAL/i.test(text)) break;
		if (mentionsDayCount(text)) return true;
	}
	return false;
}
function mentionsDayCount(text) {
	if (!text) return false;
	const spelled = '(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[-\\s](?:one|two|three|four|five|six|seven|eight|nine))?';
	const pattern = new RegExp(`(?:\\b\\d+\\b|\\(\\s*\\d+\\s*\\)|\\b${spelled}\\b)\\s*(?:day|days)`, 'i');
	return pattern.test(text);
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
					borderCollapse: true,
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
function cloneRun(run) {
	return Object.assign({}, run || {});
}

function trimRunsWhitespace(runs, opts) {
	const trimLeading = !opts || opts.leading !== false;
	const trimTrailing = !opts || opts.trailing !== false;
	const cloned = (runs || []).map(r => {
		const copy = cloneRun(r);
		copy.text = copy.text || '';
		return copy;
	});
	if (trimLeading) {
		for (let idx = 0; idx < cloned.length; idx++) {
			const current = cloned[idx];
			if (!current || !current.text) continue;
			const trimmed = current.text.replace(/^\s+/, '');
			current.text = trimmed;
			if (trimmed.length) break;
		}
	}
	if (trimTrailing) {
		for (let idx = cloned.length - 1; idx >= 0; idx--) {
			const current = cloned[idx];
			if (!current || !current.text) continue;
			const trimmed = current.text.replace(/\s+$/, '');
			current.text = trimmed;
			if (trimmed.length) break;
		}
	}
	return cloned.filter(r => r && typeof r.text === 'string');
}

function createParagraphFromRuns(runs, template) {
	const source = template || {};
	return {
		type: 'paragraph',
		runs: Array.isArray(runs) ? runs : [],
		align: source.align,
		leadingSpaces: 0,
		styleName: source.styleName,
		isListItem: false,
		listLevel: source.listLevel,
		listMarker: source.listMarker,
		spacingBeforePt: source.spacingBeforePt,
		spacingAfterPt: source.spacingAfterPt,
		lineHeightMultiple: source.lineHeightMultiple,
		leftIndentPt: source.leftIndentPt,
		firstLineIndentPt: source.firstLineIndentPt,
		hangingIndentPt: source.hangingIndentPt
	};
}

function makeRunsBold(runs) {
	return (runs || []).map(run => {
		const copy = cloneRun(run);
		copy.bold = true;
		return copy;
	});
}

function splitLabelValueRuns(para) {
	const runs = para && para.runs ? para.runs : [];
	const labelRuns = [];
	const valueRuns = [];
	let separatorFound = false;
	for (const run of runs) {
		const text = run && typeof run.text === 'string' ? run.text : '';
		if (!separatorFound) {
			const match = text.match(/[:\t]/);
			if (match) {
				const idx = match.index;
				const sep = match[0];
				const before = sep === ':' ? text.slice(0, idx + 1) : text.slice(0, idx);
				if (before) labelRuns.push(cloneRun({ ...run, text: before }));
				if (sep === '\t' && before && !/:$/.test(before.trim())) {
					labelRuns.push(cloneRun({ ...run, text: ':' }));
				}
				const after = text.slice(idx + 1);
				if (after) valueRuns.push(cloneRun({ ...run, text: after }));
				separatorFound = true;
				continue;
			}
			if (text) labelRuns.push(cloneRun(run));
		} else if (text) {
			valueRuns.push(cloneRun(run));
		}
	}
	return { separatorFound, labelRuns, valueRuns };
}

function isSummaryLabelParagraph(para) {
	const text = textOf(para);
	if (!text) return false;
	const trimmed = text.trim();
	if (!trimmed) return false;
	const colonIdx = trimmed.indexOf(':');
	if (colonIdx !== -1 && colonIdx <= 40) return true;
	if (/\t/.test(trimmed)) return true;
	return false;
}

function looksLikeValueContinuation(para) {
	const text = textOf(para);
	if (!text) return false;
	const trimmed = text.trim();
	if (!trimmed) return false;
	if (isSummaryLabelParagraph(para)) return false;
	if (/^Dear\b/i.test(trimmed)) return false;
	if (typeof para.leadingSpaces === 'number' && para.leadingSpaces > 0) return true;
	if (typeof para.leftIndentPt === 'number' && para.leftIndentPt > 0) return true;
	if (/^\{/.test(trimmed)) return true;
	return false;
}

function extractPlaceholders(text) {
	const matches = text.match(/\{\[[^\]]+\]\}/g);
	return matches ? matches : [];
}

function compressParagraphGroup(paragraphs, opts) {
	if (!Array.isArray(paragraphs) || paragraphs.length <= 1) return null;
	const labelKey = opts && typeof opts.label === 'string' ? opts.label.trim().toLowerCase() : '';
	const segments = [];
	for (const para of paragraphs) {
		const text = joinRunsText(para.runs || []).trim();
		if (!text) return null;
		const tokens = extractPlaceholders(text);
		if (!tokens.length) return null;
		const cleaned = text.replace(/\{\[[^\]]+\]\}/g, '');
		if (cleaned.replace(/[\s,.;:()\-/]+/g, '').length) return null;
		segments.push(tokens.join(''));
	}
	if (!segments.length) return null;
	if (labelKey === 'property address' && segments.length > 1) {
		return `{Compress(${segments.slice(0, 2).join('|')})}`;
	}
	return `{Compress(${segments.join('|')})}`;
}

function normalizeSummaryValueParagraphs(paragraphs) {
	return (paragraphs || []).map(par => {
		const clone = cloneParagraph(par);
		clone.leadingSpaces = 0;
		clone.leftIndentPt = undefined;
		clone.firstLineIndentPt = undefined;
		clone.hangingIndentPt = undefined;
		let text = joinRunsText(clone.runs || []);
		if (text) {
			text = text
				.replace(/(\{\[[^\]]+\]\})[\s,;:–-]*\([^()]{1,120}\)/g, '$1')
				.replace(/\([^()]{1,120}\)/g, '')
				.replace(/\s+/g, ' ')
				.trim();
		}
		if (text && /\{\[[^\]]+\]\}\s+and\s+\{\[[^\]]+\]\}/i.test(text) && !/\{If/i.test(text)) {
			const match = text.match(/(\{\[[^\]]+\]\})(\s+and\s+)(\{\[[^\]]+\]\})/i);
			if (match) {
				const connector = match[2].trim() ? ` ${match[2].trim()} ` : ' and ';
				text = `${match[1]}{If('${match[3]}'<>'')}${connector}${match[3]}{End If}`;
			}
		}
		if (text) {
			clone.runs = [{ text }];
		} else {
			clone.runs = [];
		}
		return clone;
	});
}
function stripPlaceholderAnnotations(blocks) {
	const out = [];
	for (const block of blocks || []) {
		if (!block || block.type !== 'paragraph') {
			out.push(block);
			continue;
		}
		const runs = [];
		let prevEndsWithPlaceholder = false;
		let pendingSpace = false;
		let dropParagraph = false;
		for (const run of block.runs || []) {
			if (!run) continue;
			let text = typeof run.text === 'string' ? run.text : '';
			if (!text) {
				continue;
			}
			text = text.replace(/\{\[([A-Za-z0-9\.]+)E[0-9]+\]\}/g, '{[$1]}');
			if (prevEndsWithPlaceholder && /^\s*\([^()]{1,160}\)/.test(text)) {
				const stripped = text.replace(/^\s*\([^()]{1,160}\)\s*/, ' ');
				if (!stripped.trim()) {
					pendingSpace = true;
					prevEndsWithPlaceholder = false;
					continue;
				}
				text = stripped;
			}
			if (/\(State\)/i.test(text) || /\(5-Digit Zip\)/i.test(text) || /\(4-Digit Zip\)/i.test(text) || /Foreign Country Code/i.test(text) || /Foreign Postal Code/i.test(text)) {
				dropParagraph = true;
				break;
			}
			if (pendingSpace && !/^[\s,.;:!?\)\]]/.test(text)) {
				text = ' ' + text;
			}
			text = text.replace(/(\{\[[^\]]+\]\})(\s*\([^()]{1,160}\))/g, '$1 ');
			text = text.replace(/\s{3,}/g, '  ');
			text = text.replace(/\s+([,;:])/g, '$1');
			if (!text.trim()) {
				prevEndsWithPlaceholder = false;
				pendingSpace = false;
				continue;
			}
			const copy = cloneRun(run);
			copy.text = text;
			runs.push(copy);
			prevEndsWithPlaceholder = /\{\[[^\]]+\]\}\s*$/.test(text);
			pendingSpace = false;
		}
		if (dropParagraph) continue;
		if (!runs.length) {
			out.push(block);
			continue;
		}
		const para = cloneParagraph(block);
		para.runs = runs;
		out.push(para);
	}
	return out;
}
function buildLabelValueParagraph(label, value, opts) {
	const template = opts && opts.template;
	const runs = [{ text: label, bold: true, underline: !!(opts && opts.underlineLabel) }];
	if (value && value.length) {
		runs.push({ text: ' ' });
		runs.push({ text: value });
	}
	const para = createParagraphFromRuns(runs, template);
	para.suppressTrailingBreak = !!(opts && opts.suppressTrailingBreak);
	return para;
}
function normalizeAmountSummaryBlocks(blocks) {
	const out = [];
	for (const block of blocks || []) {
		if (!block || block.type !== 'paragraph') {
			out.push(block);
			continue;
		}
		const textRaw = textOf(block);
		const normalized = normalizeWhitespace(textRaw);
		const lower = normalized.toLowerCase();
		if (!normalized) {
			out.push(block);
			continue;
		}
		if (lower.startsWith('to cure') && normalized.includes('{[M591]}')) {
			const paraText = 'To cure the aforesaid breach and default, you are required to pay {Money({[M591]})} which represents the past due amount. Please add an additional late charge of {Money({[U026]})} if paid after {[U027]}. This amount is only valid until {[L008]}.';
			out.push(createParagraphFromRuns([{ text: paraText }], block));
			continue;
		}
		if (normalized.includes('{[C001]}') && normalized.includes('{[M585]}') && normalized.includes('{[M029]}') && normalized.includes('{[M013]}')) {
			const whichIdx = lower.indexOf('which is');
			let tail = 'which is thirty (30) days from the date of this notice.';
			if (whichIdx >= 0) {
				const fragment = normalized.slice(whichIdx);
				tail = fragment.replace(/^which is\s*/i, 'which is ');
			}
			const paraText = `If payment is received after {[L008]}, you must pay the past due amount of {Math({[C001]} + {[M585]} + {[M029]} - {[M013]}|Money)} on or before {[L011]}, ${tail}`.replace(/\s+/g, ' ').trim();
			out.push(createParagraphFromRuns([{ text: paraText }], block));
			continue;
		}
		if (normalized.includes('{[L011]}') && normalized.toLowerCase().includes('total due')) {
			const paraText = 'Demand Notice expires {[L011]}. Total Due: {Math({[C001]} + {[M585]} - {[M013]}|Money)}';
			out.push(createParagraphFromRuns([{ text: paraText, bold: true }], block));
			continue;
		}
		// Only match standalone label/value paragraphs, not narrative text
		if (normalized.includes('{[M590]}') && (lower.includes('number of payments') || lower.includes('payments due'))) {
			out.push(buildLabelValueParagraph('Number of Payments Due:', '{[M590]}', { underlineLabel: true, template: block, suppressTrailingBreak: true }));
			continue;
		}
		if (normalized.includes('{[M591]}') && !lower.startsWith('to cure') && (lower.includes('net payment') || lower.includes('payment amount'))) {
			out.push(buildLabelValueParagraph('Net Payment Amount:', '{Money({[M591]})}', { underlineLabel: true, template: block, suppressTrailingBreak: true }));
			continue;
		}
		if (normalized.includes('{[M015]}') && (lower.includes('late charge') || lower.includes('unpaid late'))) {
			out.push(buildLabelValueParagraph('Unpaid Late Charges:', '{Money({[M015]})}', { underlineLabel: true, template: block, suppressTrailingBreak: true }));
			continue;
		}
		if (normalized.includes('{[M593]}') && normalized.includes('{[C004]}')) {
			out.push(buildLabelValueParagraph('NSF & Other Fees:', '{Math({[M593]} + {[C004]}|Money)}', { underlineLabel: true, template: block, suppressTrailingBreak: true }));
			continue;
		}
		// Only match standalone unapplied/suspense paragraphs, not narrative text
		// Exclude paragraphs that are clearly narrative (contain "which consists", "as of", "prior to", etc.)
		// Also exclude paragraphs that contain Math expressions (they're not standalone label/value pairs)
		const isNarrative = lower.includes('which consists') || lower.includes('as of') || 
			lower.includes('prior to') || lower.includes('notice is hereby') || 
			lower.includes('amount past due') || normalized.includes('Math(');
		// Only match if it's a standalone label/value paragraph, not part of a Math expression
		const isStandaloneLabelValue = (lower.includes('unapplied') || lower.includes('suspense') || lower.includes('partial payment')) &&
			!normalized.includes('Math(') && !normalized.includes('+') && !normalized.includes('-');
		if (normalized.includes('{[M013]}') && !normalized.includes('{[M593]}') && 
			isStandaloneLabelValue && !isNarrative) {
			out.push(buildLabelValueParagraph('Unapplied/Suspense Funds:', '{Money({[M013]})}', { underlineLabel: true, template: block }));
			continue;
		}
		out.push(block);
	}
	return out;
}
function normalizeWhitespace(text) {
	return (text || '').replace(/\s+/g, ' ').trim();
}

function collectBorrowerSummaryRows(blocks, startIndex) {
	const rows = [];
	let i = startIndex;
	while (i < blocks.length) {
		const current = blocks[i];
		if (!current || current.type !== 'paragraph') break;
		const rawText = textOf(current);
		if (!rawText || !rawText.trim()) break;
		if (!isSummaryLabelParagraph(current)) break;
		const split = splitLabelValueRuns(current);
		if (!split.separatorFound) break;
		const labelRuns = trimRunsWhitespace(split.labelRuns);
		const valueRuns = trimRunsWhitespace(split.valueRuns, { leading: true, trailing: true });
		const labelText = normalizeWhitespace(joinRunsText(labelRuns)).replace(/:\s*$/, '');
		const labelParagraph = createParagraphFromRuns(makeRunsBold(labelRuns), current);
		let valueParagraphs = [];
		if (valueRuns.length) {
			valueParagraphs.push(createParagraphFromRuns(valueRuns, current));
		}
		let j = i + 1;
		while (j < blocks.length) {
			const next = blocks[j];
			if (!next || next.type !== 'paragraph') break;
			const nextText = textOf(next);
			if (!nextText || !nextText.trim()) break;
			if (isSummaryLabelParagraph(next)) break;
			if (!looksLikeValueContinuation(next)) break;
			valueParagraphs.push(cloneParagraph(next));
			j++;
		}
		if (!valueParagraphs.length) {
			valueParagraphs.push(createParagraphFromRuns([], current));
		}
		const rawValueCount = valueParagraphs.length;
		const normalizedValues = normalizeSummaryValueParagraphs(valueParagraphs);
		const compressText = compressParagraphGroup(normalizedValues, { label: labelText });
		let rightContent;
		if (compressText) {
			rightContent = [buildParagraph(compressText)];
		} else {
			rightContent = normalizedValues.map(par => {
				const clone = cloneParagraph(par);
				clone.leadingSpaces = 0;
				clone.leftIndentPt = undefined;
				clone.firstLineIndentPt = undefined;
				clone.hangingIndentPt = undefined;
				clone.isListItem = false;
				return clone;
			});
		}
		const labelCellOpts = { widthPct: 20 };
		const labelLower = (labelText || '').toLowerCase();
		const needsTopAlign = labelLower === 'mailing address' || (rawValueCount > 1 && labelLower !== 'property address');
		if (needsTopAlign) labelCellOpts.vAlign = 'top';
		rows.push({
			cells: [
				createTableCell([labelParagraph], labelCellOpts),
				createTableCell(rightContent, {})
			]
		});
		i = j;
	}
	return { rows, nextIndex: i };
}

function convertBorrowerSummary(blocks) {
	const out = [];
	let i = 0;
	let summaryHandled = false;
	while (i < blocks.length) {
		const block = blocks[i];
		if (!summaryHandled && block && block.type === 'paragraph') {
			const text = textOf(block).trim();
			if (/^Dear\b/i.test(text)) summaryHandled = true;
			if (!summaryHandled && isSummaryLabelParagraph(block)) {
				const { rows, nextIndex } = collectBorrowerSummaryRows(blocks, i);
				if (rows.length >= 2) {
					out.push(createTable(rows, { widthPct: 100, borderCollapse: true, styleName: 'SummaryTable' }));
					i = nextIndex;
					summaryHandled = true;
					continue;
				}
			}
		}
		out.push(blocks[i]);
		i++;
	}
	return out;
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

function trimParagraphTrailingWhitespace(para) {
	if (!para || para.type !== 'paragraph') return;
	const runs = para.runs || [];
	for (let idx = runs.length - 1; idx >= 0; idx--) {
		const run = runs[idx];
		if (!run || typeof run.text !== 'string') continue;
		const trimmed = run.text.replace(/[\s\u00A0]+$/g, '');
		if (trimmed.length === 0) {
			run.text = '';
			continue;
		}
		run.text = trimmed;
		break;
	}
}

