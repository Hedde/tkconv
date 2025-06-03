// Global state
let currentRequestId = null;
let isStreaming = false;
let currentAnswer = '';
let currentThoughts = [];

// Configuration
const API_BASE_URL = 'http://localhost:8091';

// Agent name mapping for user-friendly display - Updated to match current system
const AGENT_DISPLAY_NAMES = {
  'ParliamentaryDataAgent': 'Tweede Kamer Expert',
  'AlgemeneInformatieAgent': 'Algemene Assistent', 
  'VergunningenAgent': 'Vergunningen Expert',
  'ResearchAgent': 'Onderzoeks Assistent'
};

// Function to get friendly agent name
function getFriendlyAgentName(technicalName) {
  return AGENT_DISPLAY_NAMES[technicalName] || technicalName;
}

// Utility functions
function generateRequestId() {
  return 'req_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Navigation functions
function goToWelcome() {
  window.location.href = 'index.html';
}

function goToChat(question = '') {
  const params = question ? `?q=${encodeURIComponent(question)}` : '';
  window.location.href = `chat.html${params}`;
}

function resetChat() {
  if (confirm('Weet je zeker dat je een nieuw gesprek wilt starten?')) {
    localStorage.removeItem('chatHistory');
    window.location.reload();
  }
}

// Welcome page functions
function usePrompt(prompt) {
  goToChat(prompt);
}

function startChatFromWelcome() {
  const input = document.getElementById('welcome-question');
  if (input && input.value.trim()) {
    goToChat(input.value.trim());
  }
}

// Message rendering functions
function createMessageElement(type, content, isStreaming = false) {
  const messageDiv = document.createElement('div');
  messageDiv.className = `message-${type} fade-in`;
  
  if (type === 'user') {
    messageDiv.innerHTML = `
      <div class="flex justify-end">
        <div class="bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-2xl px-4 py-3 max-w-[80%] shadow-md">
          <div class="text-sm font-medium">${escapeHtml(content)}</div>
        </div>
      </div>
    `;
  } else if (type === 'assistant') {
    const contentId = `assistant-content-${Date.now()}`;
    const citationsId = `citations-${Date.now()}`;
    messageDiv.innerHTML = `
      <div class="flex justify-start">
        <div class="w-full max-w-4xl">
          <!-- Thinking Area -->
          <div id="thinking-area" class="mb-3">
            <div class="bg-gradient-to-r from-indigo-50 via-purple-50 to-indigo-50 border border-indigo-200/60 rounded-xl px-4 py-3 shadow-sm">
              <div class="flex items-start gap-3 mb-3">
                <div class="flex-shrink-0 mt-0.5">
                  <div class="w-8 h-8 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-full flex items-center justify-center shadow-sm">
                    <svg class="w-4 h-4 text-white thinking-brain" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
                      <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>
                      <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>
                      <path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/>
                      <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/>
                      <path d="M3.477 10.896a4 4 0 0 1 .585-.396"/>
                      <path d="M19.938 10.5a4 4 0 0 1 .585.396"/>
                      <path d="M6 18a4 4 0 0 1-1.967-.516"/>
                      <path d="M19.967 17.484A4 4 0 0 1 18 18"/>
                    </svg>
                  </div>
                </div>
                <div class="flex-1">
                  <div class="text-xs bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent font-semibold mb-1">AI Assistent denkt na...</div>
                  <div class="text-sm text-indigo-800/90" id="current-thought">Verbinding maken met kennisbank...</div>
                </div>
              </div>
              
              <!-- Thinking Steps -->
              <div id="thinking-steps" class="space-y-1">
                <!-- Steps will be added here dynamically -->
              </div>
            </div>
          </div>
          
          <!-- Answer Area -->
          <div class="bg-white/95 backdrop-blur-sm border border-indigo-100/60 rounded-2xl shadow-lg">
            <div class="prose prose-lg break-words px-6 py-5" id="${contentId}">
              ${isStreaming ? '<div class="waiting-for-answer"><div class="flex items-center gap-2 text-gray-500"><div class="thinking-dots"><div class="thinking-dot"></div><div class="thinking-dot"></div><div class="thinking-dot"></div></div><span class="text-xs">Wachten op antwoord...</span></div></div>' : content}
            </div>
            
            <!-- Feedback Buttons Area -->
            <div class="feedback-buttons-container px-6 py-4 border-t border-gray-100/60 hidden">
              <div class="flex items-center justify-between">
                <div class="text-xs text-gray-500">Was dit antwoord nuttig?</div>
                <div class="feedback-buttons flex items-center gap-2">
                  <button class="feedback-action-btn thumbs-up" onclick="handleFeedback(this, 'positive')" title="Dit antwoord was nuttig">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
                    </svg>
                  </button>
                  <button class="feedback-action-btn thumbs-down" onclick="handleFeedback(this, 'negative')" title="Dit antwoord was niet nuttig">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
                    </svg>
                  </button>
                  <div class="w-px h-4 bg-gray-200 mx-1"></div>
                  <button class="feedback-action-btn copy-btn" onclick="copyAnswer(this)" title="Kopieer antwoord">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
            
            <!-- Citations Area -->
            <div id="${citationsId}" class="citations-area pt-6 pb-8 border-t border-gray-200/60 hidden">
              <div class="px-6">
                <div class="flex items-center gap-2 text-sm text-gray-600 font-medium mb-4">
                  <svg class="w-4 h-4 text-gray-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                    <polyline points="14,2 14,8 20,8"/>
                  </svg>
                  Bronnen
                </div>
                <div class="citations-list space-y-3"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    // Store the content ID for later reference
    messageDiv.dataset.contentId = contentId;
    messageDiv.dataset.citationsId = citationsId;
  }
  
  return messageDiv;
}

function createThinkingIndicator() {
  const thinkingDiv = document.createElement('div');
  thinkingDiv.className = 'thinking-indicator fade-in';
  thinkingDiv.innerHTML = `
    <div class="flex items-center space-x-2 text-indigo-600">
      <div class="flex space-x-1">
        <div class="w-2 h-2 bg-indigo-400 rounded-full thinking-dot"></div>
        <div class="w-2 h-2 bg-indigo-400 rounded-full thinking-dot"></div>
        <div class="w-2 h-2 bg-indigo-400 rounded-full thinking-dot"></div>
      </div>
      <span class="text-sm">Aan het denken...</span>
    </div>
  `;
  return thinkingDiv;
}

function createSystemStatusIndicator() {
  const statusDiv = document.createElement('div');
  statusDiv.className = 'system-status fade-in mb-4';
  statusDiv.innerHTML = `
    <div class="flex justify-center">
      <div class="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
        <div class="text-xs text-gray-600 text-center" id="status-text">Verbinding maken...</div>
      </div>
    </div>
  `;
  return statusDiv;
}

// Chat functionality
function appendMessage(type, content, isStreaming = false) {
  const output = document.getElementById('output');
  if (!output) return;
  
  const messageElement = createMessageElement(type, content, isStreaming);
  output.appendChild(messageElement);
  
  // Scroll to bottom
  setTimeout(() => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  }, 100);
  
  return messageElement;
}

function updateAssistantMessage(content) {
  // Find the most recent assistant message
  const assistantMessages = document.querySelectorAll('.message-assistant');
  if (assistantMessages.length > 0) {
    const lastMessage = assistantMessages[assistantMessages.length - 1];
    const contentId = lastMessage.dataset.contentId;
    const assistantContent = document.getElementById(contentId);
    
    if (assistantContent) {
      // Remove waiting indicator if present
      const waitingIndicator = assistantContent.querySelector('.waiting-for-answer');
      if (waitingIndicator) {
        waitingIndicator.remove();
      }
      
      // Update content with markdown parsing
      assistantContent.innerHTML = marked.parse(content);
      
      // Auto-scroll to keep the latest content in view
      scrollToLatestContent();
    }
  }
}

function scrollToLatestContent() {
  // Smooth scroll to the bottom of the page to keep the latest content visible
  setTimeout(() => {
    window.scrollTo({
      top: document.body.scrollHeight,
      behavior: 'smooth'
    });
  }, 50);
}

function updateCurrentThought(message, type = false) {
  const currentThought = document.getElementById('current-thought');
  if (currentThought) {
    // Handle long thought messages by truncating if needed
    const maxLength = 200;
    let displayMessage = message;
    
    if (message.length > maxLength) {
      displayMessage = message.substring(0, maxLength) + '...';
    }
    
    currentThought.textContent = displayMessage;
    
    // Add a subtle animation to show the thought is updating
    currentThought.style.opacity = '0.7';
    setTimeout(() => {
      currentThought.style.opacity = '1';
    }, 100);
  }
  
  // Also add to thinking steps
  addThinkingStep(message, type);
}

// Global array to store all thinking steps for later display
let allThinkingSteps = [];

function addThinkingStep(message, type = false) {
  const thinkingSteps = document.getElementById('thinking-steps');
  if (thinkingSteps) {
    // Store all steps for later use in collapsible view
    allThinkingSteps.push({
      message: message,
      type: type,
      timestamp: Date.now()
    });
    
    const stepElement = document.createElement('div');
    
    // Different styling based on type
    if (type === 'agent') {
      // Subtle agent styling - less prominent than before
      stepElement.className = 'thinking-step text-xs text-slate-700 bg-slate-50 border border-slate-200/60 rounded px-2 py-1 font-medium fade-in';
    } else if (type === 'tool') {
      // Tool call styling - subtle but distinct
      stepElement.className = 'thinking-step text-xs text-emerald-700 bg-emerald-50 border border-emerald-200/60 rounded px-2 py-1 font-medium fade-in';
    } else if (type === 'thought') {
      // Thought styling - slightly more prominent
      stepElement.className = 'thinking-step text-xs text-indigo-800 bg-gradient-to-r from-indigo-50 to-purple-50 border border-indigo-200/40 rounded-lg px-2 py-1.5 font-medium fade-in';
    } else if (type === true || type === 'important') {
      // Legacy important styling
      stepElement.className = 'thinking-step text-xs text-indigo-800 bg-gradient-to-r from-indigo-100 to-purple-100 border border-indigo-200/60 rounded-lg px-2 py-1.5 font-medium fade-in shadow-sm';
    } else {
      // Regular system messages
      stepElement.className = 'thinking-step text-xs text-indigo-700/80 bg-white/60 border border-indigo-100/50 rounded px-2 py-1 fade-in';
    }
    
    // Truncate very long messages for the step list
    const maxLength = (type === 'thought' || type === true || type === 'important') ? 200 : 120;
    let displayMessage = message;
    if (message.length > maxLength) {
      displayMessage = message.substring(0, maxLength) + '...';
    }
    
    stepElement.textContent = displayMessage;
    stepElement.title = message; // Full message on hover
    thinkingSteps.appendChild(stepElement);
    
    // Keep only the last 3 steps visible during thinking process
    const steps = thinkingSteps.querySelectorAll('.thinking-step');
    if (steps.length > 3) {
      // Remove oldest steps, keeping only the last 3
      for (let i = 0; i < steps.length - 3; i++) {
        steps[i].remove();
      }
    }
    
    // Auto-scroll to bottom
    thinkingSteps.scrollTop = thinkingSteps.scrollHeight;
  }
}

function hideThinkingArea() {
  const thinkingArea = document.getElementById('thinking-area');
  if (thinkingArea) {
    // Transform thinking area into collapsible summary using all stored steps
    const stepsHtml = allThinkingSteps.map(step => {
      let className;
      if (step.type === 'agent') {
        className = 'text-xs text-slate-700 bg-slate-50 border border-slate-200/60 rounded px-2 py-1 font-medium';
      } else if (step.type === 'tool') {
        className = 'text-xs text-emerald-700 bg-emerald-50 border border-emerald-200/60 rounded px-2 py-1 font-medium';
      } else if (step.type === 'thought') {
        className = 'text-xs text-indigo-800 bg-gradient-to-r from-indigo-50 to-purple-50 border border-indigo-200/40 rounded-lg px-2 py-1.5 font-medium';
      } else if (step.type === true || step.type === 'important') {
        className = 'text-xs text-indigo-800 bg-gradient-to-r from-indigo-100 to-purple-100 border border-indigo-200/60 rounded-lg px-2 py-1.5 font-medium shadow-sm';
      } else {
        className = 'text-xs text-gray-600 bg-gray-50 border border-gray-100 rounded px-2 py-1';
      }
      return `<div class="${className}" title="${escapeHtml(step.message)}">${escapeHtml(step.message)}</div>`;
    }).join('');
    
    thinkingArea.innerHTML = `
      <div class="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3">
        <button onclick="toggleThinkingDetails(this)" class="flex items-center justify-between w-full text-left">
          <div class="flex items-center gap-2">
            <svg class="w-4 h-4 text-gray-600" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
              <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>
              <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>
              <path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/>
              <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/>
              <path d="M3.477 10.896a4 4 0 0 1 .585-.396"/>
              <path d="M19.938 10.5a4 4 0 0 1 .585.396"/>
              <path d="M6 18a4 4 0 0 1-1.967-.516"/>
              <path d="M19.967 17.484A4 4 0 0 1 18 18"/>
            </svg>
            <span class="text-sm text-gray-700 font-medium">Toon gedachtegang (${allThinkingSteps.length} stappen)</span>
          </div>
          <svg class="w-4 h-4 text-gray-400 transition-transform duration-200 chevron" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6,9 12,15 18,9"></polyline>
          </svg>
        </button>
        <div class="thinking-details hidden mt-3 space-y-1 max-h-80 overflow-y-auto custom-scrollbar" id="thinking-details">
          ${stepsHtml}
        </div>
      </div>
    `;
    
    // Add smooth transition
    thinkingArea.style.transition = 'all 0.3s ease-out';
    thinkingArea.style.opacity = '0.8';
  }
}

// Global function for toggling thinking details
window.toggleThinkingDetails = function(button) {
  const details = document.getElementById('thinking-details');
  const chevron = button.querySelector('.chevron');
  
  if (details) {
    if (details.classList.contains('hidden')) {
      details.classList.remove('hidden');
      chevron.style.transform = 'rotate(180deg)';
    } else {
      details.classList.add('hidden');
      chevron.style.transform = 'rotate(0deg)';
    }
  }
};

function showCitations(citations) {
  // Find the most recent assistant message
  const assistantMessages = document.querySelectorAll('.message-assistant');
  if (assistantMessages.length > 0) {
    const lastMessage = assistantMessages[assistantMessages.length - 1];
    const citationsId = lastMessage.dataset.citationsId;
    const citationsArea = document.getElementById(citationsId);
    
    if (citationsArea && citations && citations.length > 0) {
      const citationsList = citationsArea.querySelector('.citations-list');
      if (citationsList) {
        citationsList.innerHTML = '';
        
        citations.forEach((citation, index) => {
          const citationElement = document.createElement('div');
          citationElement.className = 'citation-item';
          citationElement.innerHTML = `
            <a href="${citation.uri || '#'}" target="_blank" class="flex items-start gap-2 p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-xs">
              <span class="flex-shrink-0 w-5 h-5 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center font-medium">${index + 1}</span>
              <div class="flex-1">
                <div class="font-medium text-gray-900">${escapeHtml(citation.title || 'Bron')}</div>
                ${citation.publication_date ? `<div class="text-gray-500 mt-0.5">${citation.publication_date}</div>` : ''}
              </div>
              <svg class="w-3 h-3 text-gray-400 flex-shrink-0 mt-0.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M7 17L17 7"/>
                <path d="M7 7h10v10"/>
              </svg>
            </a>
          `;
          citationsList.appendChild(citationElement);
        });
        
        citationsArea.classList.remove('hidden');
      }
    }
  }
}

function showSystemStatus(message) {
  // Remove existing status
  const existingStatus = document.querySelector('.system-status');
  if (existingStatus) {
    existingStatus.remove();
  }
  
  const output = document.getElementById('output');
  if (!output) return;
  
  const statusElement = createSystemStatusIndicator();
  const statusText = statusElement.querySelector('#status-text');
  if (statusText) {
    statusText.textContent = message;
  }
  
  output.appendChild(statusElement);
  
  // Auto-remove after 3 seconds
  setTimeout(() => {
    if (statusElement.parentNode) {
      statusElement.remove();
    }
  }, 3000);
}

// Removed showThinking function - now using updateCurrentThought instead

async function sendQuestion() {
  const questionInput = document.getElementById('question');
  const sendBtn = document.getElementById('send-btn');
  
  if (!questionInput || !questionInput.value.trim() || isStreaming) {
    return;
  }
  
  const question = questionInput.value.trim();
  questionInput.value = '';
  questionInput.style.height = 'auto';
  
  // Update character count
  const counter = document.getElementById('chat-char-count');
  if (counter) {
    counter.textContent = '0/1000';
  }
  
  // Disable send button
  if (sendBtn) {
    sendBtn.disabled = true;
    sendBtn.classList.add('opacity-50');
  }
  
  // Add user message
  appendMessage('user', question);
  
  // Add assistant message placeholder
  const assistantMessage = appendMessage('assistant', '', true);
  
  // Start streaming
  isStreaming = true;
  currentRequestId = generateRequestId();
  currentAnswer = '';
  currentThoughts = [];
  allThinkingSteps = []; // Reset thinking steps for new question
  
  try {
    const response = await fetch(`${API_BASE_URL}/magentic/ask/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': currentRequestId
      },
      body: JSON.stringify({ prompt: question })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) break;
      
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            handleStreamEvent(data);
          } catch (e) {
            console.warn('Failed to parse SSE data:', line);
          }
        }
      }
    }
    
  } catch (error) {
    console.error('Error during streaming:', error);
    updateAssistantMessage('Er is een fout opgetreden bij het verwerken van je vraag. Probeer het opnieuw.');
  } finally {
    isStreaming = false;
    if (sendBtn) {
      sendBtn.disabled = false;
      sendBtn.classList.remove('opacity-50');
    }
  }
}

