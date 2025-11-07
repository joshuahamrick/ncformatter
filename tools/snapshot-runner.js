/* Node snapshot runner: compares generated HTML vs expected for all examples */
const fs = require('fs');
const path = require('path');
const { renderIRToHtml } = require('../renderer-node');
const { transformIRGeneric } = require('./transformer-node');

const SITE = 'https://ncformatter.vercel.app';
const ROOT = path.resolve(__dirname, '..');
const EXAMPLES_DIR = path.join(ROOT, 'formatter examples');

async function main() {
	const styleMap = loadStyleMap();
	const samples = collectSamples(EXAMPLES_DIR);
	if (!samples.length) {
		console.log('No samples found.');
		process.exit(1);
	}
	let passed = 0;
	let failed = 0;
	for (const s of samples) {
		try {
			const ir = await getIRFromRemote(s.inputPath);
			const ir2 = transformIRGeneric(ir);
			const html = renderIRToHtml(ir2, { styleMap });
			const expected = fs.readFileSync(s.expectedPath, 'utf8');
			const normA = normalize(html);
			const normB = normalize(expected);
			const ok = normA === normB;
			if (ok) {
				console.log(`✓ ${s.id} MATCH`);
				passed++;
			} else {
				console.log(`❌ ${s.id} DIFFER`);
				writeDiffArtifacts(s.id, html, expected);
				failed++;
			}
		} catch (e) {
			console.log(`❌ ${s.id} ERROR: ${e.message}`);
			failed++;
		}
	}
	console.log(`\nSummary: ${passed} passed, ${failed} failed`);
	if (failed > 0) process.exit(2);
}

function loadStyleMap() {
	try {
		const p = path.join(ROOT, 'style-map.json');
		const raw = fs.readFileSync(p, 'utf8');
		return JSON.parse(raw);
	} catch {
		return {};
	}
}

function collectSamples(dir) {
	const out = [];
	const subs = fs.readdirSync(dir);
	for (const name of subs) {
		const sub = path.join(dir, name);
		if (!fs.statSync(sub).isDirectory()) continue;
		const files = fs.readdirSync(sub);
		const input = files.find(f => f.toLowerCase().endsWith('.docx'));
		const expected = files.find(f => f.toLowerCase().endsWith('-formatted.html'));
		if (input && expected) {
			out.push({
				id: name,
				inputPath: path.join(sub, input),
				expectedPath: path.join(sub, expected)
			});
		}
	}
	return out;
}

async function getIRFromRemote(docxPath) {
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
	if (!res.ok) {
		throw new Error(`HTTP ${res.status}`);
	}
	const json = await res.json();
	if (!json.success || !json.ir) {
		throw new Error('API returned error');
	}
	return json.ir;
}

function normalize(html) {
	return String(html)
		.replace(/\r/g, '')
		.replace(/>\s+</g, '><')
		.replace(/\s{2,}/g, ' ')
		.trim();
}

function writeDiffArtifacts(id, generated, expected) {
	const outDir = path.join(ROOT, 'tests', 'snapshots', 'artifacts');
	fs.mkdirSync(outDir, { recursive: true });
	fs.writeFileSync(path.join(outDir, `${id}.generated.html`), generated);
	fs.writeFileSync(path.join(outDir, `${id}.expected.html`), expected);
}

main().catch(err => {
	console.error(err);
	process.exit(1);
});

