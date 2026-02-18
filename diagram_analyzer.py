# Copyright (c) 2024-2025 Suyash Vishwas Jadhav. All rights reserved.
# Project: EduEval - AI-Powered Automated Grading System
# Lead Developer & Architect: Suyash Vishwas Jadhav
# Module Contributor: HARSH GAWANDE (Diagram Evaluation System)

import os
import sys
import base64
import json
import re
import traceback
from werkzeug.utils import secure_filename

try:
    import google.generativeai as genai
    print("Successfully imported google.generativeai module")
except ImportError:
    print("Error: Required package 'google-generativeai' not installed")
    print("Install it with: pip install google-generativeai")
    sys.exit(1)

class DiagramAnalyzer:
    def __init__(self):
        # Use the environment variable for API key
        api_key = os.environ.get("GEMINI_API_KEY")
        
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable not found")
            # In production, we don't use hardcoded keys
            # api_key = "YOUR_GEMINI_API_KEY" 
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        try:
            # Configure the Gemini API
            genai.configure(api_key=api_key)
            
            # Initialize the multimodal model with the newer model name
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            print("Successfully initialized Gemini API")
            
        except Exception as e:
            print(f"Error: Failed to initialize Gemini API: {str(e)}")
            traceback.print_exc()
            raise
    
    def encode_image(self, image_path):
        """Encode an image to base64 for API submission"""
        try:
            if not os.path.exists(image_path):
                print(f"Error: Image file not found: {image_path}")
                return None
                
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                
            # Determine MIME type from file extension
            if image_path.lower().endswith(('.jpg', '.jpeg')):
                mime_type = 'image/jpeg'
            elif image_path.lower().endswith('.png'):
                mime_type = 'image/png'
            else:
                mime_type = 'image/jpeg'  # Default
                
            print(f"Successfully encoded image: {image_path}")
            return {
                "mime_type": mime_type,
                "data": encoded_image
            }
        except Exception as e:
            print(f"Error: Error encoding image {image_path}: {str(e)}")
            traceback.print_exc()
            return None
    
    def analyze_diagrams(self, answer_key_path, submission_path, question=None):
        """Analyze and compare two diagrams using Gemini API"""
        print(f"Starting analysis of diagrams: {answer_key_path} and {submission_path}")
        
        # Encode images for API submission
        answer_key_image = self.encode_image(answer_key_path)
        submission_image = self.encode_image(submission_path)
        
        if not answer_key_image or not submission_image:
            return {
                "status": "error", 
                "error": "Failed to encode one or both images"
            }
        
        # Create prompt for the analysis
        base_prompt = """
        You are a specialized diagram analysis system. I will show you two diagrams:
        
        1. The first diagram is the "answer key" (reference diagram)
        2. The second diagram is a "submission" that needs to be evaluated
        
        Analyze both diagrams carefully, comparing their visual structure and textual elements.
        
        Provide the following metrics as your analysis in a JSON format:
        
        1. Accuracy (0-100%): How correctly the submitted diagram represents the same information as the answer key
        2. Relevance (Low/Medium/High): How relevant the submitted content is to the answer key
        3. Match Percentage (0-100%): Overall percentage of matching elements between diagrams
        4. Similarity Score (0.0-1.0): A normalized score of structural and content similarity
        5. Plagiarism Detection (0-100%): Percentage of content directly copied from the answer key
        6. Diagram Size: Count of total elements (nodes/segments/bars) and connections/relationships
        
        Respond with ONLY a JSON object containing these metrics. No explanation or additional text.
        Example format: {"accuracy": "85%", "relevance": "High", "match_percentage": "80%", "similarity_score": 0.85, "plagiarism": "20%", "diagram_size": "12 nodes, 15 connections"}
        """
        
        # Add the question context if provided
        if question and question.strip():
            question_prompt = f"""
            The diagrams are related to the following question or prompt:
            
            "{question}"
            
            Take this context into account when evaluating the relevance and accuracy of the submission.
            """
            base_prompt = base_prompt + question_prompt
        
        try:
            # Call the Gemini API with both images
            print("Sending request to Gemini API...")
            response = self.model.generate_content([
                base_prompt,
                answer_key_image,
                submission_image
            ])
            
            print("Received response from Gemini API")
            
            # Debug: Print the raw response
            if hasattr(response, 'text'):
                print("Raw API Response:", response.text)
            else:
                print("Response object structure:", repr(response))
                
            # Try different ways to access the response
            response_text = ""
            if hasattr(response, 'text'):
                response_text = response.text
            elif hasattr(response, 'parts'):
                response_text = ' '.join([part.text for part in response.parts])
            elif hasattr(response, 'content'):
                response_text = response.content
            else:
                print("Unable to extract text from response object")
                response_text = str(response)
                
            print("Extracted response text:", response_text)
            
            # Try to parse the response as JSON
            try:
                # Look for JSON object in the response
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                
                if json_match:
                    json_str = json_match.group(0)
                    print("Found JSON in response:", json_str)
                    results = json.loads(json_str)
                    
                    # Debug: Print parsed results
                    print("Parsed JSON results:", results)
                    
                else:
                    print("No JSON found in response, using regex extraction")
                    # Manual extraction as fallback
                    results = {
                        "accuracy": self._extract_metric(response_text, "accuracy", "percentage"),
                        "relevance": self._extract_metric(response_text, "relevance", "text"),
                        "match_percentage": self._extract_metric(response_text, "match percentage", "percentage"),
                        "similarity_score": self._extract_metric(response_text, "similarity score", "float"),
                        "plagiarism": self._extract_metric(response_text, "plagiarism", "percentage"),
                        "diagram_size": self._extract_metric(response_text, "diagram size", "text")
                    }
                    
                    # Debug: Print extracted results
                    print("Regex extracted results:", results)
                
                results["status"] = "success"
                return results
                
            except json.JSONDecodeError as e:
                print("JSON parsing error:", e)
                # If JSON parsing fails, return the raw response for debugging
                return {
                    "status": "success",
                    "raw_response": response_text,
                    "accuracy": "0%",
                    "relevance": "Low",
                    "match_percentage": "0%",
                    "similarity_score": 0.0,
                    "plagiarism": "0%",
                    "diagram_size": "Unknown"
                }
                
        except Exception as e:
            print(f"Error calling Gemini API: {str(e)}")
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _extract_metric(self, text, metric_name, type_hint):
        """Extract a specific metric from text using regex"""
        # Try multiple pattern variations
        patterns = [
            re.compile(f"{metric_name}[:\s]+(.*?)($|\\n|,|\\.)", re.IGNORECASE),
            re.compile(f"\"{metric_name}\"[:\s]+\"?(.*?)\"?[,]", re.IGNORECASE),
            re.compile(f"{metric_name}[:\s]*([0-9.]+%?)", re.IGNORECASE)
        ]
        
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                value = match.group(1).strip()
                print(f"Found {metric_name} = {value}")
                
                # Process based on expected type
                if type_hint == "percentage":
                    percentage_match = re.search(r'(\d+(\.\d+)?)', value)
                    if percentage_match:
                        return f"{percentage_match.group(1)}%"
                    return "0%"
                    
                elif type_hint == "float":
                    float_match = re.search(r'(\d+\.\d+)', value)
                    if float_match:
                        return float(float_match.group(1))
                    int_match = re.search(r'(\d+)', value)
                    if int_match:
                        return float(int_match.group(1))
                    return 0.0
                    
                else:  # text
                    return value.strip('"').strip("'")
        
        print(f"No match found for {metric_name}")
        # Return default values if no match found
        if type_hint == "percentage":
            return "0%"
        elif type_hint == "float":
            return 0.0
        else:
            return "Unknown"