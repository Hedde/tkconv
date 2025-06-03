# Tweede Kamer AI - Frontend Demo

Een elegante frontend interface voor de Tweede Kamer AI assistent met real-time streaming responses en chain-of-thought visualisatie.

## Features

### 🎯 Core Functionaliteit
- **Streaming Responses**: Real-time typewriter effect voor AI antwoorden
- **Chain of Thought**: Visualisatie van het denkproces van de AI
- **System Status**: Live updates van backend processing stappen
- **Responsive Design**: Werkt op desktop, tablet en mobiel
- **Markdown Support**: Volledige markdown rendering in antwoorden

### 🎨 UI/UX Features
- **Moderne Interface**: Clean, professionele uitstraling
- **Smooth Animations**: Fade-in effecten en thinking dots
- **Auto-scroll**: Automatisch scrollen naar nieuwe berichten
- **Character Counter**: Real-time karakter telling
- **Loading States**: Visuele feedback tijdens processing

## Bestanden Overzicht

```
demo/
├── index.html      # Welkomstpagina met voorbeeldvragen
├── chat.html       # Chat interface voor gesprekken
├── app.js          # Hoofdlogica voor streaming en UI
├── app.css         # Styling en animaties
├── test.html       # Test pagina voor mock streaming
└── images/         # Logo en afbeeldingen
```

## Hoe het werkt

### 1. Streaming Protocol
De frontend communiceert met de backend via Server-Sent Events (SSE):

```javascript
// Voorbeeld van een streaming request
const response = await fetch('/magentic/ask/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Request-ID': requestId
  },
  body: JSON.stringify({ prompt: question })
});
```

### 2. Event Types
De backend stuurt verschillende event types:

- **`system`**: Status updates (received, planning, finalizing, etc.)
- **`agent_start`**: Agent begint met werken
- **`agent_complete`**: Agent heeft werk voltooid
- **`thought`**: Chain of thought informatie
- **`token`**: Individuele karakters van het antwoord
- **`done`**: Stream voltooid

### 3. UI Updates
Elk event type triggert specifieke UI updates:

```javascript
function handleStreamEvent(data) {
  switch (data.event) {
    case 'system':
      showSystemStatus(data.message);
      break;
    case 'thought':
      showThinking(data.agent, data.text);
      break;
    case 'token':
      currentAnswer += data.text;
      updateAssistantMessage(currentAnswer);
      break;
  }
}
```

## Gebruik

### Lokaal Testen
1. Start de backend server op `localhost:8888`
2. Open `index.html` in een browser
3. Klik op een voorbeeldvraag of typ je eigen vraag

### Test Mode
Open `test.html` voor een mock streaming demo zonder backend:
- Simuleert alle event types
- Toont chain of thought
- Demonstreert typewriter effect

### Configuratie
Pas de backend URL aan in `app.js`:

```javascript
const API_BASE_URL = 'http://localhost:8888';
```

## Technische Details

### Dependencies
- **Tailwind CSS**: Voor styling en responsive design
- **Lucide Icons**: Voor iconen
- **Marked.js**: Voor markdown parsing
- **Inter Font**: Voor typografie

### Browser Support
- Chrome/Edge 88+
- Firefox 87+
- Safari 14+

### Performance
- Optimized voor real-time streaming
- Efficient DOM updates
- Smooth scrolling en animaties
- Memory-efficient event handling

## Customization

### Styling
Pas kleuren en styling aan in `app.css` of via Tailwind config in de HTML bestanden.

### Animaties
Thinking dots en fade-in effecten kunnen worden aangepast in de CSS:

```css
@keyframes thinking {
  0%, 60%, 100% { 
    opacity: 0.3; 
    transform: scale(0.8);
  }
  30% { 
    opacity: 1; 
    transform: scale(1);
  }
}
```

### Event Handling
Voeg nieuwe event types toe in de `handleStreamEvent` functie in `app.js`.

## Troubleshooting

### Veelvoorkomende Problemen
1. **CORS Errors**: Zorg dat de backend CORS headers correct instelt
2. **Streaming Stopt**: Check browser console voor JavaScript errors
3. **Styling Issues**: Controleer of alle CSS bestanden correct laden

### Debug Mode
Open browser developer tools en check de Network tab voor SSE events. 