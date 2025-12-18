// Few-shot example packer for AI prompts
// Reads formatted examples and creates a structured few-shot prompt

const fs = require('fs');
const path = require('path');

const EXAMPLES_DIR = path.join(__dirname, '..', 'formatter examples');

// Curated examples representing different patterns
const CURATED_EXAMPLES = [
	'GB001/GB001-formatted.html',  // Transfer letter with tables
	'ES114/ES114-formatted.html',   // Simple subject + property
	'CA001/CA001-formatted.html',   // Welcome letter with bullet lists
	'CA003/CA003-formatted.html',   // ACH confirmation with conditionals
	'LM401/LM401-formatted.html',   // Complex table + conditionals
];

function loadExample(relativePath) {
	const fullPath = path.join(EXAMPLES_DIR, relativePath);
	if (!fs.existsSync(fullPath)) {
		console.warn(`Example not found: ${fullPath}`);
		return null;
	}
	return fs.readFileSync(fullPath, 'utf8').trim();
}

function packFewShotExamples() {
	const examples = [];
	
	for (const examplePath of CURATED_EXAMPLES) {
		const html = loadExample(examplePath);
		if (html) {
			examples.push({
				name: path.basename(examplePath, '.html'),
				html: html
			});
		}
	}
	
	return examples;
}

function formatFewShotPrompt(examples) {
	let prompt = '\n## Example Outputs (Few-Shot Learning)\n\n';
	prompt += 'Here are examples of correctly formatted HTML templates:\n\n';
	
	examples.forEach((ex, idx) => {
		prompt += `### Example ${idx + 1}: ${ex.name}\n`;
		prompt += '```html\n';
		prompt += ex.html;
		prompt += '\n```\n\n';
	});
	
	return prompt;
}

function getAllFormattedExamples() {
	const examples = [];
	const dirs = fs.readdirSync(EXAMPLES_DIR, { withFileTypes: true });
	
	for (const dir of dirs) {
		if (!dir.isDirectory()) continue;
		const dirPath = path.join(EXAMPLES_DIR, dir.name);
		const files = fs.readdirSync(dirPath);
		
		const formattedFile = files.find(f => f.includes('-formatted.html') && !f.includes('iterative') && !f.includes('test'));
		if (formattedFile) {
			const html = loadExample(path.join(dir.name, formattedFile));
			if (html) {
				examples.push({
					name: dir.name,
					html: html
				});
			}
		}
	}
	
	return examples;
}

module.exports = {
	packFewShotExamples,
	formatFewShotPrompt,
	getAllFormattedExamples
};

