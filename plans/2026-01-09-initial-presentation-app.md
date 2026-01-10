# Presentation App Implementation Plan

## Overview

Build an AI-powered presentation generation app that creates slides via natural language chat. Forked architecture from form-filling-exp, adapted for HTML-based slide creation with PPTX export.

## Architecture Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Slide storage | Raw HTML | Full flexibility for AI styling |
| Browser preview | HTML rendering | Interactive - users can select/highlight text |
| PPTX export | Node.js subprocess (pptxgenjs) | Best HTML-to-PPTX fidelity |
| Context files | LlamaParse integration | Allow reference docs for content |
| Edit mode | Create only | MVP scope - no PPTX upload |

## Desired End State

After implementation:
1. User can chat to create presentations from scratch
2. Slides render as interactive HTML in browser
3. User can download as PPTX file
4. Multi-turn conversations refine the presentation
5. Context files inform slide content

**Verification**:
- Start backend: `cd backend && uvicorn main:app --reload`
- Start frontend: `cd web && npm run dev`
- Create a presentation via chat, view slides, download PPTX

## What We're NOT Doing

- Uploading/editing existing PPTX files
- Real-time collaborative editing
- Template library/marketplace
- Animation/transition support
- Speaker notes editing

---

## Phase 1: Project Setup & Backend Foundation

### Overview
Create directory structure, Python backend skeleton, and Node.js conversion script.

### Changes Required:

#### 1. Directory Structure
Create the following structure:
```
presentation_app/
├── backend/
│   ├── main.py
│   ├── agent.py
│   ├── pptx_converter/
│   │   ├── convert.js
│   │   └── package.json
│   ├── parser.py
│   ├── requirements.txt
│   └── sessions_data/
├── web/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── types/
│   └── package.json
└── README.md
```

#### 2. Backend Dependencies
**File**: `backend/requirements.txt`
```
fastapi>=0.109.0
uvicorn>=0.27.0
anthropic>=0.52.0
claude-agent-sdk>=0.1.0
pydantic>=2.0.0
python-multipart>=0.0.6
llama-cloud-services>=0.6.0
mcp>=1.0.0
```

#### 3. Node.js PPTX Converter
**File**: `backend/pptx_converter/package.json`
```json
{
  "name": "pptx-converter",
  "version": "1.0.0",
  "type": "module",
  "dependencies": {
    "pptxgenjs": "^3.12.0"
  }
}
```

**File**: `backend/pptx_converter/convert.js`
- Accept JSON input with slides array
- Each slide has: `{ html: string, width: number, height: number }`
- Parse HTML, extract text/images, generate PPTX
- Output to specified path

#### 4. Basic FastAPI Setup
**File**: `backend/main.py`
- FastAPI app with CORS middleware
- Health check endpoint
- Session cleanup background task
- Import structure matching form-filler pattern

### Success Criteria:

#### Automated Verification:
- [ ] `cd backend && pip install -r requirements.txt` succeeds
- [ ] `cd backend/pptx_converter && npm install` succeeds
- [ ] `cd backend && uvicorn main:app --reload` starts without errors
- [ ] `curl http://localhost:8000/health` returns 200

#### Manual Verification:
- [ ] Directory structure matches specification

---

## Phase 2: Session Management & Data Models

### Overview
Implement session state management and slide data models.

### Changes Required:

#### 1. Data Models
**File**: `backend/models.py`

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class SlideLayout(Enum):
    TITLE = "title"
    TITLE_CONTENT = "title_content"
    TWO_COLUMN = "two_column"
    BLANK = "blank"

@dataclass
class Slide:
    index: int
    html: str  # Raw HTML content
    layout: SlideLayout = SlideLayout.BLANK
    notes: str = ""  # Speaker notes (optional)

@dataclass
class Presentation:
    title: str
    slides: list[Slide] = field(default_factory=list)
    theme: dict = field(default_factory=dict)  # Colors, fonts

@dataclass
class PendingEdit:
    edit_id: str
    slide_index: int
    operation: str  # ADD, UPDATE, DELETE, REORDER
    params: dict
    preview: str  # Human-readable description
