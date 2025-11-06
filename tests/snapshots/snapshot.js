window.Snapshots = (function () {
	const samples = [
		{ id: 'BR007', input: '../../formatter examples/BR007/BR007 - Final Demand TX - Flat Branch - V1.0.docx', expected: '../../formatter examples/BR007/BR007-formatted.html' },
		{ id: 'BR008', input: '../../formatter examples/BR008/BR008 - Final Demand IA - Flat Branch - V1.0.docx', expected: '../../formatter examples/BR008/BR008-formatted.html' },
		{ id: 'BR010', input: '../../formatter examples/BR010/BR010 - Final Demand FL - Flat Branch - V1.0.docx', expected: '../../formatter examples/BR010/BR010-formatted.html' },
		{ id: 'BR017', input: '../../formatter examples/BR017/BR017 - Final Demand SC - Flat Branch - V1.0.docx', expected: '../../formatter examples/BR017/BR017-formatted.html' },
		{ id: 'CT102', input: '../../formatter examples/CT102/CT102 CT Breach Property - MSF - V1.0.docx', expected: '../../formatter examples/CT102/CT102-formatted.html' },
		{ id: 'LM060', input: '../../formatter examples/LM060/LM060.docx', expected: '../../formatter examples/LM060/LM060-formatted.html' },
		{ id: 'SD002', input: '../../formatter examples/SD002/SD002 SD Breach Mailing - MSF - V1.0.docx', expected: '../../formatter examples/SD002/SD002-formatted.html' },
		{ id: 'SL106', input: '../../formatter examples/SL106/SL106_VP_75 Day Maturing Loan v17 (1).docx', expected: '../../formatter examples/SL106/SL106-formatted.html' },
		{ id: 'PRIVACY', input: '../../Fed-Priv-Form-MC/Federal Privacy Model Form - Mortgage Clearing - V06.11.2024 (1).docx', expected: '../../Fed-Priv-Form-MC/Fed-Priv-Form-formatted.html' }
	];

	async function init() {
		const select = document.getElementById('sampleSelect');
		for (const s of samples) {
			const opt = document.createElement('option');
			opt.value = s.id;
			opt.textContent = s.id;
			select.appendChild(opt);
		}
		document.getElementById('loadExpected').addEventListener('click', loadExpected);
		document.getElementById('runTest').addEventListener('click', runTest);
	}

	function getSelectedSample() {
		const id = document.getElementById('sampleSelect').value;
		return samples.find(s => s.id === id);
	}

	async function loadExpected() {
		const s = getSelectedSample();
		if (!s) return;
		try {
			const resp = await fetch(s.expected);
			const html = await resp.text();
			document.getElementById('expectedHtml').innerHTML = html;
		} catch (e) {
			alert('Failed to load expected HTML: ' + e.message);
		}
	}

	async function runTest() {
		const file = document.getElementById('inputFile').files[0];
		if (!file) return alert('Choose an input file first.');
		try {
			let htmlOut = '';
			if (file.name.toLowerCase().endsWith('.pdf')) {
				const ab = await readFileAsArrayBuffer(file);
				const ir = await extractIRFromPdf(ab);
				htmlOut = window.NcRenderer.renderIRToHtml(ir);
			} else {
				// Call local serverless endpoint
				const base64 = await toBase64(file);
				const resp = await fetch('/api/process-doc.py', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ fileData: base64.split(',')[1], fileName: file.name })
				});
				const json = await resp.json();
				if (!json.success) throw new Error(json.error || 'DOCX processing failed');
				htmlOut = window.NcRenderer.renderIRToHtml(json.ir);
			}
			document.getElementById('generatedHtml').innerHTML = htmlOut;
			// compare with expected
			const expected = document.getElementById('expectedHtml').innerHTML;
			const normA = window.Normalize.normalizeDom(htmlOut);
			const normB = window.Normalize.normalizeDom(expected);
			const equal = normA === normB;
			const result = document.getElementById('result');
			result.innerHTML = equal ? '<span class="ok">MATCH ✅</span>' : '<span class="bad">DIFFER ❌</span>\n\n' + diffStrings(normA, normB);
		} catch (e) {
			alert('Test failed: ' + e.message);
		}
	}

	function toBase64(file) {
		return new Promise((resolve, reject) => {
			const r = new FileReader();
			r.onload = () => resolve(String(r.result));
			r.onerror = () => reject(new Error('Failed to read file'));
			r.readAsDataURL(file);
		});
	}

	// Very simple diff for display purposes
	function diffStrings(a, b) {
		if (a === b) return '';
		return [
			'--- generated ---',
			a,
			'--- expected ---',
			b
		].join('\n');
	}

	return { init };
})();

