const fs = require('fs');
const path = require('path');
const { transformIRGeneric } = require('./transformer-node');
const { renderIRToHtml } = require('../renderer-node');

const SITE = 'https://ncformatter.vercel.app';

async function main() {
	const docPath = process.argv[2];
	if (!docPath) {
		console.error('Usage: node tools/debug-doc.js <docx-path>');
		process.exit(1);
	}
	const abs = path.resolve(docPath);
	const ir = await getIR(abs);
	if (ir.meta && ir.meta.headerTexts) {
		console.log('Header texts found:', ir.meta.headerTexts);
	} else {
		console.log('No header texts in IR meta');
	}
	console.log('Original paragraphs:');
	(ir.blocks || []).forEach((block, idx) => {
		if (block.type === 'paragraph') {
			const text = (block.runs || []).map(r => r.text).join('');
			console.log(idx + ':', JSON.stringify(text));
		} else if (block.type === 'table') {
			console.log(idx + ': [TABLE]');
		}
	});
	const transformed = transformIRGeneric(ir);
	console.log('Paragraphs after transform:');
	transformed.blocks.forEach((block, idx) => {
		if (block.type === 'paragraph') {
			const text = (block.runs || []).map(r => r.text).join('');
			console.log(idx + ':', JSON.stringify(text), 'align=', block.align);
		} else if (block.type === 'table') {
			console.log(idx + ': [TABLE]');
		} else if (block.type === 'pageBreak') {
			console.log(idx + ': [PAGE BREAK]');
		}
	});
	const html = renderIRToHtml(transformed, { styleMap: loadStyleMap() });
	fs.writeFileSync(path.join(__dirname, 'debug-output.html'), html);
	console.log('Rendered HTML written to tools/debug-output.html');
}

function loadStyleMap() {
	try {
		return JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'style-map.json'), 'utf8'));
	} catch {
		return {};
	}
}

async function getIR(docxPath) {
	const buf = fs.readFileSync(docxPath);
	const base64 = buf.toString('base64');
	const res = await fetch(`${SITE}/api/process-doc.py`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			fileData: base64,
			fileName: path.basename(docxPath)
		})
	});
	if (!res.ok) throw new Error(`HTTP ${res.status}`);
	const json = await res.json();
	if (!json.success) throw new Error(json.error || 'API error');
	return json.ir;
}

main().catch(err => {
	console.error(err);
	process.exit(1);
});

