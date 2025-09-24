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
        if (file && this.isWordDocument(file)) {
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
        if (files.length > 0 && this.isWordDocument(files[0])) {
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
            const formattedText = await WordFormatter.extractTextFromWord(file);
            this.displayResult(formattedText);
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
    new WordFormatter();
});