```

#### 2. Session Class
**File**: `backend/session.py`

```python
class PresentationSession:
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.presentation: Presentation | None = None
        self.pending_edits: list[PendingEdit] = []
        self.applied_edits: list[dict] = []
        self.context_files: list = []
        self.is_continuation: bool = False

    def reset(self): ...
    def soft_reset(self): ...  # Keep presentation, clear pending
```

#### 3. Session Manager
**File**: `backend/session.py`

- Thread-safe session storage with `threading.Lock()`
- SQLite persistence for session metadata
- File system storage for presentations (JSON)
- `get_or_create_session()`, `save_session()`, `load_session()`
- Cleanup old sessions (24-hour expiry)

### Success Criteria:

#### Automated Verification:
- [ ] `python -c "from models import Slide, Presentation; print('OK')"` works
- [ ] `python -c "from session import PresentationSession, SessionManager; print('OK')"` works

#### Manual Verification:
- [ ] Session persists across server restarts

---

## Phase 3: Agent Tools & Claude Integration

### Overview
Define presentation manipulation tools using Claude Agent SDK.

### Changes Required:

#### 1. Tool Definitions
**File**: `backend/agent.py`

Define tools using `@tool()` decorator:

| Tool | Description | Input | Output |
|------|-------------|-------|--------|
| `create_presentation` | Start new presentation | `{title: str}` | `{success, slide_count: 0}` |
| `add_slide` | Add slide with HTML | `{html: str, position?: int, layout?: str}` | `{slide_index}` |
| `update_slide` | Modify slide HTML | `{slide_index: int, html: str}` | `{success}` |
| `delete_slide` | Remove slide | `{slide_index: int}` | `{success}` |
| `reorder_slides` | Move slide | `{from_index: int, to_index: int}` | `{success}` |
| `list_slides` | Get all slides | `{}` | `{slides: [{index, html_preview}]}` |
| `get_slide` | Get slide details | `{slide_index: int}` | `{html, layout}` |
| `set_theme` | Set colors/fonts | `{theme: dict}` | `{success}` |
| `get_pending_edits` | Review staged changes | `{}` | `{edits: [...]}` |
| `commit_edits` | Apply all changes | `{}` | `{applied_count}` |

#### 2. MCP Server Registration
```python
PRESENTATION_TOOLS = [
    tool_create_presentation,
    tool_add_slide,
    tool_update_slide,
    # ... etc
]

pres_server = create_sdk_mcp_server(
    name="presentation",
    version="1.0.0",
    tools=PRESENTATION_TOOLS
)
```

#### 3. System Prompts
**New Presentation Mode:**
```
You are a presentation creation assistant. Create professional slides using HTML.

WORKFLOW:
1. Use create_presentation to start
2. Use add_slide to add slides with HTML content
3. Use commit_edits to finalize

HTML GUIDELINES:
- Use semantic HTML (h1, h2, p, ul, li)
- Use inline styles for positioning and colors
- Keep text concise - bullet points, not paragraphs
- Slide dimensions: 960x540px (16:9)

DESIGN PRINCIPLES:
- One main idea per slide
- Consistent color scheme throughout
- Use contrast for readability
```

**Continuation Mode:**
```
You are editing an existing presentation.

CRITICAL: Only modify slides the user specifically requests.
Use list_slides to see current content before changes.
```

#### 4. Agent Streaming Function
**Function**: `run_agent_stream()`

Parameters:
- `instructions: str`
- `is_continuation: bool`
- `resume_session_id: str | None`
- `user_session_id: str | None`
- `context_files: list`

Yields SSE events matching form-filler pattern.

### Success Criteria:

#### Automated Verification:
- [ ] `python -c "from agent import PRESENTATION_TOOLS; print(len(PRESENTATION_TOOLS))"` shows tool count
- [ ] Tools can be imported without SDK (graceful fallback)

#### Manual Verification:
- [ ] Each tool executes correctly in isolation

---

## Phase 4: Backend API Endpoints

### Overview
Implement FastAPI endpoints for streaming, sessions, and export.

### Changes Required:

#### 1. Main Streaming Endpoint
**File**: `backend/main.py`

```python
@app.post("/agent-stream")
async def agent_stream(
    instructions: str = Form(...),
    is_continuation: bool = Form(False),
    resume_session_id: Optional[str] = Form(None),
    user_session_id: Optional[str] = Form(None),
):
    async def event_stream():
        async for message in run_agent_stream(...):
            yield f"data: {json.dumps(message)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )
