// Word Document Formatter - Python Backend Version

class WordFormatter {
    constructor() {
        this.initializeElements();
        this.setupEventListeners();
        console.log('WordFormatter initialized');
    }

    initializeElements() {
        this.fileInput = document.getElementById('fileInput');
        this.dropZone = document.getElementById('dropZone');
        this.resultsSection = document.getElementById('resultsSection');
        this.formattedPreview = document.getElementById('formattedPreview');
        this.htmlCode = document.getElementById('htmlCode');
        this.copyButton = document.getElementById('copyButton');
        this.processingDiv = document.getElementById('processing');
        this.tabButtons = document.querySelectorAll('.tab-btn');
        
        console.log('Elements found:', {
            fileInput: !!this.fileInput,
            dropZone: !!this.dropZone,
            resultsSection: !!this.resultsSection,
            formattedPreview: !!this.formattedPreview,
            htmlCode: !!this.htmlCode,
            copyButton: !!this.copyButton,
            processingDiv: !!this.processingDiv,
            tabButtons: this.tabButtons.length
        });
    }

    setupEventListeners() {
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        }
        if (this.dropZone) {
            this.dropZone.addEventListener('dragover', (e) => this.handleDragOver(e));
            this.dropZone.addEventListener('dragleave', (e) => this.handleDragLeave(e));
            this.dropZone.addEventListener('drop', (e) => this.handleDrop(e));
        }
        if (this.copyButton) {
            this.copyButton.addEventListener('click', () => this.copyToClipboard());
        }
        
