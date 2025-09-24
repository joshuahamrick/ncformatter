// Word Document Formatter - New Version with Python Backend

class WordFormatter {
    constructor() {
        this.initializeElements();
        this.setupEventListeners();
    }

    initializeElements() {
        this.fileInput = document.getElementById('fileInput');
        this.dropZone = document.getElementById('dropZone');
        this.resultDiv = document.getElementById('resultContent');
        this.downloadBtn = document.getElementById('downloadBtn');
        this.processingDiv = document.getElementById('processing');
    }

    setupEventListeners() {
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        this.dropZone.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.dropZone.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        this.dropZone.addEventListener('drop', (e) => this.handleDrop(e));
        this.downloadBtn.addEventListener('click', () => this.downloadResult());
    }

    handleFileSelect(event) {
        const files = event.target.files;
        if (files.length > 0) {
            this.processFile(files[0]);
        }
    }

    handleDragOver(event) {
        event.preventDefault();
        this.dropZone.classList.add('dragover');
    }

    handleDragLeave(event) {
        event.preventDefault();
        this.dropZone.classList.remove('dragover');
    }

    handleDrop(event) {
        event.preventDefault();
        this.dropZone.classList.remove('dragover');
        
        const files = event.dataTransfer.files;
        if (files.length > 0) {
            this.processFile(files[0]);
        }
    }

    async processFile(file) {
        if (!this.isValidWordDocument(file)) {
            alert('Please select a valid Word document (.doc or .docx file).');
            return;
        }

        this.showProcessing();
        
        try {
            const formattedText = await DocumentProcessor.extractTextFromWord(file);
            this.displayResult(formattedText);
        } catch (error) {
            console.error('Error processing file:', error);
            this.resultDiv.innerHTML = `<p style="color: red;">Error processing document: ${error.message}</p>`;
        } finally {
            this.hideProcessing();
        }
    }

    isValidWordDocument(file) {
        const validTypes = [
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword',
            'application/vnd.ms-word'
        ];
        
        const validExtensions = ['.doc', '.docx'];
        const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
        
        return validTypes.includes(file.type) || validExtensions.includes(fileExtension);
    }

    showProcessing() {
        this.processingDiv.style.display = 'block';
        this.resultDiv.innerHTML = '';
        this.downloadBtn.style.display = 'none';
    }

    hideProcessing() {
        this.processingDiv.style.display = 'none';
    }

    displayResult(formattedText) {
        this.resultDiv.innerHTML = formattedText;
        this.downloadBtn.style.display = 'inline-block';
    }

    downloadResult() {
        const resultText = this.resultDiv.innerHTML;
        const blob = new Blob([resultText], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = 'formatted_document.html';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

// Document Processor with Python Backend
class DocumentProcessor {
    static async extractTextFromWord(file) {
        // Use Python serverless function to extract text with full formatting
        console.log('extractTextFromWord called with:', file.name, 'Size:', file.size);
        
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            
            reader.onload = async function(event) {
                console.log('FileReader onload triggered');
                const dataURL = event.target.result;
                console.log('DataURL length:', dataURL.length);
                
                try {
                    // Extract base64 string from data URL (remove "data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,")
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
                        // Show the actual error from Python
                        const errorMsg = result.error || 'Unknown error';
                        console.error('Python processing error:', errorMsg);
                        resolve(`<div style="color: red; padding: 20px; border: 1px solid red; border-radius: 4px;">
                            <h3>Error Processing Document:</h3>
                            <p>${errorMsg}</p>
                            <p><em>This error occurred in the Python backend. Check the Vercel function logs for more details.</em></p>
                        </div>`);
                    }
                    
                } catch (error) {
                    console.error('Error calling Python function:', error);
                    
                    // Fallback to basic text extraction for testing
                    const fallbackContent = "Error processing document. Using fallback content for testing.\n\n" +
                        "Dear {[Salutation]},\n\n" +
                        "This is fallback content while the Python processing is being set up.\n\n" +
                        "Sincerely,\n" +
                        "Test Department";
                    
                    resolve(fallbackContent);
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

// Initialize the formatter when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new WordFormatter();
});
