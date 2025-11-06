from http.server import BaseHTTPRequestHandler
import json

def check_libs():
	result = {
		'python': True,
		'docx': False,
		'pdfminer': False
	}
	try:
		import docx  # type: ignore
		result['docx'] = True
	# pylint: disable=bare-except
	except:
		result['docx'] = False
	try:
		import pdfminer  # type: ignore
		result['pdfminer'] = True
	except:
		result['pdfminer'] = False
	return result

class handler(BaseHTTPRequestHandler):
	def do_GET(self):
		status = {
			'success': True,
			'libs': check_libs()
		}
		self.send_response(200)
		self.send_header('Content-type', 'application/json')
		self.send_header('Access-Control-Allow-Origin', '*')
		self.end_headers()
		self.wfile.write(json.dumps(status).encode('utf-8'))

	def do_OPTIONS(self):
		self.send_response(200)
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Headers', 'Content-Type')
		self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
		self.end_headers()

