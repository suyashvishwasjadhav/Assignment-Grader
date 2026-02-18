# Copyright (c) 2024-2025 Suyash Vishwas Jadhav. All rights reserved.
# Project: EduEval - AI-Powered Automated Grading System
# Lead Developer & Architect: Suyash Vishwas Jadhav
# Module Contributor: HARSH GAWANDE (Diagram Evaluation System)

import os
import traceback
from flask import render_template, request, jsonify
from werkzeug.utils import secure_filename
from app import app, admin_required

def register_diagram_routes(app):
    @app.route('/admin/diagram-evaluation')
    @admin_required
    def diagram_evaluation():
        """Render the diagram evaluation page"""
        return render_template('admin/diagram_evaluation.html')

    @app.route('/admin/analyze-diagrams', methods=['POST'])
    @admin_required
    def analyze_diagrams():
        """Analyze diagram comparison using the DiagramAnalyzer"""
        if 'reference' not in request.files or 'submission' not in request.files:
            return jsonify({"status": "error", "error": "Missing files"})
        
        reference_file = request.files['reference']
        submission_file = request.files['submission']
        
        if reference_file.filename == '' or submission_file.filename == '':
            return jsonify({"status": "error", "error": "No selected files"})
        
        # Get optional question
        question = request.form.get('question', '')
        
        # Create uploads directory if it doesn't exist
        uploads_dir = os.path.join(app.static_folder, 'uploads', 'diagrams')
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Save uploaded files with secure filenames
        reference_filename = secure_filename(reference_file.filename)
        submission_filename = secure_filename(submission_file.filename)
        
        reference_path = os.path.join(uploads_dir, f"ref_{reference_filename}")
        submission_path = os.path.join(uploads_dir, f"sub_{submission_filename}")
        
        try:
            reference_file.save(reference_path)
            submission_file.save(submission_path)
            
            # Import the DiagramAnalyzer
            from diagram_analyzer import DiagramAnalyzer
            
            # Analyze the diagrams
            analyzer = DiagramAnalyzer()
            results = analyzer.analyze_diagrams(reference_path, submission_path, question)
            
            # Clean up uploaded files after analysis (optional)
            # os.remove(reference_path)
            # os.remove(submission_path)
            
            return jsonify(results)
        
        except Exception as e:
            # Log the error
            app.logger.error(f"Error analyzing diagrams: {str(e)}")
            traceback.print_exc()
            
            # Clean up files in case of error
            if os.path.exists(reference_path):
                os.remove(reference_path)
            if os.path.exists(submission_path):
                os.remove(submission_path)
            
            return jsonify({"status": "error", "error": str(e)})