document.addEventListener('DOMContentLoaded', function() {
    // Initialize assignment creation form
    initializeAssignmentForm();
    
    // Initialize question forms
    initializeQuestionForms();
    
    // Initialize upload functionality
    initializeUploaders();
    
    // Initialize submission handling
    initializeSubmission();
});

function initializeAssignmentForm() {
    const assignmentForm = document.getElementById('assignment-form');
    
    if (assignmentForm) {
        assignmentForm.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
                showToast('Please fill in all required fields', 'warning');
            }
        });
    }
}

function initializeQuestionForms() {
    const addQuestionForm = document.getElementById('add-question-form');
    const evaluationMethodSelect = document.getElementById('evaluation_method');
    const answerKeyGroup = document.getElementById('answer-key-group');
    
    if (addQuestionForm && evaluationMethodSelect && answerKeyGroup) {
        // Show/hide answer key based on evaluation method
        evaluationMethodSelect.addEventListener('change', function() {
            if (this.value === 'answer_key') {
                answerKeyGroup.style.display = 'block';
                document.getElementById('answer_key').setAttribute('required', '');
            } else {
                answerKeyGroup.style.display = 'none';
                document.getElementById('answer_key').removeAttribute('required');
            }
        });
        
        // Trigger change event to initialize correctly
        evaluationMethodSelect.dispatchEvent(new Event('change'));
        
        // Validate form on submit
        addQuestionForm.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
                showToast('Please fill in all required fields', 'warning');
            }
        });
    }
    
    // Setup delete question modal confirmations
    const deleteQuestionBtns = document.querySelectorAll('.delete-question-btn');
    
    deleteQuestionBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const questionId = this.getAttribute('data-question-id');
            const questionText = this.getAttribute('data-question-text');
            
            // Populate and show confirmation modal
            const modal = document.getElementById('delete-question-modal');
            if (modal) {
                const questionElement = modal.querySelector('.question-to-delete');
                const confirmForm = modal.querySelector('#delete-question-form');
                
                if (questionElement) {
                    questionElement.textContent = questionText;
                }
                
                if (confirmForm) {
                    confirmForm.action = `/admin/delete-question/${questionId}`;
                }
                
                openModal('delete-question-modal');
            }
        });
    });
}

function initializeUploaders() {
    const uploaders = document.querySelectorAll('.uploader-container');
    
    uploaders.forEach(uploader => {
        const questionId = uploader.getAttribute('data-question-id');
        const fileInput = document.getElementById(`file-input-${questionId}`);
        const previewContainer = document.getElementById(`preview-container-${questionId}`);
        const extractedTextElement = document.getElementById(`extracted-text-${questionId}`);
        
        if (fileInput && previewContainer) {
            // Handle click on uploader container
            uploader.addEventListener('click', function() {
                fileInput.click();
            });
            
            // Handle file selection
            fileInput.addEventListener('change', function() {
                if (this.files.length > 0) {
                    uploadFiles(this.files, questionId, previewContainer, extractedTextElement);
                }
            });
            
            // Setup drag and drop
            uploader.addEventListener('dragover', function(e) {
                e.preventDefault();
                this.classList.add('border-primary');
            });
            
            uploader.addEventListener('dragleave', function() {
                this.classList.remove('border-primary');
            });
            
            uploader.addEventListener('drop', function(e) {
                e.preventDefault();
                this.classList.remove('border-primary');
                
                if (e.dataTransfer.files.length > 0) {
                    uploadFiles(e.dataTransfer.files, questionId, previewContainer, extractedTextElement);
                }
            });
        }
    });
}

function uploadFiles(files, questionId, previewContainer, extractedTextElement) {
    // Show loading state
    showSpinner('Uploading and processing images...');
    
    // Create form data
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('images', files[i]);
    }
    
    // Upload files
    fetch(`/student/upload-answer/${questionId}`, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();
        
        if (data.success) {
            // Show preview
            previewContainer.innerHTML = '';
            previewContainer.style.display = 'block';
            
            const previewItem = document.createElement('div');
            previewItem.classList.add('preview-item', 'animate-fadeIn');
            
            // Use a placeholder image for preview (SVG)
            previewItem.innerHTML = `
                <svg class="preview-thumbnail" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                    <rect width="100" height="100" fill="#f0f0f0"/>
                    <text x="50" y="50" font-size="12" text-anchor="middle" dominant-baseline="middle">Image Preview</text>
                </svg>
                <div class="preview-info">
                    <div class="preview-filename">${files.length} image(s) uploaded</div>
                    <div class="preview-extract">First words: ${data.first_five_words}</div>
                </div>
            `;
            
            previewContainer.appendChild(previewItem);
            
            // Show extracted text
            if (extractedTextElement) {
                extractedTextElement.value = data.extracted_text;
                
                // Store image paths in a hidden input
                const imagePathsInput = document.getElementById(`image-paths-${questionId}`);
                if (imagePathsInput) {
                    imagePathsInput.value = JSON.stringify(data.image_paths);
                }
            }
            
            showToast('Images uploaded and processed successfully!', 'success');
        } else {
            showToast(data.error || 'Failed to upload images', 'error');
        }
    })
    .catch(error => {
        hideSpinner();
        console.error('Error:', error);
        showToast('An error occurred while uploading images', 'error');
    });
}

