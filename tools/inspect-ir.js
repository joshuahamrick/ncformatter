const fs = require('fs');
const path = require('path');

const { transformIRGeneric } = require('./transformer-node');

const SITE = 'https://ncformatter.vercel.app';
const sampleDir = path.join(__dirname, '..', 'formatter examples');

async function main() {
	const sampleId = process.argv[2] || 'BR010';
	const samplePath = findDoc(sampleId);
	if (!samplePath) {
		console.error('Sample not found:', sampleId);
		process.exit(1);
	}

	const ir = await getIR(samplePath);
	console.log('Original blocks:', ir.blocks.length);
	printSummary(ir);

	const transformed = transformIRGeneric(ir);
	console.log('\nAfter transform:');
	printSummary(transformed);
}

function findDoc(id) {
	const dir = path.join(sampleDir, id);
	if (!fs.existsSync(dir)) return null;
	const files = fs.readdirSync(dir);
	const doc = files.find(f => f.toLowerCase().endsWith('.docx'));
	return doc ? path.join(dir, doc) : null;
}

async function getIR(docPath) {
	const buf = fs.readFileSync(docPath);
	const base64 = buf.toString('base64');
	const res = await fetch(`${SITE}/api/process-doc.py`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			fileData: base64,
			fileName: path.basename(docPath)
		})
	});
	if (!res.ok) throw new Error(`HTTP ${res.status}`);
	const json = await res.json();
	if (!json.success) throw new Error(json.error || 'api error');
	return json.ir;
}

function printSummary(ir) {
	(ir.blocks || []).forEach((b, idx) => {
		if (b.type === 'paragraph') {
			const flags = [];
			if (b.isListItem) flags.push('LIST');
			if (b.preserveBlank) flags.push('BLANK');
			const flagStr = flags.length ? `[${flags.join(',')}] ` : '';
			console.log(idx, 'P:', flagStr + sanitize(textOf(b)));
		} else if (b.type === 'table') {
			const styleName = b.styleName || '';
			console.log(idx, 'T:', styleName || '-', 'rows', (b.rows || []).length);
			if (styleName === 'PaymentTable' && b.rows && b.rows[0] && b.rows[0].cells[0]) {
				const cell = b.rows[0].cells[0];
				const firstPara = cell.content && cell.content[0];
				console.log('   left cell runs:', firstPara && firstPara.runs);
			}
		} else if (b.type === 'pageBreak') {
			console.log(idx, 'PAGE BREAK');
		}
	});
}

function textOf(para) {
	return (para.runs || []).map(r => r.text || '').join('');
}

function sanitize(s) {
	return s.replace(/\s+/g, ' ').trim();
}

main().catch(err => {
	console.error(err);
	process.exit(1);
});