function handleStreamEvent(data) {
  const { event, message, text, agent, step, answer_json } = data;
  
  // Debug logging to see all events (remove this in production)
  console.log('Stream event:', data);
  
  switch (event) {
    case 'system':
      // Add a small delay for system events so they're visible
      const handleSystemEvent = () => {
        if (step === 'received') {
          updateCurrentThought('Vraag ontvangen en verwerkt');
        } else if (step === 'init_agents') {
          updateCurrentThought('AI agents worden geïnitialiseerd...');
        } else if (step === 'init_agents_done') {
          updateCurrentThought('AI agents zijn klaar voor gebruik');
        } else if (step === 'start_orchestration') {
          updateCurrentThought('Zoeken naar de juiste informatie...');
        } else if (step === 'orchestration_started') {
          updateCurrentThought('Verbinding maken met kennisbank...');
        } else if (step === 'waiting_for_result') {
          updateCurrentThought('Wachten op resultaat...');
        } else if (step === 'planning') {
          updateCurrentThought(message || 'Analyseren welke specialisten nodig zijn...');
        } else if (step === 'planning_done') {
          updateCurrentThought(message || 'Plan klaar - juiste specialisten worden ingezet');
        } else if (step === 'progress_ledger') {
          updateCurrentThought(message || 'Evalueren of alle benodigde informatie verzameld is...');
        } else if (step === 'progress_ledger_done') {
          updateCurrentThought(message || 'Alle informatie compleet - antwoord wordt voorbereid');
        } else if (step === 'finalizing') {
          updateCurrentThought(message || 'Laatste controles en antwoord afronden...');
        } else if (step === 'result_ready') {
          updateCurrentThought('Antwoord is klaar, streaming begint...');
        } else {
          // Handle any unknown system steps
          updateCurrentThought(message || `Systeem: ${step}`);
        }
      };
      
      // Add a 150ms delay for system events to make them visible
      setTimeout(handleSystemEvent, 150);
      break;
      
    case 'agent_start':
      if (agent && message) {
        // Use friendly name in the message if it contains the technical name
        const friendlyMessage = message.replace(agent, getFriendlyAgentName(agent));
        updateCurrentThought(`→ Inzetten van ${getFriendlyAgentName(agent)} voor deze taak`, 'agent');
      } else if (agent) {
        updateCurrentThought(`→ Inzetten van ${getFriendlyAgentName(agent)} voor informatie zoeken`, 'agent');
      } else {
        updateCurrentThought('→ Agent wordt ingezet voor deze taak', 'agent');
      }
      break;
      
    case 'agent_complete':
      if (agent && message) {
        // Use friendly name in the message if it contains the technical name
        const friendlyMessage = message.replace(agent, getFriendlyAgentName(agent));
        updateCurrentThought(`✓ ${getFriendlyAgentName(agent)} heeft de taak voltooid`, 'agent');
      } else if (agent) {
        updateCurrentThought(`✓ ${getFriendlyAgentName(agent)} heeft relevante informatie gevonden`, 'agent');
      } else {
        updateCurrentThought('✓ Agent heeft de taak voltooid', 'agent');
      }
      break;
      
    case 'thought':
      if (text) {
        // Show the full thought text from the agent - this is very important
        const friendlyAgentName = getFriendlyAgentName(agent || 'AI');
        updateCurrentThought(`📋 Rapport van ${friendlyAgentName}: ${text}`, 'thought');
      }
      break;
      
    case 'token':
      if (text) {
        // On first token, immediately collapse thinking area
        if (currentAnswer === '') {
          hideThinkingArea();
        }
        
        currentAnswer += text;
        updateAssistantMessage(currentAnswer);
      }
      break;
      
    case 'done':
      // Hide thinking area with smooth transition
      hideThinkingArea();
      
      // Show citations if available
      if (answer_json) {
        try {
          const answerData = JSON.parse(answer_json);
          if (answerData.citations && answerData.citations.length > 0) {
            showCitations(answerData.citations);
          }
        } catch (e) {
          console.warn('Failed to parse answer_json:', e);
        }
      }
      
      // Add feedback buttons to the completed message
      const assistantMessages = document.querySelectorAll('.message-assistant');
      if (assistantMessages.length > 0) {
        const lastMessage = assistantMessages[assistantMessages.length - 1];
        addFeedbackButtons(lastMessage);
      }
      
      // Final cleanup
      const statusElements = document.querySelectorAll('.system-status');
      statusElements.forEach(el => el.remove());
      break;
      
    case 'agent_tool_call':
      if (message) {
        updateCurrentThought(message, 'tool');
      }
      break;
      
    case 'agent_tool_result':
      if (message) {
        updateCurrentThought(message, 'tool');
      }
      break;
      
    default:
      // Handle any unknown event types gracefully
      console.warn('Unknown event type:', event, data);
      if (message) {
        updateCurrentThought(message);
      } else if (text) {
        updateCurrentThought(text);
      }
      break;
  }
}