function initializeSubmission() {
    // Handle question submission
    const submitAnswerBtns = document.querySelectorAll('.submit-answer-btn');
    
    submitAnswerBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const questionId = this.getAttribute('data-question-id');
            const assignmentId = this.getAttribute('data-assignment-id');
            const extractedText = document.getElementById(`extracted-text-${questionId}`).value;
            const imagePathsInput = document.getElementById(`image-paths-${questionId}`);
            
            if (!extractedText) {
                showToast('Please upload images first', 'warning');
                return;
            }
            
            // Get image paths from hidden input
            let imagePaths = [];
            try {
                imagePaths = JSON.parse(imagePathsInput.value);
            } catch (e) {
                console.error('Error parsing image paths:', e);
            }
            
            // Show loading state
            showSpinner('Evaluating your answer...');
            
            // Submit answer
            fetch(`/student/submit-answer/${assignmentId}/${questionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    extracted_text: extractedText,
                    image_paths: imagePaths
                })
            })
            .then(response => response.json())
            .then(data => {
                hideSpinner();
                
                if (data.success) {
                    // Update UI with evaluation results
                    const resultContainer = document.getElementById(`result-container-${questionId}`);
                    
                    if (resultContainer) {
                        resultContainer.innerHTML = `
                            <div class="response-preview animate-fadeIn">
                                <div class="response-header">
                                    <h4 class="response-title">Evaluation Results</h4>
                                    <div class="response-stats">
                                        <div class="response-stat">
                                            <i class="fas fa-bullseye"></i> Relevance: ${data.response.relevance_score.toFixed(2)}%
                                        </div>
                                        <div class="response-stat">
                                            <i class="fas fa-check-circle"></i> Marks: ${data.response.marks_awarded.toFixed(2)}
                                        </div>
                                    </div>
                                </div>
                                <div class="response-text">${extractedText}</div>
                                <div class="response-stats">
                                    <div class="response-stat">
                                        <i class="fas fa-text-height"></i> Grammar: ${data.response.grammar_score.toFixed(2)}%
                                    </div>
                                    <div class="response-stat">
                                        <i class="fas fa-ruler"></i> Size: ${data.response.size_score.toFixed(2)}%
                                    </div>
                                    <div class="response-stat">
                                        <i class="fas fa-font"></i> Words: ${data.response.word_count_actual}
                                    </div>
                                </div>
                                <div class="response-feedback">
                                    <strong>Feedback:</strong> ${data.response.feedback}
                                </div>
                            </div>
                        `;
                        
                        // Scroll to results
                        resultContainer.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                    showToast('Answer submitted and evaluated successfully!', 'success');
                    
                    // Update submit button to show submitted
                    this.innerHTML = '<i class="fas fa-check"></i> Submitted';
                    this.classList.remove('btn-primary');
                    this.classList.add('btn-success');
                    this.disabled = true;
                    
                    // Check if all questions are answered and show finalize button
                    checkAllQuestionsAnswered();
                } else {
                    showToast(data.error || 'Failed to submit answer', 'error');
                }
            })
            .catch(error => {
                hideSpinner();
                console.error('Error:', error);
                showToast('An error occurred while submitting your answer', 'error');
            });
        });
    });
    
    // Handle final submission
    const finalizeBtn = document.getElementById('finalize-submission-btn');
    
    if (finalizeBtn) {
        finalizeBtn.addEventListener('click', function() {
            const assignmentId = this.getAttribute('data-assignment-id');
            
            // Confirm submission
            if (!confirm('Are you sure you want to finalize this submission? You cannot make changes after submission.')) {
                return;
            }
            
            // Show loading state
            showSpinner('Finalizing your submission...');
            
            // Submit assignment
            fetch(`/student/finalize-submission/${assignmentId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            })
            .then(response => response.json())
            .then(data => {
                hideSpinner();
                
                if (data.success) {
                    showToast('Assignment submitted successfully!', 'success');
                    
                    // Show modal with success message
                    const successModal = document.getElementById('submission-success-modal');
                    if (successModal) {
                        openModal('submission-success-modal');
                        
                        // Redirect to dashboard after 3 seconds
                        setTimeout(() => {
                            window.location.href = '/student/dashboard';
                        }, 3000);
                    } else {
                        // Redirect immediately if no modal
                        window.location.href = '/student/dashboard';
                    }
                } else {
                    showToast(data.error || 'Failed to finalize submission', 'error');
                }
            })
            .catch(error => {
                hideSpinner();
                console.error('Error:', error);
                showToast('An error occurred while finalizing your submission', 'error');
            });
        });
    }
}

function checkAllQuestionsAnswered() {
    const submitButtons = document.querySelectorAll('.submit-answer-btn');
    const finalizeBtn = document.getElementById('finalize-submission-btn');
    
    if (finalizeBtn) {
        let allAnswered = true;
        
        submitButtons.forEach(btn => {
            if (!btn.disabled) {
                allAnswered = false;
            }
        });
        
        if (allAnswered) {
            finalizeBtn.style.display = 'block';
            animateElement(finalizeBtn);
        }
    }
}