```

#### 2. Session Endpoints
```python
@app.get("/session/{session_id}")
async def get_session(session_id: str):
    # Returns presentation JSON

@app.get("/session/{session_id}/slides")
async def get_slides(session_id: str):
    # Returns slides array with HTML

@app.get("/session/{session_id}/export")
async def export_pptx(session_id: str):
    # Calls Node.js converter, returns PPTX bytes
```

#### 3. Context Files Endpoint
```python
@app.post("/parse-files")
async def parse_files_endpoint(
    files: list[UploadFile],
    user_session_id: str = Form(...),
    parse_mode: str = Form("cost_effective"),
):
    # Stream parsing progress via SSE
```

#### 4. PPTX Export Implementation
```python
async def export_to_pptx(presentation: Presentation) -> bytes:
    # 1. Write slides JSON to temp file
    # 2. Run: node pptx_converter/convert.js input.json output.pptx
    # 3. Read output.pptx bytes
    # 4. Cleanup temp files
    # 5. Return bytes
```

### Success Criteria:

#### Automated Verification:
- [ ] `curl -X POST http://localhost:8000/agent-stream -F "instructions=Create a hello world presentation"` streams events
- [ ] Export endpoint returns valid PPTX bytes

#### Manual Verification:
- [ ] SSE events render correctly in browser

---

## Phase 5: Frontend Foundation

### Overview
Set up Next.js frontend with chat panel and API client.

### Changes Required:

#### 1. Type Definitions
**File**: `web/src/types/index.ts`

```typescript
export interface Slide {
  index: number;
  html: string;
  layout: string;
}

export interface Presentation {
  title: string;
  slides: Slide[];
  theme: Record<string, string>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  status?: 'pending' | 'streaming' | 'complete' | 'error';
  agentLog?: AgentLogEntry[];
}

export interface StreamEvent {
  type: 'init' | 'status' | 'tool_use' | 'assistant' | 'complete' | 'error';
  // ... fields per type
}
```

#### 2. API Client
**File**: `web/src/lib/api.ts`

```typescript
export async function* streamAgent(options: {
  instructions: string;
  isContinuation: boolean;
  resumeSessionId?: string;
  userSessionId?: string;
}): AsyncGenerator<StreamEvent> {
  // SSE streaming pattern from form-filler
}

export async function getSessionSlides(sessionId: string): Promise<Slide[]>
export async function exportPptx(sessionId: string): Promise<Blob>
export async function* streamParseFiles(...): AsyncGenerator<ParseProgress>
```

#### 3. Session Persistence
**File**: `web/src/lib/session.ts`

- `generateSessionId()`
- `setSessionInUrl()` / `getSessionFromUrl()`
- `saveSessionToStorage()` / `loadSessionFromStorage()`
- Store: messages, userSessionId (not slides - fetch from backend)

#### 4. Chat Components (Fork from form-filler)
**Files**:
- `web/src/components/ChatPanel.tsx`
- `web/src/components/ChatMessage.tsx`
- `web/src/components/AgentActivityLog.tsx`
- `web/src/components/ContextFilesUpload.tsx`

Adapt for presentation context (remove PDF-specific logic).

### Success Criteria:

#### Automated Verification:
- [ ] `cd web && npm run build` succeeds
- [ ] `cd web && npm run lint` passes

#### Manual Verification:
- [ ] Chat panel renders and accepts input
- [ ] SSE events display in agent activity log

---

## Phase 6: Slide Viewer & Export UI

### Overview
Implement HTML slide rendering and PPTX download.

### Changes Required:

#### 1. Slide Renderer Component
**File**: `web/src/components/SlideRenderer.tsx`

```tsx
interface SlideRendererProps {
  html: string;
  width?: number;  // Default 960
  height?: number; // Default 540
  scale?: number;  // For thumbnail vs full view
}

export function SlideRenderer({ html, width, height, scale }: SlideRendererProps) {
  return (
    <div
      className="slide-container"
      style={{
        width: width * scale,
        height: height * scale,
        transform: `scale(${scale})`,
        transformOrigin: 'top left',
      }}
    >
      <div
        className="slide-content"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}
```