// Initialize chat page
function initializeChatPage() {
  // Check for question parameter
  const urlParams = new URLSearchParams(window.location.search);
  const question = urlParams.get('q');
  
  if (question) {
    // Set the question and send it
    const questionInput = document.getElementById('question');
    if (questionInput) {
      questionInput.value = question;
      // Clear URL parameter
      window.history.replaceState({}, document.title, window.location.pathname);
      // Send the question
      setTimeout(() => sendQuestion(), 500);
    }
  }
  
  // Add enter key listener
  const questionInput = document.getElementById('question');
  if (questionInput) {
    questionInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
      }
    });
  }
}

// Initialize welcome page
function initializeWelcomePage() {
  const questionInput = document.getElementById('welcome-question');
  if (questionInput) {
    questionInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        startChatFromWelcome();
      }
    });
  }
}

// Feedback functionality
function addFeedbackButtons(messageElement) {
  // Check if feedback buttons already exist or are already visible
  const feedbackContainer = messageElement.querySelector('.feedback-buttons-container');
  if (!feedbackContainer || !feedbackContainer.classList.contains('hidden')) {
    return;
  }
  
  // Show the feedback buttons container
  feedbackContainer.classList.remove('hidden');
}

function handleFeedback(button, type) {
  // Remove active state from sibling feedback buttons
  const feedbackButtons = button.parentElement.querySelectorAll('.feedback-action-btn.thumbs-up, .feedback-action-btn.thumbs-down');
  feedbackButtons.forEach(btn => btn.classList.remove('active'));
  
  // Add active state to clicked button
  button.classList.add('active');
  
  // Log feedback (in a real app, you'd send this to your analytics)
  console.log(`Feedback: ${type} for message`);
  
  // Show a brief confirmation with tooltip
  const originalTitle = button.getAttribute('title');
  button.setAttribute('title', 'Bedankt voor je feedback!');
  
  setTimeout(() => {
    button.setAttribute('title', originalTitle);
  }, 2000);
}

