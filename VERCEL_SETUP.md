# Vercel Deployment Setup

## 🚀 Deploy to Vercel (Python Support!)

This project is now configured for Vercel deployment with Python serverless functions.

### **Quick Setup:**

1. **Install Vercel CLI:**
   ```bash
   npm install -g vercel
   ```

2. **Login to Vercel:**
   ```bash
   vercel login
   ```

3. **Deploy:**
   ```bash
   vercel
   ```

### **Or Deploy via GitHub:**

1. **Connect to Vercel:**
   - Go to [vercel.com](https://vercel.com)
   - Sign in with GitHub
   - Click "New Project"
   - Import your `joshuahamrick/ncformatter` repository

2. **Configure Build Settings:**
   - **Framework Preset:** Other
   - **Root Directory:** `.`
   - **Build Command:** (leave empty)
   - **Output Directory:** `.`

3. **Deploy!**

### **Project Structure:**
```
├── api/
│   └── process-word.py     # Python serverless function
├── index.html              # Frontend
├── script-new.js           # Frontend logic
├── styles.css              # Styles
├── vercel.json             # Vercel configuration
├── requirements.txt        # Python dependencies
└── *.docx                  # Sample documents
```

### **Features:**
- ✅ **Python Backend:** Full Word document processing with `python-docx`
- ✅ **Full Formatting:** Bold, underline, alignment, font size
- ✅ **Universal Rules:** Works with any Word document
- ✅ **Serverless:** Scales automatically
- ✅ **Free Hosting:** Vercel free tier

### **API Endpoint:**
- **URL:** `https://your-site.vercel.app/api/process-word`
- **Method:** POST
- **Input:** Base64-encoded Word document
- **Output:** Formatted HTML with full styling

### **Testing:**
1. Upload a Word document via the web interface
2. The Python function will process it with full formatting
3. Download the formatted HTML result

### **Troubleshooting:**
- Check Vercel function logs in the dashboard
- Ensure `python-docx` is installed (handled automatically)
- Verify CORS headers are set correctly
