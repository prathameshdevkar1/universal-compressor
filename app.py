import os
import uuid
from io import BytesIO
from flask import Flask, request, send_file, abort, jsonify, render_template
from PyPDF2 import PdfReader, PdfWriter
from werkzeug.utils import secure_filename
from PIL import Image

# Initialize the Flask application
app = Flask(__name__)

# Security: Define allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    """Check if the uploaded file has a permitted extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Serve the frontend interface."""
    return render_template('index.html')

@app.route('/compress', methods=['POST'])
def compress_file():
    """Handle the file upload, dynamic validation, and memory-based compression."""
    
    # 1. INITIAL VALIDATION
    if 'file' not in request.files:
        abort(400, description="No file provided in the request.")
        
    file = request.files['file']
    if file.filename == '':
        abort(400, description="No file selected.")

    if not allowed_file(file.filename):
        abort(400, description="Invalid file type. Only PDF, JPG, and PNG are supported.")

    # 2. DYNAMIC FILE SIZE LIMIT LOGIC
    # Retrieve the dynamic limit set by the user (defaulting to 16MB if missing)
    try:
        dynamic_limit_mb = float(request.form.get('max_upload_limit', 16))
    except ValueError:
        dynamic_limit_mb = 16.0
        
    max_bytes = dynamic_limit_mb * 1024 * 1024
    
    # Validate against actual content length
    if request.content_length and request.content_length > max_bytes:
        abort(413, description=f"File exceeds the dynamic limit of {dynamic_limit_mb} MB.")

    # Retrieve the target compression size (default to 500KB)
    try:
        target_size_kb = int(request.form.get('target_size', 500))
    except ValueError:
        target_size_kb = 500

    # 3. SECURE SETUP
    filename = secure_filename(file.filename)
    file_ext = filename.rsplit('.', 1)[1].lower()
    
    # Create an in-memory buffer to hold the final compressed file
    output_buffer = BytesIO()

    # 4. PROCESSING LOGIC (IN-MEMORY)
    try:
        # --- IMAGE COMPRESSION (JPG/PNG) ---
        if file_ext in ['jpg', 'jpeg', 'png']:
            img = Image.open(file.stream)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            quality = 95
            scale = 1.0  # Represents 100% of the original image size
            
            # Advanced Iterative Loop (Quality + Dimensional Resizing)
            while True:
                output_buffer.seek(0)
                output_buffer.truncate()
                
                # Apply resizing if the scale has been reduced
                if scale < 1.0:
                    new_size = (int(img.width * scale), int(img.height * scale))
                    current_img = img.resize(new_size, Image.Resampling.LANCZOS)
                else:
                    current_img = img
                    
                current_img.save(output_buffer, format="JPEG", quality=quality)
                
                # 1. Success Check: Did we hit the target size?
                if (output_buffer.tell() / 1024) <= target_size_kb:
                    break
                    
                # 2. Reduction Logic: How to make it smaller on the next loop
                if quality > 20:
                    quality -= 15  # Step 1: Drop quality aggressively first
                else:
                    scale *= 0.8   # Step 2: If quality is awful, shrink physical dimensions by 20%
                    quality = 50   # Reset quality a bit so the smaller image isn't too blurry
                    
                # 3. Safety Net: Prevent infinite loops if user asks for 0.1 KB
                if scale < 0.05:
                    break
                    
            download_name = f"compressed_{filename.rsplit('.', 1)[0]}.jpg"
            mimetype = 'image/jpeg'

        # --- PDF COMPRESSION ---
        elif file_ext == 'pdf':
            reader = PdfReader(file.stream)
            writer = PdfWriter()
            
            # Compress the data streams of each page
            for page in reader.pages:
                page.compress_content_streams()
                
            # Write the compressed PDF to our memory buffer
            writer.write(output_buffer)
            
            download_name = f"compressed_{filename}"
            mimetype = 'application/pdf'

        # 5. PREPARE THE RESPONSE
        # Reset the buffer's position to the beginning before sending it to the user
        output_buffer.seek(0)
        
        return send_file(
            output_buffer,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
        )

    except Exception as e:
        # Catch unexpected processing errors (e.g., corrupted files)
        app.logger.error(f"Compression error: {str(e)}")
        abort(500, description=f"An error occurred during compression: {str(e)}")

# Standardized error handlers to return clean text to the frontend
@app.errorhandler(400)
@app.errorhandler(413)
@app.errorhandler(500)
def handle_error(error):
    return error.description, error.code

if __name__ == '__main__':
    # Bypassing Flask's hard limit so our dynamic limit logic works
    app.config['MAX_CONTENT_LENGTH'] = None 
    app.run(debug=True, port=5000)