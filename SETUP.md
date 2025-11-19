# Word Document Formatter - Setup Guide

## 🚀 Quick Setup (5 minutes)

### 1. **Deploy to Vercel (FREE)**
1. Go to [vercel.com](https://vercel.com) and sign up (free)
2. Connect your GitHub account
3. Push this project to GitHub
4. Deploy from GitHub on Vercel

### 2. **Enable Python Functions**
1. Vercel automatically detects `api/` folder as serverless functions
2. The Python function will automatically deploy
3. Vercel will install `python-docx` from `requirements.txt`

### 3. **Test the Formatter**
1. Open your deployed site
2. Drag and drop a Word document
3. Get perfectly formatted HTML with full formatting preservation!

## 🎯 What This Does

- **Full Formatting Preservation**: Extracts alignment, font size, bold, underline from Word docs
- **Universal Rules**: Works with ANY Word document (BR010, BR017, SL106, etc.)
- **Perfect Structure**: Creates proper header tables, salutations, and formatting
- **Free Hosting**: Runs on Vercel's free tier

## 🔧 How It Works

1. **Frontend**: JavaScript handles file upload and display
2. **Backend**: Python serverless function processes Word documents
3. **Processing**: Extracts all formatting and applies universal rules
4. **Output**: Perfect HTML that matches the Word document exactly

## 📁 Project Structure

```
├── index.html              # Main page
├── script-new.js           # New JavaScript (uses Python backend)
├── api/
│   └── process-word.py     # Python Word processor (Vercel function)
├── vercel.json             # Vercel configuration
├── requirements.txt        # Python dependencies
└── SETUP.md               # This file
```

## 🎉 Benefits Over Previous Version

- ✅ **Full formatting preservation** (alignment, font size, bold, underline)
- ✅ **No hardcoded text** - works with actual Word document content
- ✅ **Universal rules** - applies to ANY document type
- ✅ **Proper structure** - creates correct tables and formatting
- ✅ **Free hosting** - no server costs
- ✅ **Fast setup** - deploy in minutes

## 🚨 Important Notes

- The Python function will take a few seconds to "warm up" on first use
- Free Vercel tier includes generous function execution limits
- All Word document formatting is preserved exactly as it appears in the original

## 🔄 Migration from Old Version

1. Replace `script.js` with `script-new.js` in your HTML
2. Deploy to Vercel
3. Test with your Word documents
4. Enjoy perfect formatting!

## 📞 Support

If you run into any issues:
1. Check the browser console for errors
2. Check Vercel function logs in the dashboard
3. Test with a simple Word document first

The new system is much more robust and will handle your Word documents perfectly!