#### 2. Slide Grid Navigation
**File**: `web/src/components/SlideGrid.tsx`

- Thumbnail grid of all slides
- Click to select/focus slide
- Shows slide numbers
- Highlights current slide

#### 3. Main Slide Viewer
**File**: `web/src/components/SlideViewer.tsx`

- Full-size current slide display
- Previous/Next navigation buttons
- Slide counter (e.g., "3 / 10")
- Keyboard navigation (arrow keys)

#### 4. Export Menu
**File**: `web/src/components/ExportMenu.tsx`

```tsx
export function ExportMenu({ sessionId }: { sessionId: string }) {
  const handleDownload = async () => {
    const blob = await exportPptx(sessionId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'presentation.pptx';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <button onClick={handleDownload}>
      Download PPTX
    </button>
  );
}
```

#### 5. Main Page Layout
**File**: `web/src/app/page.tsx`

Two-panel layout:
- **Left (50%)**: Slide viewer + grid
- **Right (50%)**: Chat panel

State management:
- `presentation: Presentation | null`
- `currentSlideIndex: number`
- `messages: ChatMessage[]`
- `agentSessionId`, `userSessionId`

### Success Criteria:

#### Automated Verification:
- [ ] `npm run build` succeeds
- [ ] `npm run lint` passes

#### Manual Verification:
- [ ] Slides render with selectable text
- [ ] Navigation between slides works
- [ ] PPTX downloads and opens in PowerPoint

---

## Phase 7: Integration & Polish

### Overview
End-to-end testing, error handling, and final polish.

### Changes Required:

#### 1. Error Handling
- Backend: Proper HTTP error codes, error event in SSE
- Frontend: Error boundaries, toast notifications
- Agent: Graceful tool failure handling

#### 2. Loading States
- Chat: Streaming indicator during agent response
- Slides: Skeleton loader while fetching
- Export: Progress indicator during PPTX generation

#### 3. Styling Polish
**File**: `web/src/app/globals.css`

- Color variables (accent, success, error, neutrals)
- Slide container shadow and border
- Responsive layout breakpoints
- Custom scrollbar styling

#### 4. Session Restoration
- URL contains session ID
- On page load: fetch presentation from backend
- Restore chat history from localStorage
- Resume agent conversation with `resume_session_id`

#### 5. End-to-End Test Scenarios
1. Create new presentation with 3 slides
2. Ask to modify slide 2
3. Refresh page, verify restoration
4. Download PPTX, open in PowerPoint
5. Upload context file, create slides from it

### Success Criteria:

#### Automated Verification:
- [ ] Backend starts without errors
- [ ] Frontend builds without errors
- [ ] No console errors in browser

#### Manual Verification:
- [ ] Complete flow: chat → slides → download works
- [ ] Session persists across page refresh
- [ ] Error states display appropriately
- [ ] PPTX opens correctly in PowerPoint/Google Slides

---

## Testing Strategy

### Unit Tests
- Session management: create, save, load, cleanup
- Tool functions: each tool in isolation
- PPTX converter: HTML input → valid PPTX

### Integration Tests
- Agent streaming: full conversation flow
- API endpoints: request/response validation
- Frontend: component rendering

### Manual Testing Steps
1. Start backend: `uvicorn main:app --reload`
2. Start frontend: `npm run dev`
3. Open http://localhost:3000
4. Type: "Create a presentation about climate change with 5 slides"
5. Verify slides appear in viewer
6. Type: "Make the title slide more impactful"
7. Verify only slide 1 updates
8. Click Download PPTX
9. Open in PowerPoint, verify content matches

---

## References

- Research document: `prompts/research.md`
- Form-filler backend patterns: `/Users/jerryliu/Programming/other/jerry-exp-2025-12-28/form-filling-exp/backend/agent.py`
- Form-filler frontend patterns: `/Users/jerryliu/Programming/other/jerry-exp-2025-12-28/form-filling-exp/web/src/app/page.tsx`
- pptxgenjs docs: https://gitbrent.github.io/PptxGenJS/
- Claude Agent SDK: https://platform.claude.com/docs/en/agent-sdk/overview
