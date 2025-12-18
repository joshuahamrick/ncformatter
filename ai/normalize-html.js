// HTML normalization for deterministic exact snapshot matching

function normalizeHtml(html) {
	if (!html || typeof html !== 'string') {
		return '';
	}
	
	let normalized = html;
	
	// Normalize line endings
	normalized = normalized.replace(/\r\n/g, '\n');
	normalized = normalized.replace(/\r/g, '\n');
	
	// Normalize <br> tags (handle both <br> and <br/>)
	normalized = normalized.replace(/<br\s*\/?>/gi, '<br>');
	
	// Normalize whitespace around tags (but preserve intentional spacing)
	// Remove spaces before closing tags
	normalized = normalized.replace(/\s+<\//g, '</');
	// Remove spaces after opening tags (except for content)
	normalized = normalized.replace(/>\s+/g, '>');
	
	// Normalize whitespace in conditional blocks
	normalized = normalized.replace(/\{If\([^}]+\}\)\s+/g, (match) => {
		return match.trim() + ' ';
	});
	normalized = normalized.replace(/\s+\{End If\}/g, (match) => {
		return ' ' + match.trim();
	});
	
	// Normalize multiple consecutive <br> tags (preserve intentional spacing)
	// Replace 3+ consecutive <br> with exactly what was there (but normalize spacing)
	normalized = normalized.replace(/(<br>\s*){3,}/g, (match) => {
		const count = (match.match(/<br>/g) || []).length;
		return '<br>'.repeat(count);
	});
	
	// Normalize whitespace in table attributes (order doesn't matter, but normalize spacing)
	normalized = normalized.replace(/<table([^>]+)>/g, (match, attrs) => {
		// Sort attributes alphabetically for consistency (optional, but helps with exact matching)
		const attrMap = {};
		attrs.replace(/(\w+(?:-\w+)*)="([^"]*)"/g, (_, name, value) => {
			attrMap[name] = value;
		});
		const sortedAttrs = Object.keys(attrMap)
			.sort()
			.map(name => `${name}="${attrMap[name]}"`)
			.join(' ');
		return `<table ${sortedAttrs}>`;
	});
	
	// Normalize whitespace between tags and content
	normalized = normalized.replace(/>\s+</g, '><');
	normalized = normalized.replace(/>\s+([^<])/g, '>$1');
	normalized = normalized.replace(/([^>])\s+</g, '$1<');
	
	// Normalize trailing whitespace
	normalized = normalized.replace(/\s+$/gm, '');
	
	// Normalize empty lines (remove completely empty lines, but preserve intentional spacing)
	normalized = normalized.replace(/\n{3,}/g, '\n\n');
	
	// Final trim
	normalized = normalized.trim();
	
	return normalized;
}

module.exports = {
	normalizeHtml
};