function copyAnswer(button) {
  // Find the message content
  const messageElement = button.closest('.message-assistant');
  const proseElement = messageElement.querySelector('.prose');
  
  if (proseElement) {
    // Get the text content without HTML tags
    const textContent = proseElement.innerText;
    
    // Copy to clipboard
    navigator.clipboard.writeText(textContent).then(() => {
      // Show success state
      const originalTitle = button.getAttribute('title');
      const originalIcon = button.innerHTML;
      
      button.classList.add('copied');
      button.setAttribute('title', 'Gekopieerd!');
      button.innerHTML = `
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
        </svg>
      `;
      
      setTimeout(() => {
        button.classList.remove('copied');
        button.setAttribute('title', originalTitle);
        button.innerHTML = originalIcon;
      }, 2000);
    }).catch(err => {
      console.error('Failed to copy text: ', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = textContent;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      
      // Show success state
      const originalTitle = button.getAttribute('title');
      button.classList.add('copied');
      button.setAttribute('title', 'Gekopieerd!');
      setTimeout(() => {
        button.classList.remove('copied');
        button.setAttribute('title', originalTitle);
      }, 2000);
    });
  }
}

// Initialize based on current page
document.addEventListener('DOMContentLoaded', function() {
  if (window.location.pathname.includes('chat.html')) {
    initializeChatPage();
  } else {
    initializeWelcomePage();
  }
});
