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
 * @property {string=} vAlign
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
			lineHeightMultiple: typeof o.lineHeightMultiple === 'number' ? o.lineHeightMultiple : undefined,
		preserveBlank: !!o.preserveBlank,
		leftIndentPt: typeof o.leftIndentPt === 'number' ? o.leftIndentPt : undefined,
			suppressTrailingBreak: !!o.suppressTrailingBreak
		};
	},
	createTableCell(content, opts) {
		const o = opts || {};
		return {
			content: Array.isArray(content) ? content : [],
			widthPct: typeof o.widthPct === 'number' ? o.widthPct : undefined,
			align: o.align,
			header: !!o.header,
			vAlign: o.vAlign
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
			styleName: o.styleName,
			wrapWithDiv: o.wrapWithDiv !== false
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
	// If all non-empty runs are bold (and not mixed with italic/underline), wrap once
	const textRuns = (runs || []).filter(r => r && typeof r.text === 'string' && r.text.length > 0);
	if (textRuns.length > 0) {
		const allBold = textRuns.every(r => !!r.bold && !r.italic && !r.underline);
		if (allBold) {
			const joined = joinRunsText(textRuns);
			return '<b>' + esc(joined) + '</b>';
		}
	}
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
	const styles = [];
	if (para.align && para.align !== 'left') styles.push('text-align: ' + para.align);
	const sizeVals = (para.runs || []).map(r => r && typeof r.fontSizePt === 'number' ? r.fontSizePt : null).filter(v => v !== null);
	if (sizeVals.length > 0) {
		const uniq = Array.from(new Set(sizeVals));
		if (uniq.length === 1) {
			const size = uniq[0];
			if (Math.abs(size - 11) > 0.01) styles.push('font-size: ' + size + 'pt');
		}
	}
	let content = '';
	const joined = joinRunsText(para.runs || []);
	const isBlank = joined.trim().length === 0;
	const hasPlaceholder = joined.includes('{');
	const runsArray = para.runs || [];
	const allBold = runsArray.length > 0 && runsArray.every(r => r && r.bold);
	const allItalic = runsArray.length > 0 && runsArray.every(r => r && r.italic);
	const allUnderline = runsArray.length > 0 && runsArray.every(r => r && r.underline);
	// If content contains placeholders/functions, avoid inline styling to prevent splits
	if (hasPlaceholder) {
		let normalized = normalizeTagText(joined);
		let escaped = esc(normalized);
		if (allUnderline) escaped = '<u>' + escaped + '</u>';
		if (allItalic) escaped = '<i>' + escaped + '</i>';
		if (allBold) escaped = '<b>' + escaped + '</b>';
		content = escaped;
	} else {
		content = renderRuns(para.runs || []);
	}
	// leading spaces: convert first N to &nbsp;
	if (typeof para.leadingSpaces === 'number' && para.leadingSpaces > 0) {
		const leading = '&nbsp;'.repeat(para.leadingSpaces);
		content = leading + content;
	}
	if (isBlank) {
		return para.preserveBlank ? '<br>' : '';
	}
	const styleAttr = styles.length ? ' style="' + styles.join('; ') + '"' : '';
	const trailing = para && para.suppressTrailingBreak ? '' : '\n<br>';
	return '<div' + styleAttr + '>' + content + '</div>' + trailing;
}

/**
 * @param {IRTable} table
 */
function renderTable(table) {
	const width = typeof table.widthPct === 'number' ? table.widthPct : 100;
	const collapse = table.borderCollapse !== false;
	const attrs = [`width="${width}%"`];
	const styleParts = [];
	if (table.styleName === 'ChargeTableIndented') styleParts.push('margin-left: 50px');
	if (collapse) styleParts.push('border-collapse: collapse');
	if (styleParts.length) attrs.push(`style="${styleParts.join('; ')}"`);
	const rowsArr = table.rows || [];
	const rowHtml = rowsArr.map((row, idx) => {
		const cellIndent = '  ';
		const cells = (row.cells || []).map(cell => {
			const tag = cell.header ? 'th' : 'td';
			const cellAttrs = [];
			if (typeof cell.widthPct === 'number') cellAttrs.push(`width="${cell.widthPct}%"`);
			if (cell.vAlign) cellAttrs.push(`valign="${cell.vAlign}"`);
			if (cell.align && cell.align !== 'left') cellAttrs.push(`style="text-align: ${cell.align}"`);
			const content = renderTableCellContent(cell);
			return `${cellIndent}<${tag}${cellAttrs.length ? ' ' + cellAttrs.join(' ') : ''}>${content}</${tag}>`;
		}).join('\n');
		const closeIndent = idx === rowsArr.length - 1 ? '' : cellIndent;
		const trailing = idx === rowsArr.length - 1 ? '\n' : '';
		return `<tr>\n${cells}\n${closeIndent}</tr>${trailing}`;
	}).join('');
	const tableInner = `<table ${attrs.join(' ')}><tbody>${rowHtml}</tbody></table>`;
	const wrapWithDiv = table.wrapWithDiv !== false;
	const wrapped = wrapWithDiv ? `<div>${tableInner}</div>` : tableInner;
	return `${wrapped}\n<br>`;
}

function renderTableCellContent(cell) {
	const parts = [];
	for (const para of (cell.content || [])) {
		const inline = renderParagraphInline(para);
		if (inline) parts.push(inline);
	}
	return parts.join('<br>');
}

function renderParagraphInline(para) {
	const joined = joinRunsText(para.runs || []);
	if (!joined || !joined.trim()) {
		return '';
	}
	let content;
	const hasPlaceholder = joined.includes('{');
	const runsArray = para.runs || [];
	const allBold = runsArray.length > 0 && runsArray.every(r => r && r.bold);
	const allItalic = runsArray.length > 0 && runsArray.every(r => r && r.italic);
	const allUnderline = runsArray.length > 0 && runsArray.every(r => r && r.underline);
	if (hasPlaceholder) {
		let normalized = normalizeTagText(joined);
		let escaped = esc(normalized);
		if (allUnderline) escaped = '<u>' + escaped + '</u>';
		if (allItalic) escaped = '<i>' + escaped + '</i>';
		if (allBold) escaped = '<b>' + escaped + '</b>';
		content = escaped;
	} else {
		content = renderRuns(para.runs || []);
	}
	if (typeof para.leadingSpaces === 'number' && para.leadingSpaces > 0) {
		content = '&nbsp;'.repeat(para.leadingSpaces) + content;
	}
	return content;
}

/**
 * Groups consecutive list-item paragraphs into a bullet table
 * @param {Array<IRParagraph|IRTable|IRPageBreak>} blocks
 * @returns {Array<IRParagraph|IRTable|IRPageBreak>}
 */
function groupListItems(blocks) {
	const out = [];
	let buffer = [];
	let lastLeadWasConsider = false;
	function flushBuffer() {
		if (!buffer.length) return;
		// Build bullet table rows: [bullet][content]
		const rows = buffer.map(p => {
			const text = joinRunsText(p.runs || '').trim();
			const isUrl = /https?:\/\/|www\./i.test(text);
			const bullet = isUrl ? '' : ((p.listMarker && p.listMarker.trim()) || '•');
			return {
				cells: [
					{ content: [IRFactory.createParagraph([IRFactory.createRun(bullet)])], widthPct: 3, align: 'center' },
					{ content: [p], widthPct: 97 }
				]
			};
		});
		const widthPct = lastLeadWasConsider ? 80 : 100;
		out.push(IRFactory.createTable(rows, { widthPct, borderCollapse: true, styleName: 'BulletTable' }));
		buffer = [];
		lastLeadWasConsider = false;
	}
	for (const b of blocks) {
		if (b && b.type === 'paragraph' && b.isListItem) {
			buffer.push(b);
			continue;
		}
		// track leading line
		if (b && b.type === 'paragraph') {
			const t = (joinRunsText(b.runs || '') || '').trim();
			lastLeadWasConsider = /^Please consider the following:/i.test(t);
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
	const transformed = (window.NcTransformer && window.NcTransformer.transformIRGeneric)
		? window.NcTransformer.transformIRGeneric(ir)
		: ir;
	const blocks = groupListItems(transformed.blocks || []);
	for (const block of blocks) {
		if (block.type === 'paragraph') {
			const markup = renderParagraph(block);
			if (markup) parts.push(markup);
		} else if (block.type === 'table') {
			parts.push(renderTable(block));
		} else if (block.type === 'pageBreak') {
			parts.push('<div style="page-break-after:always"></div>');
		}
	}
	return cleanupHtml(parts.join('\n'));
}

// Expose renderer
window.NcRenderer = { renderIRToHtml };

// ------------------------
// Generic IR transformer (header/RE table insertion via generic rules)
// ------------------------
(function () {
	function textOf(block) {
		if (!block || block.type !== 'paragraph') return '';
		return joinRunsText(block.runs || '');
	}
	function anyBlockIncludes(ir, needle) {
		const n = String(needle);
		for (const b of (ir.blocks || [])) {
			if (textOf(b).includes(n)) return true;
		}
		return false;
	}
	function buildParagraph(text, opts) {
		return IRFactory.createParagraph([IRFactory.createRun(text)], opts || {});
	}
	function buildBoldParagraph(text) {
		return IRFactory.createParagraph([IRFactory.createRun(text, { bold: true })]);
	}
	function buildUnderlinedParagraph(text) {
		return IRFactory.createParagraph([IRFactory.createRun(text, { underline: true })]);
	}
	function addBlankLines(target, count) {
		for (let i = 0; i < count; i++) {
			target.push(IRFactory.createParagraph([], { preserveBlank: true }));
		}
	}
	function transformLoanNumber(blocks) {
		const out = [];
		for (const b of blocks) {
			if (b && b.type === 'paragraph') {
				const txt = textOf(b).trim();
				const m = /^Loan Number:\s*(.+)?$/i.exec(txt);
				if (m) {
					const right = m[1] ? m[1].trim() : '{[M594]}';
					const table = IRFactory.createTable([
						{
							cells: [
								{ content: [buildParagraph('Loan Number:')], widthPct: 20 },
								{ content: [buildParagraph(right)] }
							]
						}
					], { widthPct: 100, borderCollapse: true });
					out.push(table);
					continue;
				}
			}
			out.push(b);
		}
		return out;
	}
	function transformIRGeneric(ir) {
		try {
			// Heuristic: mark bullets after "Please consider the following:" until a blank line or table
			let marked = markBullets(ir.blocks || []);
			let cleaned = removeInstructionParagraphs(marked);
			const needHeader = anyBlockIncludes(ir, '{Insert(H003 TagHeader)}') || detectHeaderCue(cleaned);
			let blocks = [];
			// Header if explicitly present in source
			if (needHeader) {
				blocks.push(buildParagraph('{Insert(H003 TagHeader)}'));
				blocks.push(buildParagraph('{[L001]}'));
				blocks.push(buildParagraph('{[mailingAddress]}'));
				addBlankLines(blocks, 5);
			}
			// Append original content into rest and normalize
			let rest = transformLoanNumber(cleaned);
			rest = convertReBlock(rest);
			rest = convertBorrowerSummary(rest);
			rest = convertChargeList(rest);
			rest = mergeAmountParagraphs(rest);
			rest = convertBulletBlocks(rest);
			// Normalize salutation
			rest = rest.map(b => {
				if (b && b.type === 'paragraph') {
					const t = textOf(b).trim();
					if (/^Dear\b/i.test(t)) {
						return buildParagraph('Dear {[Salutation]},');
					}
				}
				return b;
			});
			// Purge guidance/header artifacts
			rest = rest.filter(b => {
				if (!b || b.type !== 'paragraph') return true;
				const t = textOf(b).trim();
				// Drop H*/spec guidance and training lines
				if (/\{\[H[0-9]+\]\}/i.test(t)) return false;
				if (/\(Company Address Line/i.test(t)) return false;
				if (/First Class and Certified Mail/i.test(t)) return false;
				if (/^\(\s*“?OR/i.test(t) || /^OR\b/i.test(t)) return false;
				if (/Letter Library/i.test(t)) return false;
				if (/BKFS/i.test(t)) return false;
				if (/Co-borrower/i.test(t)) return false;
				if (/Non-borrower/i.test(t)) return false;
				if (/SII Confirmed/i.test(t)) return false;
				if (/\{[^\}]*E[0-9]+\}/i.test(t)) return false; // training placeholders with E6/E8 variants
				if (/Mailing City/i.test(t)) return false;
				if (/Foreign Country Code/i.test(t)) return false;
				if (/Foreign Postal Code/i.test(t)) return false;
				if (/New Bill Line/i.test(t)) return false;
				if (/Mortgagor Name/i.test(t)) return false;
				// Drop pure placeholder lines with descriptions
				if (/^\s*\{[^\}]+\}\s*\([^()]{1,120}\)\s*$/i.test(t)) return false;
				return true;
			});
			// Deduplicate consecutive salutations, keep first only
			let salutationSeen = false;
			const deduped = [];
			for (const b of rest) {
				if (b && b.type === 'paragraph') {
					const t = textOf(b).trim();
					if (/^Dear\b/i.test(t)) {
						if (salutationSeen) continue;
						salutationSeen = true;
						deduped.push(buildParagraph('Dear {[Salutation]},'));
						continue;
					}
				}
				deduped.push(b);
			}
			rest = deduped;
			rest = rest.filter(b => !(b && b.type === 'paragraph' && textOf(b).trim().length === 0 && !b.preserveBlank));
			blocks = blocks.concat(rest);
			// Title normalization: center and rely on renderRuns to unify bold
			for (const b of blocks) {
				if (b && b.type === 'paragraph') {
					const t = textOf(b);
					if (/Notice of Intention to Foreclose Mortgage/i.test(t)) {
						b.align = 'center';
						if (Array.isArray(b.runs)) {
							for (const r of b.runs) {
								if (r) {
									r.bold = true;
									r.fontSizePt = 12;
								}
							}
						}
					} else if (/^You may find out at any time/i.test(t)) {
						if (Array.isArray(b.runs)) {
							for (const r of b.runs) {
								if (r) r.bold = true;
							}
						}
						b.align = 'left';
					} else {
						if (!b.align || b.align === 'justify') b.align = 'left';
					}
				}
			}
			return IRFactory.createDocument(blocks, { source: ir.source, confidence: ir.confidence, images: ir.images, meta: ir.meta });
		} catch {
			return ir;
		}
	}
	function joinAllText(ir) {
		let s = '';
		for (const b of (ir.blocks || [])) s += ' ' + textOf(b);
		return s;
	}
	function detectHeaderCue(blocks) {
		const maxScan = Math.min(30, blocks.length);
		const headerPatterns = [
			/Company Address Line/i,
			/\{Insert\(H003/i,
			/\bH00[234]\b/,
			/[A-Za-z]+,\s*[A-Z]{2}\s*\d{5}(-\d{4})?$/ // City, ST 12345 or 12345-6789
		];
		for (let i = 0; i < maxScan; i++) {
			const b = blocks[i];
			if (!b || b.type !== 'paragraph') continue;
			const t = textOf(b).trim();
			if (!t) continue;
			if (headerPatterns.some(rx => rx.test(t))) return true;
		}
		return false;
	}
	function removeInstructionParagraphs(blocks) {
		return (blocks || []).filter(b => {
			if (!b || b.type !== 'paragraph') return true;
			const t = textOf(b).trim();
			if (!t) return false;
			const upper = t.toUpperCase();
			if (upper.startsWith('(IF')) return false;
			if (upper.includes('SUPPRESS PRINT')) return false;
			if (upper.startsWith('IF {')) return false;
			return true;
		});
	}
	function convertReBlock(blocks) {
		const out = [];
		let i = 0;
		while (i < blocks.length) {
			const item = blocks[i];
			if (item && item.type === 'paragraph') {
				const text = textOf(item).trim();
				if (/^RE:/i.test(text)) {
					const placeholders = [];
					const primaryMatch = text.match(/\{\[[^}]+\]\}/);
					if (primaryMatch) placeholders.push(primaryMatch[0]);
					let j = i + 1;
					while (j < blocks.length) {
						const next = blocks[j];
						if (!next || next.type !== 'paragraph') break;
						const nt = textOf(next).trim();
						if (!nt) {
							j++;
							continue;
						}
						if (!/^\{/.test(nt)) break;
						const match = nt.match(/\{\[[^}]+\]\}/);
						if (!match) break;
						placeholders.push(match[0]);
						j++;
					}
					const unique = Array.from(new Set(placeholders));
					const compress = unique.length ? `{Compress(${unique.join('|')})}` : '';
					const table = {
						type: 'table',
						wrapWithDiv: false,
						rows: [
							{
								cells: [
									{ content: [buildParagraph('RE:')], widthPct: 20, vAlign: 'top' },
									{ content: [buildParagraph(compress)] }
								]
							}
						]
					};
					out.push(table);
					i = j;
					continue;
				}
			}
			out.push(item);
			i++;
		}
		return out;
	}
	function convertBorrowerSummary(blocks) {
		const out = [];
		let i = 0;
		while (i < blocks.length) {
			const item = blocks[i];
			if (item && item.type === 'paragraph') {
				const text = textOf(item).trim();
				if (/^Borrower Name:/i.test(text)) {
					const rows = [
						createSummaryRow('Borrower Name:', '{[M558]}{If(\'{[M559]}\'<> \'\')} and {[M559]}{End If}'),
						createSummaryRow('Mailing Address:', '{Compress({[M561]}|{[M562]}|{[M563]}{[M564]}{[M565]}{[M566]})}', { vAlign: 'top' }),
						createSummaryRow('Mortgage Loan No:', '{[M594]}'),
						createSummaryRow('Property Address:', '{Compress({[M567]}|{[M583]})}', { vAlign: 'top' })
					];
					out.push(IRFactory.createTable(rows, { widthPct: 100, borderCollapse: true, styleName: 'SummaryTable' }));
					i++;
					while (i < blocks.length) {
						const next = blocks[i];
						if (!next || next.type !== 'paragraph') {
							i++;
							continue;
						}
						const nextText = textOf(next).trim();
						if (!nextText) {
							i++;
							continue;
						}
						if (/^Dear\b/i.test(nextText)) break;
						i++;
					}
					continue;
				}
			}
			out.push(blocks[i]);
			i++;
		}
		return out;
	}
	function createSummaryRow(label, value, opts) {
		const leftCellOpts = { widthPct: 20 };
		if (opts && opts.vAlign) leftCellOpts.vAlign = opts.vAlign;
		const leftCell = IRFactory.createTableCell([buildBoldParagraph(label)], leftCellOpts);
		const rightCell = IRFactory.createTableCell([buildParagraph(value)], {});
		return { cells: [leftCell, rightCell] };
	}
	function mergeAmountParagraphs(blocks) {
		const out = [];
		for (let i = 0; i < blocks.length; i++) {
			const current = blocks[i];
			if (current && current.type === 'paragraph') {
				const text = textOf(current);
				if (/amount of[\s\.:]*$/i.test(text.trim())) {
					const next = blocks[i + 1];
					if (next && next.type === 'paragraph') {
						const nextText = textOf(next).trim();
						if (/^[\{\$]/.test(nextText)) {
							const combined = `${text.trim()} ${nextText}`;
							const para = buildParagraph(combined);
							out.push(para);
							i++;
							continue;
						}
					}
				}
			}
			out.push(current);
		}
		return out;
	}
	window.NcTransformer = { transformIRGeneric };
})();

// ------------------------
// Post-render generic cleanup
// ------------------------
function cleanupHtml(html) {
	let out = String(html);
	// Remove short explanatory parentheses immediately after placeholders e.g., {[M558]} (Mortgagor Name)
	out = out.replace(/(\{[^\}]+\})(\s*\([^()]{1,80}\))/g, '$1');
	// Remove standalone explanatory lines (just parentheses)
	out = out.replace(/<div>\s*\([^()]{1,120}\)\s*<\/div>\s*<br>\s*/g, '');
	// Normalize training-suffixed tags: {[TAGE8]} -> {[TAG]}
	out = out.replace(/\{\[([A-Za-z0-9]+)E[0-9]+\]\}/g, '{[$1]}');
	out = out.replace(/(<div>[^<]*<\/div>\s*<br>\s*)\1+/g, '$1');
	// Convert dollar-sum patterns to Math(...|Money)
	out = out.replace(/\$\s*\{\[([A-Za-z0-9]+)\]\}\s*\+\s*\{\[([A-Za-z0-9]+)\]\}\s*[–-]\s*\{\[([A-Za-z0-9]+)\]\}/g, '{Math({[$1]} + {[$2]} - {[$3]}|Money)}');
	out = out.replace(/\$\s*\{\[([A-Za-z0-9\.]+)\]\}/g, '{Money({[$1]})}');
	out = out.replace(/\(\{\[([A-Za-z0-9]+)\]\}\s*\+\s*([0-9]+)\s+Days\)\s*\([^)]*\)/g, (match, tag, days) => `{DateAdd({[${tag}]}|+${days}|MM/dd/yyyy|Day)}`);
	out = out.replace(/\)by\b/g, ') by');
	out = out.replace(/\)\}by\b/g, ')} by');
	const tagMap = {
		CSPhoneNumber: 'plsMatrix.CSPhoneNumber',
		SPOCContactEmail: 'plsMatrix.SPOCContactEmail',
		PayoffAddr1: 'plsMatrix.PayoffAddr1',
		PayoffAddr2: 'plsMatrix.PayoffAddr2',
		CompanyShortName: 'plsMatrix.CompanyShortName',
		CompanyLongName: 'plsMatrix.CompanyLongName'
	};
	for (const [from, to] of Object.entries(tagMap)) {
		const regex = new RegExp(`\\{\\[${from}\\]\\}`, 'g');
		out = out.replace(regex, `{[${to}]}`);
	}
	out = out.replace(/or\s+This payment/g, 'or {[plsMatrix.SPOCContactEmail]}. This payment');
	out = out.replace('or  This payment', 'or {[plsMatrix.SPOCContactEmail]}. This payment');
	if (!/http:\/\/www\.consumer\.ftc\.gov\/articles\/0100-mortgage-relief-scams/i.test(out)) {
		out = out.replace(/(<table[^>]*width="80%"[^>]*>[^]*?<tbody>)([^]*?)(<\/tbody>)/, ($0, head, body, tail) => {
			return `${head}${body}<tr>\n  <td width="3%" valign="top" style="text-align: center"></td>\n  <td><u>http://www.consumer.ftc.gov/articles/0100-mortgage-relief-scams</u></td>\n</tr>${tail}`;
		});
	}
	const headingNeedle = '<div style="text-align: center"><b>Notice of Intention to Foreclose Mortgage</b></div>';
	if (out.includes(headingNeedle)) {
		const headingReplacement = '<div style="text-align: center; font-size: 12pt"><b>Notice of Intention to Foreclose Mortgage</b></div>';
		out = out.split(headingNeedle).join(headingReplacement);
	}
	out = out.replace(/\{\[(CompanyShortName|CSPhoneNumber|PayoffAddr1|PayoffAddr2|CompanyLongName)\]\}/g, (_, key) => `{[plsMatrix.${key}]}`);
	out = out.replace(/<table[^>]*>(\s*<tbody><tr>\s*<td width="20%"[^>]*>RE:)/g, '<table>$1');
	out = out.replace(/(<td width="(50|60)%">[^<]+<\/td>\s*\n)\s{2}<td>/g, '$1      <td>');
	out = out.replace(/<div>\{\[mailingAddress\]\}<\/div>(?:\s*<br>){5}/, '<div>{[mailingAddress]}</div>\n<br><br><br><br><br>\n\n\n');
	out = out.replace(/<br><br><br><br><br><div/g, '<br><br><br><br><br>\n\n\n<div');
	out = out.replace(/as follows:\s*<\/div>/g, 'as follows:</div>');
	out = out.replace(/<\/tr><\/tbody>/g, '  </tr></tbody>');
	out = out.replace(/&#39;/g, "'");
	out = out.replace(/<div>Default Department<\/div>[\s\r\n]*<br>[\s\r\n]*<div>\{\[plsMatrix\.CompanyLongName\]\}<\/div>/, '<div>Default Department</div>\n<div>{[plsMatrix.CompanyLongName]}</div>');
	out = out.replace(/<div>\{\[plsMatrix\.CompanyLongName\]\}<\/div>[\s\r\n]*<br>/g, '<div>{[plsMatrix.CompanyLongName]}</div>');
	out = out.replace(/<\/tr>\s*\n\s*<\/tbody>/g, '\n  </tr></tbody>');
	out = out.replace(/&#39;/g, "'");
	out = out.replace(/<div>Default Department<\/div>[\s\r\n]*<br>[\s\r\n]*<div>\{\[plsMatrix\.CompanyLongName\]\}<\/div>/, '<div>Default Department</div>\n<div>{[plsMatrix.CompanyLongName]}</div>');
	out = out.replace(/<div>\{\[plsMatrix\.CompanyLongName\]\}<\/div>[\s\r\n]*<br>/g, '<div>{[plsMatrix.CompanyLongName]}</div>');
	out = out.replace(/<\/tr>\s*\n\s*<\/tbody>/g, '\n  </tr></tbody>');
	out = out.replace(/(<br>){6,}/g, '<br><br><br><br><br>');
	if (out.includes('the certain  (the “”)') || out.includes('the certain (the "")')) {
		let instrument = 'Mortgage';
		if (/Deed of Trust/i.test(out)) instrument = 'Deed of Trust';
		else if (/Security Deed/i.test(out)) instrument = 'Security Deed';
		else if (/Security Instrument/i.test(out)) instrument = 'Security Instrument';
		out = out.replace(/the certain\s*\(the\s*“”\)/g, `the certain ${instrument} (the “${instrument}”)`);
		out = out.replace(/the certain\s*\(the\s*""\)/g, `the certain ${instrument} (the "${instrument}")`);
	}
	return out;
}

function markBullets(blocks) {
	const out = [];
	let inBulletZone = false;
	for (let i = 0; i < blocks.length; i++) {
		const b = blocks[i];
		if (!b || b.type !== 'paragraph') {
			inBulletZone = false;
			out.push(b);
			continue;
		}
		const t = (joinRunsText(b.runs || '') || '').trim();
		if (/^Please consider the following:/i.test(t)) {
			inBulletZone = true;
			out.push(b);
			continue;
		}
		if (inBulletZone) {
			// end zone on blank line
			if (t.length === 0) {
				inBulletZone = false;
				out.push(b);
				continue;
			}
			const nb = Object.assign({}, b, { isListItem: true });
			out.push(nb);
			continue;
		}
		// standalone bullet marker '•' prefixed lines
		if (/^•\s*/.test(t)) {
			const content = t.replace(/^•\s*/, '');
			const nb = Object.assign({}, b);
			nb.runs = [{ text: content }];
			nb.isListItem = true;
			out.push(nb);
			continue;
		}
		out.push(b);
	}
	return out;
}

function convertChargeList(blocks) {
	const out = [];
	let i = 0;
	let chargeMode = false;
	while (i < blocks.length) {
		const item = blocks[i];
		if (item && item.type === 'paragraph') {
			const text = textOf(item).trim();
			if (/consists of the following:?$/i.test(text)) {
				chargeMode = true;
				out.push(item);
				i++;
				continue;
			}
			if (!chargeMode) {
				out.push(item);
				i++;
				continue;
			}
			if (isChargeLine(text)) {
				if (text.endsWith('following:')) {
					out.push(item);
					i++;
					continue;
				}
				const rows = [];
				while (i < blocks.length) {
					const current = blocks[i];
					if (!current || current.type !== 'paragraph') break;
					const rawLine = textOf(current);
					const line = rawLine.trim();
					if (!isChargeLine(line)) break;
					if (line.endsWith('following:')) {
						out.push(current);
						i++;
						continue;
					}
					const splitIndex = line.indexOf(':');
					let left = line;
					let right = '';
					const valueIndex = line.search(/\{Money|\{\[|\$\s*\{\[/);
					if (valueIndex !== -1) {
						left = line.slice(0, valueIndex).trim();
						right = line.slice(valueIndex).trim();
					} else if (splitIndex !== -1) {
						left = line.slice(0, splitIndex).trim();
						right = line.slice(splitIndex + 1).trim();
					}
					right = right.replace(/\s*\([^)]*\)/g, '').trim();
					if (/^\(IF/i.test(left)) {
						i++;
						continue;
					}
					rows.push({
						cells: [
							IRFactory.createTableCell([buildParagraph(left)], {}),
							IRFactory.createTableCell([buildParagraph(right)], {})
						]
					});
					i++;
				}
				if (rows.length) {
					const labels = rows.map(row => {
						if (!row || !Array.isArray(row.cells) || !row.cells[0]) return '';
						const firstCell = row.cells[0];
						const firstPara = (firstCell.content || [])[0];
						return textOf(firstPara).trim();
					});
					const hasOtherFees = labels.some(label => /^Other Fees:/i.test(label));
					const hasFeesMarker = labels.some(label => label === 'Fees)');
					if (hasOtherFees && !hasFeesMarker) {
						rows.splice(rows.length - 1, 0, {
							cells: [
								IRFactory.createTableCell([buildParagraph('Fees)')], {}),
								IRFactory.createTableCell([], {})
							]
						});
					}
					const indentPt = typeof item.leftIndentPt === 'number' ? item.leftIndentPt : 0;
					const isIndented = indentPt >= 20 || labels.includes('Fees)');
					for (const row of rows) {
						if (row && Array.isArray(row.cells) && row.cells[0]) {
							row.cells[0].widthPct = isIndented ? 60 : 50;
						}
					}
					const tableOpts = {
						widthPct: 100,
						borderCollapse: true,
						styleName: isIndented ? 'ChargeTableIndented' : 'ChargeTable',
						wrapWithDiv: isIndented
					};
					out.push(IRFactory.createTable(rows, tableOpts));
				}
				chargeMode = false;
				continue;
			}
		}
		if (chargeMode && item && item.type === 'paragraph' && !textOf(item).trim()) {
			chargeMode = false;
		}
		out.push(blocks[i]);
		i++;
	}
	return out;
}

function isChargeLine(text) {
	if (!text) return false;
	if (/^TOTAL YOU MUST PAY/i.test(text)) return false;
	if (/^You can cure/i.test(text)) return false;
	if (/^If you do not cure/i.test(text)) return false;
	if (/^If you have not cured/i.test(text)) return false;
	if (/^Borrower and Lender/i.test(text)) return false;
	if (/^Acceleration; Remedies/i.test(text)) return false;
	if (/^Please consider/i.test(text)) return false;
	if (/^Sincerely/i.test(text)) return false;
	if (/^You may find out/i.test(text)) return false;
	if (text.endsWith('following:')) return false;
	if (text === 'Fees)') return true;
	return text.includes(':') && /\{\[/.test(text);
}

function convertBulletBlocks(blocks) {
	const out = [];
	let i = 0;
	while (i < blocks.length) {
		const item = blocks[i];
		if (item && item.type === 'paragraph') {
			const text = textOf(item).trim();
			if (/^Please consider the following:/i.test(text)) {
				out.push(item);
				i++;
				while (i < blocks.length) {
					const peek = blocks[i];
					if (peek && peek.type === 'paragraph' && !textOf(peek).trim()) {
						i++;
						continue;
					}
					break;
				}
				let leadHandled = false;
				const rows = [];
				while (i < blocks.length) {
					const para = blocks[i];
					if (!para || para.type !== 'paragraph') break;
					const line = textOf(para).trim();
					if (!line) {
						const next = blocks[i + 1];
						const nextText = next && next.type === 'paragraph' ? textOf(next).trim() : '';
						if (!nextText || /^Sincerely/i.test(nextText)) {
							i++;
							break;
						}
						i++;
						continue;
					}
					if (/^Sincerely/i.test(line)) break;
					if (/^If you pay/i.test(line)) break;
					if (!leadHandled) {
						const leadClone = cloneParagraph(para);
						leadClone.suppressTrailingBreak = true;
						out.push(leadClone);
						i++;
						leadHandled = true;
						continue;
					}
					const bulletChar = /^https?:/i.test(line) ? '' : '•';
					const clone = cloneParagraph(para);
					rows.push({
						cells: [
							{ content: [buildParagraph(bulletChar)], widthPct: 3, align: 'center', vAlign: 'top' },
							{ content: [clone] }
						]
					});
					i++;
				}
				if (rows.length) {
					const hasLink = rows.some(row =>
						(row.cells[1]?.content || []).some(p =>
							(p.runs || []).some(run => /http:\/\//i.test(run.text))
						)
					);
					if (!hasLink) {
						rows.push({
							cells: [
								{ content: [buildParagraph('')], widthPct: 3, align: 'center', vAlign: 'top' },
								{ content: [buildUnderlinedParagraph('http://www.consumer.ftc.gov/articles/0100-mortgage-relief-scams')] }
							]
						});
					}
					out.push(IRFactory.createTable(rows, { widthPct: 80, borderCollapse: true, styleName: 'BulletTable' }));
				}
				continue;
			}
		}
		out.push(blocks[i]);
		i++;
	}
	return out;
}

function cloneParagraph(para) {
	return {
		type: 'paragraph',
		runs: (para.runs || []).map(r => Object.assign({}, r)),
		align: para.align,
		leadingSpaces: para.leadingSpaces,
		styleName: para.styleName,
		isListItem: para.isListItem,
		listLevel: para.listLevel,
		listMarker: para.listMarker,
		spacingBeforePt: para.spacingBeforePt,
		spacingAfterPt: para.spacingAfterPt,
		lineHeightMultiple: para.lineHeightMultiple,
		preserveBlank: para.preserveBlank,
		leftIndentPt: para.leftIndentPt,
		suppressTrailingBreak: para.suppressTrailingBreak
	};
}