const fs = require('fs');
const path = require('path');
const { transformIRGeneric } = require('./transformer-node');

async function main() {
	const docPath = process.argv[2];
	if (!docPath) {
		console.error('usage: node tools/inspect-bullets.js <docx>');
		process.exit(1);
	}
	const abs = path.resolve(docPath);
	const buf = fs.readFileSync(abs);
	const base64 = buf.toString('base64');
	const res = await fetch('https://ncformatter.vercel.app/api/process-doc.py', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ fileData: base64, fileName: path.basename(abs) })
	});
	const json = await res.json();
	const ir = transformIRGeneric(json.ir);
	ir.blocks.forEach((b, idx) => {
		if (b.type === 'table' && b.widthPct === 80) {
			console.log('Bullet table at block', idx);
			b.rows.forEach((row, rIdx) => {
				const texts = row.cells.map(cell =>
					(cell.content || [])
						.map(p => (p.runs || []).map(run => run.text).join(''))
						.join(' ')
				);
				console.log(' row', rIdx, texts);
			});
		}
	});
}

main().catch(err => {
	console.error(err);
	process.exit(1);
});

