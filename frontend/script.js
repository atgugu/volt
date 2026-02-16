// Local LLM Agent Framework - Frontend
const API_BASE = window.location.origin;

let sessionId = null;
let voiceMode = false;

// DOM elements
const agentSelector = document.getElementById('agent-selector');
const voiceToggle = document.getElementById('voice-toggle');
const messagesDiv = document.getElementById('messages');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const statusText = document.getElementById('status-text');
const progressText = document.getElementById('progress-text');

// Load available agents
async function loadAgents() {
    try {
        const response = await fetch(`${API_BASE}/agents`);
        const agents = await response.json();

        agentSelector.innerHTML = '<option value="">Select an agent...</option>';
        agents.forEach(agent => {
            const option = document.createElement('option');
            option.value = agent.id;
            option.textContent = `${agent.name} (${agent.required_field_count} fields)`;
            agentSelector.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load agents:', error);
        addMessage('system', 'Failed to connect to backend. Is it running?');
    }
}

// Start conversation with selected agent
async function startConversation(agentId) {
    try {
        const response = await fetch(`${API_BASE}/conversation/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agent_id: agentId,
                voice_mode: voiceMode,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start conversation');
        }

        const data = await response.json();
        sessionId = data.session_id;

        // Clear and show greeting
        messagesDiv.innerHTML = '';
        addMessage('bot', data.greeting);

        // Enable input
        messageInput.disabled = false;
        sendBtn.disabled = false;
        messageInput.focus();

        statusText.textContent = `Agent: ${data.agent_name}`;
        progressText.textContent = '0% complete';

    } catch (error) {
        console.error('Failed to start conversation:', error);
        addMessage('system', `Error: ${error.message}`);
    }
}

// Send message
const MAX_MESSAGE_LENGTH = 2000;

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || !sessionId) return;

    if (message.length > MAX_MESSAGE_LENGTH) {
        addMessage('system', `Message too long (${message.length} chars). Please keep it under ${MAX_MESSAGE_LENGTH} characters.`);
        return;
    }

    // Show user message
    addMessage('user', message);
    messageInput.value = '';
    messageInput.disabled = true;
    sendBtn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/conversation/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                message: message,
                voice_mode: voiceMode,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to send message');
        }

        const data = await response.json();

        // Show bot response
        addMessage('bot', data.response);

        // Update progress
        progressText.textContent = `${data.completion_percentage}% complete`;

        if (data.is_complete) {
            statusText.textContent += ' (Complete)';
            addMessage('system', 'Conversation complete! Select an agent to start a new one.');
        }

    } catch (error) {
        console.error('Failed to send message:', error);
        addMessage('system', `Error: ${error.message}`);
    }

    messageInput.disabled = false;
    sendBtn.disabled = false;
    messageInput.focus();
}

// Add message to chat
function addMessage(type, text) {
    const div = document.createElement('div');
    div.className = `message ${type}`;

    // Simple markdown: **bold**
    let html = text
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');

    div.innerHTML = html;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Create agent elements
const createBtn = document.getElementById('create-agent-btn');
const createPanel = document.getElementById('create-panel');
const createPrompt = document.getElementById('create-prompt');
const createCancel = document.getElementById('create-cancel');
const createSubmit = document.getElementById('create-submit');

function toggleCreatePanel(show) {
    if (show === undefined) show = createPanel.classList.contains('hidden');
    createPanel.classList.toggle('hidden', !show);
    if (show) createPrompt.focus();
}

async function createAgent() {
    const prompt = createPrompt.value.trim();
    if (!prompt) return;

    createSubmit.disabled = true;
    createSubmit.textContent = 'Generating...';
    statusText.textContent = 'Generating agent...';

    try {
        const response = await fetch(`${API_BASE}/agents/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create agent');
        }

        const data = await response.json();

        await loadAgents();
        agentSelector.value = data.id;

        toggleCreatePanel(false);
        createPrompt.value = '';

        startConversation(data.id);
        addMessage('system', `Agent "${data.name}" created with ${data.field_count} fields.`);
    } catch (error) {
        console.error('Failed to create agent:', error);
        addMessage('system', `Error creating agent: ${error.message}`);
        statusText.textContent = 'Agent creation failed';
    }

    createSubmit.disabled = false;
    createSubmit.textContent = 'Create Agent';
}

createBtn.addEventListener('click', () => toggleCreatePanel());
createCancel.addEventListener('click', () => toggleCreatePanel(false));
createSubmit.addEventListener('click', createAgent);
createPrompt.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        createAgent();
    }
});

// Event listeners
agentSelector.addEventListener('change', (e) => {
    if (e.target.value) {
        startConversation(e.target.value);
    }
});

sendBtn.addEventListener('click', sendMessage);

messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

voiceToggle.addEventListener('click', () => {
    voiceMode = !voiceMode;
    voiceToggle.classList.toggle('active', voiceMode);
    voiceToggle.title = voiceMode ? 'Voice mode ON' : 'Voice mode OFF';
});

// Initialize
loadAgents();
