document.addEventListener('DOMContentLoaded', function() {
    // Initialize chat functionality
    initializeChat();
});

function initializeChat() {
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message-input');
    const messagesContainer = document.getElementById('chat-messages');
    const chatPartnerIdInput = document.getElementById('chat-partner-id');
    const toggleSidebarBtn = document.getElementById('toggle-chat-sidebar');
    const chatSidebar = document.getElementById('chat-sidebar');
    
    // Initialize mobile sidebar toggle
    if (toggleSidebarBtn && chatSidebar) {
        toggleSidebarBtn.addEventListener('click', function() {
            chatSidebar.classList.toggle('collapsed');
        });
    }
    
    if (chatForm && messageInput && messagesContainer && chatPartnerIdInput) {
        // Handle sending messages
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const message = messageInput.value.trim();
            const receiverId = chatPartnerIdInput.value;
            
            if (!message || !receiverId) {
                return;
            }
            
            // Create form data
            const formData = new FormData();
            formData.append('receiver_id', receiverId);
            formData.append('message', message);
            
            // Disable input during send
            messageInput.disabled = true;
            
            // Get current user ID from data attribute
            const currentUserId = messagesContainer.getAttribute('data-user-id');
            
            // Send message
            const isStudent = window.location.pathname.includes('student');
            const sendUrl = isStudent ? '/student/send-message' : '/admin/send-message';
            
            fetch(sendUrl, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Clear input
                    messageInput.value = '';
                    
                    // Scroll to bottom
                    scrollToBottom();
                } else {
                    showToast(data.error || 'Failed to send message', 'error');
                }
                
                // Re-enable input
                messageInput.disabled = false;
                messageInput.focus();
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('An error occurred while sending your message', 'error');
                messageInput.disabled = false;
            });
        });
        
        // Focus input on load
        messageInput.focus();
        
        // Scroll to bottom on load
        scrollToBottom();
        
        // Setup polling for new messages
        let lastMessageId = getLastMessageId();
        
        setInterval(() => {
            checkForNewMessages(lastMessageId);
        }, 3000);
    }
    
    // Handle chat user selection
    const chatUsers = document.querySelectorAll('.chat-user');
    
    chatUsers.forEach(user => {
        user.addEventListener('click', function() {
            const userId = this.getAttribute('data-user-id');
            const isStudent = window.location.pathname.includes('student');
            
            // Redirect to chat with selected user
            window.location.href = isStudent ? 
                `/student/chat/${userId}` : 
                `/admin/chat/${userId}`;
                
            // Collapse sidebar on mobile after selection
            if (chatSidebar && window.innerWidth < 768) {
                chatSidebar.classList.add('collapsed');
            }
        });
    });
    
    // Handle window resize to adjust mobile view
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 768 && chatSidebar) {
            chatSidebar.classList.remove('collapsed');
        }
    });
}

function getLastMessageId() {
    const messagesContainer = document.getElementById('chat-messages');
    const messages = messagesContainer.querySelectorAll('.chat-message');
    
    if (messages.length > 0) {
        const lastMessage = messages[messages.length - 1];
        return lastMessage.getAttribute('data-message-id');
    }
    
    return 0;
}

function checkForNewMessages(lastId) {
    const messagesContainer = document.getElementById('chat-messages');
    const chatPartnerIdInput = document.getElementById('chat-partner-id');
    
    if (!messagesContainer || !chatPartnerIdInput) {
        return;
    }
    
    const partnerId = chatPartnerIdInput.value;
    const isStudent = window.location.pathname.includes('student');
    const fetchUrl = isStudent ? 
        `/student/get-messages/${partnerId}?last_id=${lastId}` : 
        `/admin/get-messages/${partnerId}?last_id=${lastId}`;
    
    fetch(fetchUrl)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.messages.length > 0) {
                // Append new messages
                appendMessages(data.messages);
                
                // Update last message ID
                const newLastId = data.messages[data.messages.length - 1].id;
                
                // Update global variable
                window.lastMessageId = newLastId;
            }
        })
        .catch(error => {
            console.error('Error checking for new messages:', error);
        });
}

function appendMessages(messages) {
    const messagesContainer = document.getElementById('chat-messages');
    const currentUserId = messagesContainer.getAttribute('data-user-id');
    
    let wasAtBottom = isScrolledToBottom();
    
    messages.forEach(message => {
        const isSent = message.sender_id == currentUserId;
        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-message');
        messageElement.classList.add(isSent ? 'chat-message-sent' : 'chat-message-received');
        messageElement.setAttribute('data-message-id', message.id);
        
        messageElement.innerHTML = `
            ${message.message}
            <div class="chat-message-time">${formatChatTime(message.timestamp)}</div>
        `;
        
        // Add animation class
        messageElement.classList.add('animate-fadeIn');
        
        messagesContainer.appendChild(messageElement);
    });
    
    // Scroll to bottom if user was already at bottom
    if (wasAtBottom) {
        scrollToBottom();
    }
}

function scrollToBottom() {
    const messagesContainer = document.getElementById('chat-messages');
    if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

function isScrolledToBottom() {
    const messagesContainer = document.getElementById('chat-messages');
    if (!messagesContainer) return true;
    
    const threshold = 100; // pixels from bottom
    return messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < threshold;
}

function formatChatTime(timestamp) {
    const date = new Date(timestamp);
    
    // Format time as HH:MM
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    
    // Check if message is from today
    const today = new Date();
    if (date.getDate() === today.getDate() && 
        date.getMonth() === today.getMonth() && 
        date.getFullYear() === today.getFullYear()) {
        return `Today at ${hours}:${minutes}`;
    }
    
    // Check if message is from yesterday
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.getDate() === yesterday.getDate() && 
        date.getMonth() === yesterday.getMonth() && 
        date.getFullYear() === yesterday.getFullYear()) {
        return `Yesterday at ${hours}:${minutes}`;
    }
    
    // Format date as MMM DD
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = monthNames[date.getMonth()];
    const day = date.getDate();
    
    return `${month} ${day} at ${hours}:${minutes}`;
}
