document.addEventListener('DOMContentLoaded', function() {
    // Check if on PDF generation page
    if (document.body.classList.contains('pdf-report')) {
        initializePDF();
    }
    
    // Setup PDF download buttons on other pages
    const downloadPdfButtons = document.querySelectorAll('.download-pdf-btn');
    
    downloadPdfButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            const submissionId = this.getAttribute('data-submission-id');
            
            // Show loading spinner
            showSpinner('Generating PDF report...');
            
            // Open PDF page in new tab
            const pdfWindow = window.open(`/admin/generate-pdf/${submissionId}`, '_blank');
            
            // Hide spinner when new window opens
            if (pdfWindow) {
                pdfWindow.addEventListener('load', function() {
                    hideSpinner();
                });
                
                // Fallback in case load event doesn't fire
                setTimeout(hideSpinner, 3000);
            } else {
                hideSpinner();
                showToast('Please allow pop-ups to generate the PDF report', 'warning');
            }
        });
    });
});

function initializePDF() {
    // This function runs when we're on the PDF template page
    
    // Add print button if it doesn't exist
    if (!document.getElementById('print-pdf-btn')) {
        const printBtn = document.createElement('button');
        printBtn.id = 'print-pdf-btn';
        printBtn.classList.add('btn', 'btn-primary', 'print-btn');
        printBtn.innerHTML = '<i class="fas fa-print"></i> Print Report';
        printBtn.style.position = 'fixed';
        printBtn.style.top = '20px';
        printBtn.style.right = '20px';
        printBtn.style.zIndex = '9999';
        
        printBtn.addEventListener('click', function() {
            window.print();
        });
        
        document.body.appendChild(printBtn);
    }
    
    // Automatically print after a short delay to allow styles to load
    setTimeout(function() {
        window.print();
    }, 1000);
}

// Define custom styles for printing
function setupPrintStyles() {
    const style = document.createElement('style');
    style.textContent = `
        @media print {
            body {
                padding: 20px;
                font-size: 12pt;
            }
            
            .print-btn {
                display: none;
            }
            
            header, footer, nav, .sidebar, .no-print {
                display: none;
            }
            
            .container, .content {
                width: 100%;
                margin: 0;
                padding: 0;
            }
            
            h1 {
                font-size: 18pt;
                margin-bottom: 10px;
            }
            
            h2 {
                font-size: 16pt;
                margin-bottom: 8px;
            }
            
            h3 {
                font-size: 14pt;
                margin-bottom: 6px;
            }
            
            table {
                page-break-inside: auto;
                border-collapse: collapse;
                width: 100%;
            }
            
            tr {
                page-break-inside: avoid;
                page-break-after: auto;
            }
            
            td, th {
                padding: 5px;
            }
            
            .page-break {
                page-break-before: always;
            }
        }
    `;
    
    document.head.appendChild(style);
}

// If on PDF generation page, setup print styles
if (document.body.classList.contains('pdf-report')) {
    setupPrintStyles();
}
