window.Normalize = (function () {
	function normalizeHtmlStr(html) {
		// Remove redundant whitespace between tags and normalize spaces
		return String(html)
			.replace(/\r/g, '')
			.replace(/\n\s*\n+/g, '\n')
			.replace(/>\s+</g, '><')
			.replace(/\s{2,}/g, ' ')
			.trim();
	}
	function normalizeDom(html) {
		const div = document.createElement('div');
		div.innerHTML = html;
		// Remove insignificant whitespace text nodes
		walk(div, node => {
			if (node.nodeType === Node.TEXT_NODE) {
				node.textContent = node.textContent.replace(/\s+/g, ' ').trim();
			}
		});
		return div.innerHTML;
	}
	function walk(node, fn) {
		fn(node);
		let child = node.firstChild;
		while (child) {
			const next = child.nextSibling;
			walk(child, fn);
			child = next;
		}
	}
	return { normalizeHtmlStr, normalizeDom };
})();