        // Tab switching
        this.tabButtons.forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
		if (file && (this.isWordDocument(file) || isPdfDocument(file))) {
            this.processFile(file);
        }
    }

    handleDragOver(event) {
        event.preventDefault();
        this.dropZone.classList.add('drag-over');
    }

    handleDragLeave(event) {
        event.preventDefault();
        this.dropZone.classList.remove('drag-over');
    }

    handleDrop(event) {
        event.preventDefault();
        this.dropZone.classList.remove('drag-over');
        
        const files = event.dataTransfer.files;
		if (files.length > 0 && (this.isWordDocument(files[0]) || isPdfDocument(files[0]))) {
            this.processFile(files[0]);
        }
    }

    isWordDocument(file) {
        return file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
               file.type === 'application/msword' ||
               file.name.toLowerCase().endsWith('.docx') ||
               file.name.toLowerCase().endsWith('.doc');
    }

    async processFile(file) {
        console.log('Processing file:', file.name);
        
        try {
            this.showProcessing();
			let htmlOut = '';
			if (this.isWordDocument(file)) {
				// Use DOCX IR endpoint
				const arrayBuffer = await new Promise((resolve, reject) => {
					const reader = new FileReader();
					reader.onload = e => resolve(e.target.result);
					reader.onerror = () => reject(new Error('Failed to read file'));
					reader.readAsDataURL(file);
				});
				const base64String = String(arrayBuffer).split(',')[1];
				const response = await fetch('/api/process-doc.py', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ fileData: base64String, fileName: file.name })
				});
				if (!response.ok) throw new Error('DOCX processing failed: ' + response.status);
				const result = await response.json();
				if (!result.success) throw new Error(result.error || 'DOCX processing error');
				const ir = result.ir;
				htmlOut = window.NcRenderer.renderIRToHtml(ir);
			} else if (isPdfDocument(file)) {
				const arrayBuffer = await readFileAsArrayBuffer(file);
				let ir = await extractIRFromPdf(arrayBuffer);
				// Fallback to server PDF extraction if result looks empty/low-confidence
				const hasContent = Array.isArray(ir.blocks) && ir.blocks.some(b => b.type === 'paragraph' && joinRunsText(b.runs || []).trim().length > 0);
				if (!hasContent || (typeof ir.confidence === 'number' && ir.confidence < 0.5)) {
					try {
						const base64String = await new Promise((resolve, reject) => {
							const r = new FileReader();
							r.onload = () => resolve(String(r.result).split(',')[1]);
							r.onerror = () => reject(new Error('Failed to read file'));
							r.readAsDataURL(file);
						});
						const resp = await fetch('/api/process-pdf.py', {
							method: 'POST',
							headers: { 'Content-Type': 'application/json' },
							body: JSON.stringify({ fileData: base64String, fileName: file.name })
						});
						if (resp.ok) {
							const json = await resp.json();
							if (json && json.success && json.ir) {
								ir = json.ir;
							}
						}
					} catch (e) {
						console.warn('PDF server fallback failed:', e);
					}
				}
				htmlOut = window.NcRenderer.renderIRToHtml(ir);
			} else {
				throw new Error('Unsupported file type');
			}
			this.displayResult(htmlOut);
        } catch (error) {
            console.error('Error processing file:', error);
            this.showError('Failed to process document: ' + error.message);
        }
    }

    showProcessing() {
        if (this.processingDiv) {
            this.processingDiv.style.display = 'block';
        }
        if (this.resultsSection) {
            this.resultsSection.style.display = 'none';
        }
    }

    hideProcessing() {
        if (this.processingDiv) {
            this.processingDiv.style.display = 'none';
        }
    }

    displayResult(formattedText) {
        console.log('Displaying result:', formattedText.substring(0, 100) + '...');
        
        // Hide processing
        this.hideProcessing();
        
        // Set the preview content
        if (this.formattedPreview) {
            this.formattedPreview.innerHTML = formattedText;
        }
        
        // Set the HTML code content
        if (this.htmlCode) {
            this.htmlCode.textContent = formattedText;
        }
        
        // Show results section
        if (this.resultsSection) {
            this.resultsSection.style.display = 'block';
            this.resultsSection.scrollIntoView({ behavior: 'smooth' });
        }
    }

    showError(message) {
        this.hideProcessing();
        alert('Error: ' + message);
    }

    switchTab(tabName) {
        // Remove active class from all tabs and content
        this.tabButtons.forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        
        // Add active class to selected tab and content
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
        document.getElementById(`${tabName}Tab`).classList.add('active');
    }

    copyToClipboard() {
        if (!this.htmlCode) {
            console.error('HTML code element not found');
            return;
        }
        
        const htmlContent = this.htmlCode.textContent;
        navigator.clipboard.writeText(htmlContent).then(() => {
            // Show feedback
            if (this.copyButton) {
                const originalText = this.copyButton.innerHTML;
                this.copyButton.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20,6 9,17 4,12"/>
                    </svg>
                    Copied!
                `;
                
                setTimeout(() => {
                    this.copyButton.innerHTML = originalText;
                }, 2000);
            }
        }).catch(err => {
            console.error('Failed to copy: ', err);
            alert('Failed to copy to clipboard');
        });
    }

    static async extractTextFromWord(file) {
        console.log('extractTextFromWord called with:', file.name, 'Size:', file.size);
        
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            
            reader.onload = async function(event) {
                console.log('FileReader onload triggered');
                const dataURL = event.target.result;
                console.log('DataURL length:', dataURL.length);
                
                try {
                    // Extract base64 string from data URL
                    const base64String = dataURL.split(',')[1];
                    
                    // Call Vercel Python serverless function
                    const response = await fetch('/api/process-word.py', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            fileData: base64String,
                            fileName: file.name
                        })
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    
                    const result = await response.json();
                    console.log('Python processing result:', result);
                    
                    if (result.success) {
                        resolve(result.formattedHtml);
                    } else {
                        const errorMsg = result.error || 'Unknown error';
                        console.error('Python processing error:', errorMsg);
                        resolve(`<div style="color: red; padding: 20px; border: 1px solid red; border-radius: 4px;">
                            <h3>Error Processing Document:</h3>
                            <p>${errorMsg}</p>
                        </div>`);
                    }
                    
                } catch (error) {
                    console.error('Error calling Python function:', error);
                    resolve(`<div style="color: red; padding: 20px; border: 1px solid red; border-radius: 4px;">
                        <h3>Error Processing Document:</h3>
                        <p>Failed to process document: ${error.message}</p>
                    </div>`);
                }
            };
            
            reader.onerror = function() {
                console.error('FileReader error occurred');
                reject(new Error('Failed to read file'));
            };
            
            reader.readAsDataURL(file);
        });
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
	// Preload style-map.json (best-effort)
	(async () => {
		try {
			const resp = await fetch('style-map.json', { cache: 'no-store' });
			if (resp.ok) {
				const map = await resp.json();
				window.NcStyleMap = map;
			} else {
				window.NcStyleMap = {};
			}
		} catch {
			window.NcStyleMap = {};
		}
		// Health status
		try {
			const hr = await fetch('/api/health.py', { cache: 'no-store' });
			let text = 'API: ';
			if (hr.ok) {
				const json = await hr.json();
				const libs = json.libs || {};
				const ok = libs.docx && libs.pdfminer;
				text += ok ? 'OK' : 'Degraded';
				text += ` (docx: ${libs.docx ? 'yes' : 'no'}, pdfminer: ${libs.pdfminer ? 'yes' : 'no'})`;
			} else {
				text += 'Unavailable';
			}
			const el = document.getElementById('healthStatus');
			if (el) el.textContent = text;
		} catch (e) {
			const el = document.getElementById('healthStatus');
			if (el) el.textContent = 'API: Unavailable';
		}
    new WordFormatter();
	})();
});

// ------------------------
// PDF client-side extractor (pdf.js)
// ------------------------

/**
 * Returns true if the file is a PDF
 * @param {File} file
 */
function isPdfDocument(file) {
	if (!file) return false;
	const name = (file.name || '').toLowerCase();
	return file.type === 'application/pdf' || name.endsWith('.pdf');
}

/**
 * Load pdf.js if not already present on window
 * @returns {Promise<any>}
 */
async function ensurePdfJsLoaded() {
	// Already loaded
	if (window['pdfjsLib']) return window['pdfjsLib'];
	// Inject from CDN
	await new Promise((resolve, reject) => {
		const script = document.createElement('script');
		script.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.6.82/pdf.min.js';
		script.onload = resolve;
		script.onerror = () => reject(new Error('Failed to load pdf.js'));
		document.head.appendChild(script);
	});
	const pdfjsLib = window['pdfjsLib'];
	if (!pdfjsLib) throw new Error('pdf.js failed to initialize');
	// Optional: worker (use same CDN version)
	if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
		pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.6.82/pdf.worker.min.js';
	}
	return pdfjsLib;
}

/**
 * Convert PDF file to ArrayBuffer
 * @param {File} file
 * @returns {Promise<ArrayBuffer>}
 */
function readFileAsArrayBuffer(file) {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = e => resolve(e.target.result);
		reader.onerror = () => reject(new Error('Failed to read file'));
		reader.readAsArrayBuffer(file);
	});
}

/**
 * Extracts a simple IRDocument from PDF using pdf.js
 * @param {ArrayBuffer} arrayBuffer
 * @returns {Promise<IRDocument>}
 */
async function extractIRFromPdf(arrayBuffer) {
	const pdfjsLib = await ensurePdfJsLoaded();
	const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
	const pdf = await loadingTask.promise;

	/** @type {Array<IRParagraph|IRTable|IRPageBreak>} */
	const blocks = [];

	for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
		const page = await pdf.getPage(pageNum);
		const content = await page.getTextContent();
		// Collect items with positions
		const items = content.items
			.map(it => {
				const t = it.transform; // [a,b,c,d,e,f]; e=x, f=y
				return {
					str: it.str || '',
					x: typeof t[4] === 'number' ? t[4] : 0,
					y: typeof t[5] === 'number' ? t[5] : 0,
					fontSize: (it.height) || undefined
				};
			})
			.filter(it => it.str && it.str.trim().length > 0);

		// Group items by Y (line) with tolerance
		const yTolerance = 2.0;
		items.sort((a, b) => b.y - a.y || a.x - b.x);
		/** @type {Array<Array<typeof items[0]>>} */
		const lines = [];
		for (const it of items) {
			let placed = false;
			for (const line of lines) {
				if (Math.abs(line[0].y - it.y) <= yTolerance) {
					line.push(it);
					placed = true;
					break;
				}
			}
			if (!placed) lines.push([it]);
		}
		// Sort each line by X and build text
		const lineTexts = lines.map(line => {
			line.sort((a, b) => a.x - b.x);
			// Insert single spaces between fragments when far enough
			let text = '';
			let prevX = null;
			for (const frag of line) {
				if (prevX !== null && (frag.x - prevX) > 2) {
					text += ' ';
				}
				text += frag.str;
				prevX = frag.x + (frag.str ? frag.str.length : 0);
			}
			return text;
		});

		// Simple paragraphization: join consecutive non-empty lines with spaces, split on blank lines
		const paragraphs = [];
		let buf = [];
		for (const lt of lineTexts) {
			if (lt.trim().length === 0) {
				if (buf.length) {
					paragraphs.push(buf.join(' '));
					buf = [];
				}
			} else {
				buf.push(lt);
			}
		}
		if (buf.length) paragraphs.push(buf.join(' '));

		for (const pText of paragraphs) {
			const run = IRFactory.createRun(pText, {});
			const para = IRFactory.createParagraph([run], { align: 'left' });
			blocks.push(para);
		}

		// Page break between pages (except after last)
		if (pageNum < pdf.numPages) {
			blocks.push(IRFactory.createPageBreak());
		}
	}

	return IRFactory.createDocument(blocks, { source: 'pdf', confidence: 0.6, images: [] });
}
/**
 * Intermediate Representation (IR) schema for unified DOCX/PDF processing
 * These typedefs describe the normalized structure we render from.
 */

/**
 * @typedef {'paragraph'|'list'|'table'|'pageBreak'} IRBlockType
 */

/**
 * @typedef {'left'|'center'|'right'|'justify'} IRAlignment
 */

/**
 * @typedef {Object} IRRun
 * @property {string} text
 * @property {boolean=} bold
 * @property {boolean=} italic
 * @property {boolean=} underline
 * @property {boolean=} smallCaps
 * @property {number=} fontSizePt
 * @property {string=} fontFamily
 */

/**
 * @typedef {Object} IRParagraph
 * @property {'paragraph'} type
 * @property {IRRun[]} runs
 * @property {IRAlignment=} align
 * @property {number=} leadingSpaces     // count of leading spaces to preserve
 * @property {string=} styleName         // original style name if any
 * @property {boolean=} isListItem
 * @property {number=} listLevel         // 0-based nesting level
 * @property {string=} listMarker        // '-', '•', '1.', etc. (normalized)
 * @property {number=} spacingBeforePt
 * @property {number=} spacingAfterPt
 * @property {number=} lineHeightMultiple
 */

/**
 * @typedef {Object} IRTableCell
 * @property {IRParagraph[]} content
 * @property {number=} widthPct           // preferred width percentage (0-100)
 * @property {IRAlignment=} align
 * @property {boolean=} header
 */

/**
 * @typedef {Object} IRTableRow
 * @property {IRTableCell[]} cells
 */

/**
 * @typedef {Object} IRTable
 * @property {'table'} type
 * @property {IRTableRow[]} rows
 * @property {number=} widthPct
 * @property {boolean=} borderCollapse
 * @property {string=} styleName
 */

/**
 * @typedef {Object} IRImage
 * @property {string} id
 * @property {string} alt
 * @property {number} widthPx
 * @property {number} heightPx
 * @property {string=} dataUrl
 */

/**
 * @typedef {Object} IRPageBreak
 * @property {'pageBreak'} type
 */

/**
 * @typedef {Object} IRDocument
 * @property {Array<IRParagraph|IRTable|IRPageBreak>} blocks
 * @property {'docx'|'pdf'} source
 * @property {number=} confidence    // 0..1 (used for PDF extraction confidence)
 * @property {IRImage[]=} images
 * @property {Object.<string, any>=} meta
 */

/**
 * Minimal IR factory with safe defaults
 */
const IRFactory = {
	createRun(text, opts) {
		const o = opts || {};
		return {
			text: typeof text === 'string' ? text : '',
			bold: !!o.bold,
			italic: !!o.italic,
			underline: !!o.underline,
			smallCaps: !!o.smallCaps,
			fontSizePt: typeof o.fontSizePt === 'number' ? o.fontSizePt : undefined,
			fontFamily: o.fontFamily
		};
	},
	createParagraph(runs, opts) {
		const o = opts || {};
		return {
			type: 'paragraph',
			runs: Array.isArray(runs) ? runs : [],
			align: o.align,
			leadingSpaces: typeof o.leadingSpaces === 'number' ? o.leadingSpaces : undefined,
			styleName: o.styleName,
			isListItem: !!o.isListItem,
			listLevel: typeof o.listLevel === 'number' ? o.listLevel : undefined,
			listMarker: o.listMarker,
			spacingBeforePt: typeof o.spacingBeforePt === 'number' ? o.spacingBeforePt : undefined,
			spacingAfterPt: typeof o.spacingAfterPt === 'number' ? o.spacingAfterPt : undefined,
			lineHeightMultiple: typeof o.lineHeightMultiple === 'number' ? o.lineHeightMultiple : undefined
		};
	},
	createTableCell(content, opts) {
		const o = opts || {};
		return {
			content: Array.isArray(content) ? content : [],
			widthPct: typeof o.widthPct === 'number' ? o.widthPct : undefined,
			align: o.align,
			header: !!o.header
		};
	},
	createTableRow(cells) {
		return {
			cells: Array.isArray(cells) ? cells : []
		};
	},
	createTable(rows, opts) {
		const o = opts || {};
		return {
			type: 'table',
			rows: Array.isArray(rows) ? rows : [],
			widthPct: typeof o.widthPct === 'number' ? o.widthPct : undefined,
			borderCollapse: o.borderCollapse !== false, // default true
			styleName: o.styleName
		};
	},
	createPageBreak() {
		return { type: 'pageBreak' };
	},
	createDocument(blocks, opts) {
		const o = opts || {};
		return {
			blocks: Array.isArray(blocks) ? blocks : [],
			source: o.source === 'pdf' ? 'pdf' : 'docx',
			confidence: typeof o.confidence === 'number' ? o.confidence : undefined,
			images: Array.isArray(o.images) ? o.images : undefined,
			meta: o.meta || {}
		};
	}
};

// Expose IRFactory for debugging and for other modules
window.NcIR = IRFactory;

// ------------------------
// Tag/Function tokenizer and parser to AST
// ------------------------

/**
 * @typedef {'text'|'tag'|'func'} ASTNodeType
 */

/**
 * @typedef {Object} ASTText
 * @property {'text'} type
 * @property {string} value
 */

/**
 * @typedef {Object} ASTTag
 * @property {'tag'} type
 * @property {string} name   // inside {[...]} e.g., 'M558' or 'plsMatrix.CompanyName'
 */

/**
 * @typedef {Object} ASTFunc
 * @property {'func'} type
 * @property {string} name    // Money, Math, Compress, etc.
 * @property {ASTNode[]} args // positional args (already split on commas where applicable)
 * @property {string[]=} pipes // optional pipe modifiers e.g., ['Money']
 */

/**
 * @typedef {ASTText|ASTTag|ASTFunc} ASTNode
 */

const TagParser = (function () {
	function isWhitespace(ch) {
		return ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r';
	}
	function parse(input) {
		let i = 0;
		/** @type {ASTNode[]} */
		const nodes = [];
		function peek() { return input[i]; }
		function next() { return input[i++]; }
		function eof() { return i >= input.length; }

		function parseText(untilChars) {
			let buf = '';
			while (!eof()) {
				const ch = peek();
				if (untilChars && untilChars.includes(ch)) break;
				// possible start of tag or function
				if (ch === '{') break;
				buf += next();
			}
			if (buf.length) nodes.push({ type: 'text', value: buf });
		}

		function parseBraced() {
			// assumes current char is '{'
			next(); // consume '{'
			// Detect tag: {[
			if (peek() === '[') {
				next(); // consume '['
				let name = '';
				while (!eof()) {
					const ch = next();
					if (ch === ']') {
						if (peek() !== '}') throw new Error('Tag missing closing }');
						next(); // consume '}'
						nodes.push({ type: 'tag', name });
						return;
					}
					name += ch;
				}
				throw new Error('Unclosed tag');
			}

			// Otherwise parse function-like: Name( ... )
			let fname = '';
			while (!eof()) {
				const ch = peek();
				if (ch === '(') {
					next(); // consume '('
					const { args, pipes } = parseFuncArgs();
					// expect closing ) then }
					if (peek() !== ')') throw new Error('Function missing )');
					next(); // consume ')'
					if (peek() !== '}') throw new Error('Function missing }');
					next(); // consume '}'
					nodes.push({ type: 'func', name: fname.trim(), args, pipes: pipes.length ? pipes : undefined });
					return;
				}
				if (ch === '}') {
					// treat as literal?
					next();
					nodes.push({ type: 'text', value: '{' + fname + '}' });
					return;
				}
				fname += next();
			}
			throw new Error('Unclosed function');
		}

		function parseFuncArgs() {
			/** @type {ASTNode[]} */ const outArgs = [];
			/** @type {string[]} */ const pipes = [];
			let current = '';
			let depth = 0;
			while (!eof()) {
				const ch = peek();
				if (ch === '(' || ch === '{' || ch === '[') {
					depth++; current += next(); continue;
				}
				if (ch === ')' && depth > 0) {
					depth--; current += next(); continue;
				}
				if (ch === '|' && depth === 0) {
					// flush current as argument (if any)
					if (current.trim().length) {
						outArgs.push(...parseInline(current));
						current = '';
					}
					next(); // consume '|'
					// parse pipe token until comma or ')'
					let pipe = '';
					while (!eof()) {
						const c2 = peek();
						if (c2 === ',' || c2 === ')') break;
						pipe += next();
					}
					if (pipe.trim().length) pipes.push(pipe.trim());
					continue;
				}
				if (ch === ',' && depth === 0) {
					// end of one argument
					outArgs.push(...parseInline(current));
					current = '';
					next();
					continue;
				}
				if (ch === ')') {
					// end of args
					if (current.trim().length) {
						outArgs.push(...parseInline(current));
					}
					return { args: outArgs, pipes };
				}
				current += next();
			}
			throw new Error('Unclosed function arguments');
		}

		function parseInline(src) {
			// parse a mini-expression that may contain nested tags/functions
			const saved = i;
			const savedInput = input;
			// Temporarily parse using a child parser
			let j = 0;
			const local = [];
			function Lpeek() { return src[j]; }
			function Lnext() { return src[j++]; }
			function Leof() { return j >= src.length; }
			function pushText(value) { if (value) local.push({ type: 'text', value }); }
			let buf = '';
			while (!Leof()) {
				const ch = Lpeek();
				if (ch === '{') {
					// flush text
					pushText(buf);
					buf = '';
					// parse a braced sequence with the parent parser to reuse logic
					// Rebind parser state
					input = src;
					i = j;
					parseBraced();
					// collect last added node
					local.push(nodes.pop());
					// restore state
					j = i;
					input = savedInput;
					i = saved;
					continue;
				}
				buf += Lnext();
			}
			pushText(buf);
			return local.filter(Boolean);
		}

		while (!eof()) {
			parseText(['{']);
			if (!eof()) {
				if (peek() === '{') {
					parseBraced();
				}
			}
		}
		return nodes;
	}
	return { parse };
})();

// Expose for debugging
window.NcTagParser = TagParser;

// ------------------------
// IR → HTML renderer
// ------------------------

/**
 * Escapes HTML entities
 * @param {string} s
 */
function esc(s) {
	return s
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

/**
 * Render inline runs into HTML string
 * @param {IRRun[]} runs
 */
function renderRuns(runs) {
	let out = '';
	for (const r of runs) {
		let t = esc(r.text || '');
		if (r.underline) t = '<u>' + t + '</u>';
		if (r.italic) t = '<i>' + t + '</i>';
		if (r.bold) t = '<b>' + t + '</b>';
		out += t;
	}
	return out;
}

/**
 * Joins run text without inline styles; used to protect tags/functions from splitting
 * @param {IRRun[]} runs
 */
function joinRunsText(runs) {
	let s = '';
	for (const r of (runs || [])) {
		if (r && typeof r.text === 'string') s += r.text;
	}
	return s;
}

/**
 * Light normalization to avoid broken placeholders
 * @param {string} s
 */
function normalizeTagText(s) {
	// Collapse spaces inside braces and brackets minimally
	return s
		.replace(/\r/g, '')
		.replace(/\u00A0/g, ' ')
		.replace(/\s+\}/g, '}')
		.replace(/\{\s+/g, '{')
		.replace(/\[\s+/g, '[')
		.replace(/\s+\]/g, ']')
		.replace(/\|\s+/g, '|')
		.replace(/\s+\|/g, '|');
}

/**
 * @param {IRParagraph} para
 */
function renderParagraph(para) {
	// Apply style-map class if available
	let classAttr = '';
	if (para.styleName && window.NcStyleMap && window.NcStyleMap.paragraph) {
		const m = window.NcStyleMap.paragraph[para.styleName];
		if (m && m.class) classAttr = ' class="' + m.class + '"';
	}
	const styles = [];
	if (para.align && para.align !== 'left') styles.push('text-align:' + para.align);
	let content = '';
	const joined = joinRunsText(para.runs || []);
	// If content contains placeholders/functions, avoid inline styling to prevent splits
	if (joined.includes('{')) {
		content = esc(normalizeTagText(joined));
	} else {
		content = renderRuns(para.runs || []);
	}
	// leading spaces: convert first N to &nbsp;
	if (typeof para.leadingSpaces === 'number' && para.leadingSpaces > 0) {
		const leading = '&nbsp;'.repeat(para.leadingSpaces);
		content = leading + content;
	}
	const styleAttr = styles.length ? ' style="' + styles.join(';') + '"' : '';
	return '<div' + classAttr + styleAttr + '>' + content + '</div>';
}

/**
 * @param {IRTable} table
 */
function renderTable(table) {
	const width = typeof table.widthPct === 'number' ? table.widthPct : 100;
	const collapse = table.borderCollapse !== false;
	const tableStyle = 'width:' + width + '%;' + (collapse ? 'border-collapse:collapse;' : '');
	let classAttr = '';
	if (table.styleName && window.NcStyleMap && window.NcStyleMap.table) {
		const m = window.NcStyleMap.table[table.styleName];
		if (m && m.class) classAttr = ' class="' + m.class + '"';
	}
	let html = '<table' + classAttr + ' style="' + tableStyle + '"><tbody>';
	for (const row of (table.rows || [])) {
		html += '<tr>';
		for (const cell of (row.cells || [])) {
			const cellStyles = ['vertical-align:top'];
			if (typeof cell.widthPct === 'number') cellStyles.push('width:' + cell.widthPct + '%');
			if (cell.align && cell.align !== 'left') cellStyles.push('text-align:' + cell.align);
			const tag = cell.header ? 'th' : 'td';
			html += '<' + tag + ' style="' + cellStyles.join(';') + '">';
			for (const p of (cell.content || [])) {
				html += renderParagraph(p);
			}
			html += '</' + tag + '>';
		}
		html += '</tr>';
	}
	html += '</tbody></table>';
	return html;
}

/**
 * Groups consecutive list-item paragraphs into a bullet table
 * @param {Array<IRParagraph|IRTable|IRPageBreak>} blocks
 * @returns {Array<IRParagraph|IRTable|IRPageBreak>}
 */
function groupListItems(blocks) {
	const out = [];
	let buffer = [];
	function flushBuffer() {
		if (!buffer.length) return;
		// Build bullet table rows: [bullet][content]
		const rows = buffer.map(p => {
			const bullet = (p.listMarker && p.listMarker.trim()) || '•';
			return {
				cells: [
					{ content: [IRFactory.createParagraph([IRFactory.createRun(bullet)])], widthPct: 3, align: 'center' },
					{ content: [p], widthPct: 97 }
				]
			};
		});
		out.push(IRFactory.createTable(rows, { widthPct: 100, borderCollapse: true, styleName: 'BulletTable' }));
		buffer = [];
	}
	for (const b of blocks) {
		if (b && b.type === 'paragraph' && b.isListItem) {
			buffer.push(b);
			continue;
		}
		flushBuffer();
		out.push(b);
	}
	flushBuffer();
	return out;
}

/**
 * @param {IRDocument} ir
 * @returns {string} html
 */
function renderIRToHtml(ir) {
	const parts = [];
	// Preprocess blocks for generic structures (e.g., list grouping)
	const blocks = groupListItems(ir.blocks || []);
	for (const block of blocks) {
		if (block.type === 'paragraph') {
			parts.push(renderParagraph(block));
			parts.push('<br>');
		} else if (block.type === 'table') {
			parts.push(renderTable(block));
			parts.push('<br>');
		} else if (block.type === 'pageBreak') {
			parts.push('<div style="page-break-after:always"></div>');
		}
	}
	return parts.join('\n');
}

// Expose renderer
window.NcRenderer = { renderIRToHtml };