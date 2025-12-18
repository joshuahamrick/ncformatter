// Snapshot runner for AI-generated HTML comparison
// Compares AI-generated HTML against expected snapshots

const fs = require('fs');
const path = require('path');

const EXAMPLES_DIR = path.join(__dirname, '..', 'formatter examples');

// Normalization function (inline)
function normalizeHtml(html) {
	if (!html || typeof html !== 'string') {
		return '';
	}
	
	let normalized = html;
	
	// Normalize line endings
	normalized = normalized.replace(/\r\n/g, '\n');
	normalized = normalized.replace(/\r/g, '\n');
	
	// Normalize <br> tags
	normalized = normalized.replace(/<br\s*\/?>/gi, '<br>');
	
	// Normalize whitespace around tags
	normalized = normalized.replace(/\s+<\//g, '</');
	normalized = normalized.replace(/>\s+/g, '>');
	
	// Normalize conditional blocks
	normalized = normalized.replace(/\{If\([^}]+\}\)\s+/g, (match) => {
		return match.trim() + ' ';
	});
	normalized = normalized.replace(/\s+\{End If\}/g, (match) => {
		return ' ' + match.trim();
	});
	
	// Normalize multiple <br> tags
	normalized = normalized.replace(/(<br>\s*){3,}/g, (match) => {
		const count = (match.match(/<br>/g) || []).length;
		return '<br>'.repeat(count);
	});
	
	// Normalize whitespace between tags
	normalized = normalized.replace(/>\s+</g, '><');
	normalized = normalized.replace(/>\s+([^<])/g, '>$1');
	normalized = normalized.replace(/([^>])\s+</g, '$1<');
	
	// Normalize trailing whitespace
	normalized = normalized.replace(/\s+$/gm, '');
	
	// Normalize empty lines
	normalized = normalized.replace(/\n{3,}/g, '\n\n');
	
	return normalized.trim();
}

function getAllExamplePairs() {
	const pairs = [];
	const dirs = fs.readdirSync(EXAMPLES_DIR, { withFileTypes: true });
	
	for (const dir of dirs) {
		if (!dir.isDirectory()) continue;
		const dirPath = path.join(EXAMPLES_DIR, dir.name);
		const files = fs.readdirSync(dirPath);
		
		// Find docx and formatted HTML
		const docxFile = files.find(f => f.endsWith('.docx'));
		const formattedFile = files.find(f => 
			f.includes('-formatted.html') && 
			!f.includes('iterative') && 
			!f.includes('test')
		);
		
		if (docxFile && formattedFile) {
			pairs.push({
				name: dir.name,
				docxPath: path.join(dirPath, docxFile),
				expectedHtmlPath: path.join(dirPath, formattedFile)
			});
		}
	}
	
	return pairs;
}

function loadExpectedHtml(filePath) {
	try {
		return fs.readFileSync(filePath, 'utf8');
	} catch (e) {
		return null;
	}
}

function compareHtml(actual, expected) {
	// Normalize both
	const normalizedActual = normalizeHtml(actual);
	const normalizedExpected = normalizeHtml(expected);
	
	if (normalizedActual === normalizedExpected) {
		return { match: true, diff: null };
	}
	
	// Generate diff
	const diff = generateDiff(normalizedActual, normalizedExpected);
	return { match: false, diff };
}

function generateDiff(actual, expected) {
	const actualLines = actual.split('\n');
	const expectedLines = expected.split('\n');
	const maxLen = Math.max(actualLines.length, expectedLines.length);
	
	const diff = [];
	for (let i = 0; i < maxLen; i++) {
		const actualLine = actualLines[i] || '';
		const expectedLine = expectedLines[i] || '';
		
		if (actualLine !== expectedLine) {
			diff.push({
				line: i + 1,
				expected: expectedLine,
				actual: actualLine
			});
		}
	}
	
	return diff;
}

async function runSnapshotTest(pair, generateFn) {
	console.log(`\nTesting: ${pair.name}`);
	console.log(`  DOCX: ${path.basename(pair.docxPath)}`);
	console.log(`  Expected: ${path.basename(pair.expectedHtmlPath)}`);
	
	try {
		// Load expected HTML
		const expectedHtml = loadExpectedHtml(pair.expectedHtmlPath);
		if (!expectedHtml) {
			console.log(`  ⚠️  No expected HTML found, skipping`);
			return { name: pair.name, skipped: true };
		}
		
		// Generate HTML (this would need to call your AI generation)
		// For now, this is a placeholder - you'd need to integrate with your IR extraction + AI generation
		const actualHtml = await generateFn(pair.docxPath);
		
		if (!actualHtml) {
			console.log(`  ❌ Generation failed`);
			return { name: pair.name, error: 'Generation failed' };
		}
		
		// Compare
		const comparison = compareHtml(actualHtml, expectedHtml);
		
		if (comparison.match) {
			console.log(`  ✅ Exact match!`);
			return { name: pair.name, match: true };
		} else {
			console.log(`  ❌ Mismatch (${comparison.diff.length} differences)`);
			if (comparison.diff.length <= 10) {
				comparison.diff.forEach(d => {
					console.log(`    Line ${d.line}:`);
					console.log(`      Expected: ${d.expected.substring(0, 80)}`);
					console.log(`      Actual:   ${d.actual.substring(0, 80)}`);
				});
			}
			return { name: pair.name, match: false, diff: comparison.diff };
		}
		
	} catch (error) {
		console.log(`  ❌ Error: ${error.message}`);
		return { name: pair.name, error: error.message };
	}
}

async function runAllSnapshots(generateFn) {
	console.log('Running snapshot tests for AI-generated HTML...\n');
	
	const pairs = getAllExamplePairs();
	console.log(`Found ${pairs.length} example pairs\n`);
	
	const results = [];
	for (const pair of pairs) {
		const result = await runSnapshotTest(pair, generateFn);
		results.push(result);
	}
	
	// Summary
	console.log('\n' + '='.repeat(60));
	console.log('SUMMARY');
	console.log('='.repeat(60));
	
	const matched = results.filter(r => r.match).length;
	const mismatched = results.filter(r => !r.match && !r.error && !r.skipped).length;
	const errors = results.filter(r => r.error).length;
	const skipped = results.filter(r => r.skipped).length;
	
	console.log(`Total: ${results.length}`);
	console.log(`✅ Matched: ${matched}`);
	console.log(`❌ Mismatched: ${mismatched}`);
	console.log(`⚠️  Errors: ${errors}`);
	console.log(`⏭️  Skipped: ${skipped}`);
	
	if (matched === results.length - skipped) {
		console.log('\n🎉 All tests passed!');
	} else {
		console.log('\n⚠️  Some tests failed. Review differences above.');
	}
	
	return results;
}

// Placeholder for generate function - would need to integrate with actual IR extraction + AI
async function placeholderGenerate(docxPath) {
	// This would:
	// 1. Extract IR from DOCX
	// 2. Call AI generation API
	// 3. Return HTML
	throw new Error('Generate function not implemented. Integrate with IR extraction + AI API.');
}

// If run directly
if (require.main === module) {
	runAllSnapshots(placeholderGenerate).catch(console.error);
}

module.exports = {
	runAllSnapshots,
	runSnapshotTest,
	getAllExamplePairs,
	compareHtml
};

