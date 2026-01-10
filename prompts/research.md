# Research: Building a PowerPoint Chat Agent

> Comprehensive research for building an AI-powered presentation generation agent, forked from the form-filling chatbot template.

---

## Table of Contents
1. [Form-Filling Repository Analysis](#part-1-form-filling-repository-analysis)
2. [PowerPoint Generation Approaches](#part-2-powerpoint-generation-approaches)
3. [Competitive Analysis](#part-3-competitive-analysis)
4. [Recommended Architecture](#part-4-recommended-architecture)
5. [Implementation Plan](#part-5-implementation-plan)
6. [Sources](#sources)

---

## Part 1: Form-Filling Repository Analysis

### Repository Location
`/Users/jerryliu/Programming/other/jerry-exp-2025-12-28/form-filling-exp`
GitHub: https://github.com/jerryjliu/form_filling_app

### Repository Structure

```
form-filling-exp/
├── backend/                     # FastAPI + Claude Agent SDK
│   ├── main.py                 # FastAPI server (900+ lines, 7+ endpoints)
│   ├── agent.py                # Claude Agent SDK integration (1400+ lines)
│   ├── pdf_processor.py        # PyMuPDF-based PDF field detection (350+ lines)
│   ├── llm.py                  # Structured outputs for field mapping (270+ lines)
│   ├── parser.py               # LlamaParse integration (150+ lines)
│   ├── sessions.db             # SQLite persistence
│   └── sessions_data/          # PDF file storage
├── web/                        # Next.js + React Frontend
│   ├── src/
│   │   ├── app/page.tsx        # Main app component
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx   # Chat UI with message input
│   │   │   ├── ChatMessage.tsx # Individual message rendering
│   │   │   ├── PdfViewer.tsx   # PDF display with mode toggle
│   │   │   ├── ContextFilesUpload.tsx  # File upload with drag-drop
│   │   │   └── AgentActivityLog.tsx    # Agent iteration details
│   │   ├── lib/
│   │   │   ├── api.ts          # API client with SSE support
│   │   │   └── session.ts      # Session persistence (localStorage + backend)
│   │   └── types/
│   │       └── index.ts        # TypeScript interfaces
│   └── package.json
├── requirements.txt
└── README.md
```

### Technology Stack

#### Backend

| Technology | Version | Purpose |
|-----------|---------|---------|
| FastAPI | >=0.109.0 | Web framework with async support |
| Uvicorn | >=0.27.0 | ASGI server |
| Claude Agent SDK | >=0.1.0 | Agent framework with MCP tools |
| Anthropic SDK | >=0.52.0 | Claude API client |
| PyMuPDF (fitz) | >=1.24.0 | PDF processing and field detection |
| MCP | >=1.0.0 | Model Context Protocol |
| LlamaCloud | >=0.6.0 | File parsing (optional) |
| Pydantic | >=2.0.0 | Data validation & structured outputs |
| python-multipart | >=0.0.6 | File upload handling |

#### Frontend

| Technology | Version | Purpose |
|-----------|---------|---------|
| Next.js | 16.1.1 | React framework with SSR |
| React | 19.2.3 | UI library |
| TypeScript | ^5 | Type safety |
| Tailwind CSS | ^4 | Utility-first styling |
| ESLint | ^9 | Code quality |

### Key Architectural Patterns

#### 1. Tool Definition with `@tool` Decorator

The Claude Agent SDK uses decorators to define MCP-compatible tools:

```python
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    tool,
    create_sdk_mcp_server,
    AssistantMessage, UserMessage, SystemMessage, ResultMessage,
    TextBlock, ToolUseBlock, ToolResultBlock,
)

@tool("load_pdf", "Load a PDF file for form filling", {"pdf_path": str})
async def tool_load_pdf(args: dict[str, Any]) -> dict[str, Any]:
    """Load PDF and detect all form fields."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}

    pdf_path = args.get("pdf_path")
    # Implementation...
    return {"success": True, "field_count": len(fields)}

# Register all tools with MCP server
FORM_TOOLS = [
    tool_load_pdf,
    tool_list_all_fields,
    tool_search_fields,
    tool_get_field_details,
    tool_set_field,
    tool_get_pending_edits,
    tool_commit_edits,
]

form_server = create_sdk_mcp_server(
    name="form-filler",
    version="1.0.0",
    tools=FORM_TOOLS
)
```

#### 2. Agent Configuration and Execution

```python
options = ClaudeAgentOptions(
    system_prompt=system_prompt,
    mcp_servers={"forms": form_server},
    allowed_tools=[
        "mcp__forms__load_pdf",
        "mcp__forms__list_all_fields",
        "mcp__forms__search_fields",
        "mcp__forms__get_field_details",
        "mcp__forms__set_field",
        "mcp__forms__get_pending_edits",
        "mcp__forms__commit_edits",
    ],
    resume=resume_session_id,  # For multi-turn conversations
)

async with ClaudeSDKClient(options=options) as client:
    await client.query(prompt)
    async for message in client.receive_response():
        # Process streaming messages
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    yield {"type": "assistant", "text": block.text}
                elif isinstance(block, ToolUseBlock):
                    yield {"type": "tool_use", "tool_calls": [...]}
```

#### 3. Session Context Management with ContextVar

```python
from contextvars import ContextVar

_current_session: ContextVar[FormFillingSession | None] = ContextVar(
    'current_session',
    default=None
)

def get_current_session() -> FormFillingSession | None:
    """Get the current session from context (async-safe)."""
    return _current_session.get()

def set_current_session(session: FormFillingSession | None):
    """Set the current session in context."""
    _current_session.set(session)
```

#### 4. SSE Streaming for Real-Time Updates

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

@app.post("/fill-agent-stream")
async def fill_pdf_agent_stream(
    pdf_file: UploadFile,
    instructions: str = Form(...),
    is_continuation: bool = Form(False),
    user_session_id: str | None = Form(None),
    resume_session_id: str | None = Form(None),
):
    async def event_stream():
        try:
            async for message in run_agent_stream(
                pdf_bytes=await pdf_file.read(),
                instructions=instructions,
                is_continuation=is_continuation,
                user_session_id=user_session_id,
                resume_session_id=resume_session_id,
            ):
                yield f"data: {json.dumps(message, default=str)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

#### 5. Multi-Turn Conversation Flow

**First Turn:**
1. User uploads PDF via `analyzePdf()` endpoint
2. Backend detects all form fields with PyMuPDF
3. User types instructions via `streamAgentFill()`
4. Agent processes, stages edits, commits changes
5. Backend creates `user_session_id`, stores original + filled PDFs
6. Frontend saves session to localStorage + URL query param

**Subsequent Turns:**
1. User types new instructions
2. Frontend sends with:
   - `isContinuation=true`
   - `filledPdfBytes` (from previous turn)
   - `previousEdits` (cumulative edit history)
   - `resumeSessionId` (Claude SDK session for context)
   - `userSessionId` (backend session)
3. Agent loads filled PDF as starting point
4. Agent ONLY modifies requested fields (preserves existing)
5. Saves updated PDF to backend for next turn

### Form-Filling Tools (7 Total)

| Tool | Description | Input | Output |
|------|-------------|-------|--------|
| `load_pdf` | Load PDF and detect fields | `{pdf_path: str}` | `{success, field_count}` |
| `list_all_fields` | List all form fields with current values | `{}` | `{fields: [...]}` |
| `search_fields` | Find fields by query string | `{query: str}` | `{matching_fields: [...]}` |
| `get_field_details` | Get details about specific field | `{field_id: str}` | `{field: {...}}` |
| `set_field` | Stage a field edit (parallel-friendly) | `{field_id, value}` | `{success, staged}` |
| `get_pending_edits` | Review all staged edits | `{}` | `{pending_edits: [...]}` |
| `commit_edits` | Apply staged edits and save PDF | `{}` | `{applied_count, saved_path}` |

### System Prompt Design

The form-filler uses two distinct system prompts:

**Standard Mode (First Turn):**
```
You are a PDF form filling assistant. Your job is to help users fill out PDF forms...

WORKFLOW:
1. First, use load_pdf to load the document
2. Use list_all_fields to see available fields
3. Use set_field to stage edits (you can call this in parallel!)
4. Use commit_edits to apply all changes

IMPORTANT: Call set_field multiple times in parallel for efficiency.
```

**Continuation Mode (Multi-Turn):**
```
You are continuing to edit a PDF form. The form already has some fields filled.

CRITICAL: Only modify fields the user specifically asks about.
DO NOT change fields that are already filled unless explicitly requested.

Use list_all_fields to see current values before making changes.
```

### SSE Event Types

```typescript
type StreamEvent =
  | { type: 'init'; message: string }
  | { type: 'status'; message: string }
  | { type: 'tool_use'; tool_calls: ToolCall[]; friendly?: string[] }
  | { type: 'assistant'; text?: string }
  | { type: 'user'; content: string }
  | { type: 'complete'; applied_count: number; applied_edits: Record<string, unknown>; session_id: string; user_session_id: string }
  | { type: 'pdf_ready'; pdf_bytes: string }  // Hex-encoded
  | { type: 'error'; error: string }
```

### Frontend SSE Handler Pattern

```typescript
export async function* streamAgentFill(options: StreamAgentFillOptions): AsyncGenerator<StreamEvent> {
  const formData = new FormData();
  formData.append('pdf_file', options.pdfFile);
  formData.append('instructions', options.instructions);
  // ... other fields

  const response = await fetch(`${API_BASE}/fill-agent-stream`, {
    method: 'POST',
    body: formData,
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const event: StreamEvent = JSON.parse(line.slice(6));
        yield event;
      }
    }
  }
}
```

### Session Persistence Architecture

**Backend (SQLite + File System):**
```python
# sessions.db schema
CREATE TABLE sessions (
    user_session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    original_pdf_path TEXT,
    filled_pdf_path TEXT,
    edits_json TEXT,
    claude_session_id TEXT
);

# File storage
sessions_data/
├── {user_session_id}/
│   ├── original.pdf
│   ├── filled.pdf
│   └── metadata.json
```

**Frontend (localStorage + URL):**
```typescript
// Save session
localStorage.setItem(`session_${fileHash}`, userSessionId);
window.history.pushState({}, '', `?session=${userSessionId}`);

// Restore session
const urlSession = new URLSearchParams(window.location.search).get('session');
const storedSession = localStorage.getItem(`session_${fileHash}`);
```

---

## Part 2: PowerPoint Generation Approaches

### Approach 1: Claude Built-in Document Skills

Anthropic provides production-ready document skills in the [anthropics/skills](https://github.com/anthropics/skills) repository.

#### How to Enable Skills

```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    cwd="/path/to/project",
    setting_sources=["user", "project"],  # Required to load skills
    allowed_tools=["Skill", "Read", "Write", "Bash"]
)

async for message in query(prompt="Create a presentation about AI", options=options):
    print(message)
```

#### PPTX Skill Capabilities

**Reading & Analysis:**
- Text extraction via `python -m markitdown path-to-file.pptx`
- Raw XML access for comments, speaker notes, animations
- Typography and color scheme analysis from theme files
- Comprehensive text inventory generation

**Creation Workflows:**

1. **HTML-to-PPTX (From Scratch)**
   - Design slides using HTML/CSS
   - Render to PPTX with precise positioning
   - 17+ pre-built color palettes
   - Web-safe fonts (Arial, Helvetica, Georgia, etc.)

   ```bash
   # Workflow
   1. Read html2pptx.md completely
   2. State design approach before coding
   3. Generate HTML slides
   4. Convert to PPTX
   5. Validate output
   ```

2. **Template-Based Creation**
   - Duplicate and rearrange existing slides
   - Extract template content and create thumbnail grids
   - Use `rearrange.py` for slide ordering
   - Use `replace.py` with JSON schemas for text replacement

   ```bash
   # Workflow
   1. Unpack template with ooxml/scripts/unpack.py
   2. Generate thumbnail grid for visual analysis
   3. Create text inventory with inventory.py
   4. Generate replacement JSON
   5. Apply replacements with replace.py
   6. Validate output
   ```

3. **Direct XML Editing (OOXML)**
   - Unpack, modify XML, validate, repack
   - Granular control over document structure
   - Required for advanced formatting

**Skill File Structure:**
```
pptx/
├── SKILL.md          # Main workflow documentation
├── html2pptx.md      # HTML conversion guide
├── ooxml.md          # XML editing guide
├── scripts/
│   ├── unpack.py     # Unpack PPTX to XML
│   ├── repack.py     # Repack XML to PPTX
│   ├── rearrange.py  # Slide reordering
│   ├── inventory.py  # Text extraction
│   └── replace.py    # Text replacement
└── palettes/         # Color palette definitions
```

**Dependencies:**
- Python: markitdown, defusedxml
- Node.js: pptxgenjs, playwright, sharp
- System: LibreOffice (`soffice`), Poppler (`pdftoppm`), Pandoc

### Approach 2: Python-pptx Library (Custom Tools)

[python-pptx](https://python-pptx.readthedocs.io/) is a production-ready Python library for programmatic PowerPoint manipulation.

#### Key Characteristics
- No Microsoft PowerPoint required
- Works on macOS, Linux, Windows
- MIT licensed
- 3.1k+ GitHub stars, 28.4k+ repos using it
- Supports PPTX format (PowerPoint 2007+)

#### Core Classes

| Class | Purpose |
|-------|---------|
| `Presentation` | Main entry point for .pptx files |
| `Slide` | Individual slides |
| `Shape` | AutoShapes, pictures, text boxes |
| `Table` | Tabular data |
| `Chart` | Data visualization |
| `Placeholder` | Template slots |

#### Code Patterns

**Creating a Presentation:**
```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# Create new or open existing
prs = Presentation()  # New
# prs = Presentation('template.pptx')  # From template
```

**Adding Slides:**
```python
# Slide layouts (0-indexed)
# 0: Title Slide
# 1: Title and Content
# 5: Title Only
# 6: Blank

# Add title slide
title_layout = prs.slide_layouts[0]
slide = prs.slides.add_slide(title_layout)

# Populate placeholders
title = slide.shapes.title
title.text = "Quarterly Report"

subtitle = slide.placeholders[1]
subtitle.text = "Q4 2025 Results"
```

**Text Boxes with Formatting:**
```python
# Add text box
left = Inches(1)
top = Inches(2)
width = Inches(6)
height = Inches(1.5)

txBox = slide.shapes.add_textbox(left, top, width, height)
tf = txBox.text_frame
tf.word_wrap = True

# First paragraph
p = tf.paragraphs[0]
p.text = "Main heading"
p.font.bold = True
p.font.size = Pt(24)
p.font.color.rgb = RGBColor(0, 0, 128)
p.alignment = PP_ALIGN.CENTER

# Add more paragraphs
p2 = tf.add_paragraph()
p2.text = "Supporting text"
p2.font.size = Pt(14)
p2.level = 1  # Indent level
```

**Adding Images:**
```python
# Add image with specified position and size
img_path = 'chart.png'
left = Inches(2)
top = Inches(3)
height = Inches(3)  # Width auto-calculated to maintain aspect

pic = slide.shapes.add_picture(img_path, left, top, height=height)

# Or specify width
pic = slide.shapes.add_picture(img_path, left, top, width=Inches(4))
```

**Creating Charts:**
```python
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE

# Prepare data
chart_data = CategoryChartData()
chart_data.categories = ['Q1', 'Q2', 'Q3', 'Q4']
chart_data.add_series('Revenue', (1200, 1400, 1100, 1500))
chart_data.add_series('Profit', (400, 500, 300, 600))

# Add chart
x, y, cx, cy = Inches(1), Inches(2), Inches(8), Inches(4)
chart = slide.shapes.add_chart(
    XL_CHART_TYPE.COLUMN_CLUSTERED,  # Or LINE, PIE, BAR_CLUSTERED, etc.
    x, y, cx, cy, chart_data
).chart

# Customize chart
chart.has_legend = True
chart.legend.include_in_layout = False
```

**Creating Tables:**
```python
# Add table
rows, cols = 4, 3
left = Inches(1)
top = Inches(2)
width = Inches(8)
height = Inches(2)

table_shape = slide.shapes.add_table(rows, cols, left, top, width, height)
table = table_shape.table

# Set column widths
table.columns[0].width = Inches(2)
table.columns[1].width = Inches(3)
table.columns[2].width = Inches(3)

# Populate cells
table.cell(0, 0).text = "Product"
table.cell(0, 1).text = "Q3 Sales"
table.cell(0, 2).text = "Q4 Sales"

# Style header row
for cell in table.rows[0].cells:
    cell.fill.solid()
    cell.fill.fore_color.rgb = RGBColor(0, 112, 192)
    cell.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 255, 255)
    cell.text_frame.paragraphs[0].font.bold = True
```

**Saving:**
```python
prs.save('output.pptx')

# Or to bytes for streaming
from io import BytesIO
buffer = BytesIO()
prs.save(buffer)
pptx_bytes = buffer.getvalue()
```

#### Working with Existing Presentations

```python
# Open existing
prs = Presentation('existing.pptx')

# Iterate slides
for idx, slide in enumerate(prs.slides):
    print(f"Slide {idx + 1}")
    for shape in slide.shapes:
        if shape.has_text_frame:
            print(f"  Text: {shape.text_frame.text[:50]}...")
        if shape.has_table:
            print(f"  Table: {shape.table.rows} rows")

# Analyze placeholders in a layout
for layout in prs.slide_layouts:
    print(f"Layout: {layout.name}")
    for placeholder in layout.placeholders:
        print(f"  {placeholder.placeholder_format.idx}: {placeholder.placeholder_format.type}")
```

### Approach 3: Hybrid (Recommended)

Combine python-pptx for core operations with Claude skill patterns for design:

**Use python-pptx for:**
- Programmatic slide creation/editing
- Session management and state
- Fine-grained content manipulation
- Export to bytes for streaming

**Use Claude skill patterns for:**
- Design decisions (colors, layouts, typography)
- Template analysis and recommendations
- Complex formatting requirements
- Visual validation workflows

---

## Part 3: Competitive Analysis

### Gamma.app (Leading AI Presentation Tool)

#### Core Capabilities

**AI-Powered Generation:**
- Generate presentations from text prompts in seconds
- Understands vague prompts, generates multi-section decks
- Can rewrite, summarize, suggest media (images, GIFs)

**Gamma Agent (2025):**
- Real-time web research with citations
- Content integration from any source
- Instant redesigns via natural language
- Structure optimization for engagement
- Grammar fixes, content length adjustment
- Translation to 60+ languages

**Output Formats:**
- Traditional presentations with Smart Diagrams
- Instagram carousels and Stories
- LinkedIn posts
- Interactive documents with embedded content
- Responsive websites
- Export to PPT, PDF, Google Slides

#### Design Features

- 40+ modern, minimalist templates
- 17 color palette options
- Interactive elements (charts, videos, surveys)
- Multi-theme generation (preview in various themes)
- AI image editing directly in platform
- Figma, YouTube embeds without coding

#### Pricing

| Tier | Price | Key Features |
|------|-------|--------------|
| Free | $0 | 400 credits to test |
| Plus | $8/mo | Unlimited AI, no branding |
| Pro | $15/mo | API access, 50 monthly API generations, Zapier |
| Ultra | $39/mo | Studio Mode, cinematic effects |

#### Limitations

- Limited font customization (modern sans-serif only)
- Can hallucinate facts/data
- ~40 templates (fewer than traditional tools)
- No precise font size control

### Key Learnings for Our App

1. **Natural Language First** - Primary interaction is conversational
2. **Template Support** - Users expect pre-built starting points
3. **Multiple Export Formats** - PPTX, PDF, images all matter
4. **Real-Time Preview** - See changes as they happen
5. **Design Automation** - Auto colors, layouts highly valued
6. **Iteration Support** - Multi-turn refinement is essential
7. **Web Research Integration** - Adding context from the web is powerful

---

## Part 4: Recommended Architecture

### Technology Choice: Hybrid Approach (Confirmed)

**Decision:** Use python-pptx for core CRUD operations with Claude skill patterns for design/formatting.

**Rationale:**
- python-pptx provides full control and simpler dependencies
- Claude skill patterns offer design intelligence for formatting
- Form-filler architecture provides proven session/streaming infrastructure

**Capabilities (Confirmed):**
- Create new presentations from scratch
- Edit/modify existing PPTX files
- Multi-turn conversation support

**Export Formats (Confirmed):**
- PPTX (primary download)
- PDF export
- Thumbnail generation for slide previews

### Proposed Tools for Presentation Agent

#### Core Tools (Mapped from Form-Filler)

| Form-Filler Tool | Presentation Tool | Purpose |
|-----------------|-------------------|---------|
| `load_pdf` | `load_presentation` | Load existing PPTX file |
| `list_all_fields` | `list_slides` | List all slides with summaries |
| `search_fields` | `search_slides` | Find slides by content |
| `get_field_details` | `get_slide_content` | Get slide text/shapes/images |
| `set_field` | `update_slide` | Modify slide content |
| `get_pending_edits` | `get_pending_changes` | Review staged changes |
| `commit_edits` | `save_presentation` | Save all changes |

#### Additional Tools

| Tool | Description | Input | Output |
|------|-------------|-------|--------|
| `create_presentation` | Create new from scratch or template | `{title?, template?}` | `{presentation_id}` |
| `add_slide` | Insert new slide at position | `{layout, position?, content?}` | `{slide_index}` |
| `delete_slide` | Remove slide | `{slide_index}` | `{success}` |
| `reorder_slides` | Change slide order | `{from_index, to_index}` | `{success}` |
| `add_text` | Add text box to slide | `{slide_index, text, position, style?}` | `{shape_id}` |
| `add_image` | Add image to slide | `{slide_index, image_path, position, size?}` | `{shape_id}` |
| `add_chart` | Add chart to slide | `{slide_index, chart_type, data}` | `{shape_id}` |
| `add_table` | Add table to slide | `{slide_index, rows, cols, data}` | `{shape_id}` |
| `set_theme` | Apply color theme | `{theme_name}` | `{success}` |
| `export_pdf` | Export as PDF | `{}` | `{pdf_bytes}` |
| `generate_thumbnails` | Create preview images | `{slide_indices?}` | `{thumbnails: [...]}` |

### Data Models

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class SlideLayout(Enum):
    TITLE = 0
    TITLE_CONTENT = 1
    SECTION_HEADER = 2
    TWO_CONTENT = 3
    COMPARISON = 4
    TITLE_ONLY = 5
    BLANK = 6
    CONTENT_WITH_CAPTION = 7
    PICTURE_WITH_CAPTION = 8

@dataclass
class SlideInfo:
    index: int
    layout: SlideLayout
    title: Optional[str]
    content_summary: str
    shape_count: int
    has_images: bool
    has_tables: bool
    has_charts: bool

@dataclass
class ShapeInfo:
    shape_id: str
    shape_type: str  # TEXT_BOX, PICTURE, TABLE, CHART, AUTO_SHAPE
    position: tuple[float, float, float, float]  # left, top, width, height (inches)
    text: Optional[str]

@dataclass
class PendingEdit:
    edit_id: str
    slide_index: int
    operation: str  # ADD_TEXT, UPDATE_TEXT, ADD_IMAGE, DELETE_SHAPE, etc.
    params: dict
    preview: str  # Human-readable description
```

### File Structure (Forked from Form-Filler)

```
presentation_app/
├── backend/
│   ├── main.py                  # FastAPI server (fork from form-filler)
│   │   ├── /health
│   │   ├── /analyze-presentation  # Analyze uploaded PPTX
│   │   ├── /agent-stream          # Main agent endpoint (SSE)
│   │   ├── /session/{id}          # Get session state
│   │   ├── /session/{id}/download # Download PPTX
│   │   ├── /session/{id}/pdf      # Download PDF
│   │   └── /session/{id}/thumbnails # Get slide thumbnails
│   │
│   ├── agent.py                 # Claude Agent SDK integration
│   │   ├── PRESENTATION_TOOLS   # Tool definitions
│   │   ├── pres_server          # MCP server
│   │   ├── run_agent_stream()   # Main agent loop
│   │   └── System prompts       # Standard + continuation modes
│   │
│   ├── pptx_processor.py        # NEW: python-pptx operations
│   │   ├── PresentationSession  # Session state class
│   │   ├── load_presentation()  # Load PPTX bytes
│   │   ├── create_presentation()# Create new PPTX
│   │   ├── get_slide_info()     # Extract slide data
│   │   ├── add_slide()          # Insert slide
│   │   ├── update_slide()       # Modify content
│   │   ├── export_pdf()         # Convert to PDF
│   │   └── generate_thumbnail() # Create PNG preview
│   │
│   ├── parser.py                # Reuse for context files
│   ├── sessions.db              # SQLite session storage
│   ├── sessions_data/           # PPTX file storage
│   │   └── {session_id}/
│   │       ├── original.pptx
│   │       ├── current.pptx
│   │       └── thumbnails/
│   │           ├── slide_0.png
│   │           └── slide_1.png
│   │
│   └── requirements.txt
│       # Add:
│       # python-pptx>=0.6.21
│       # pdf2image>=1.16.0  (for PDF export)
│       # Pillow>=9.0.0      (for thumbnails)
│
├── web/
│   ├── src/
│   │   ├── app/page.tsx         # Main app (fork with PPTX support)
│   │   │
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx    # Reuse (chat UI)
│   │   │   ├── ChatMessage.tsx  # Reuse (message display)
│   │   │   ├── PptxViewer.tsx   # NEW: Current slide preview
│   │   │   ├── SlideGrid.tsx    # NEW: Thumbnail grid navigation
│   │   │   ├── SlideEditor.tsx  # NEW: Visual editing (optional)
│   │   │   └── ExportMenu.tsx   # NEW: Download options
│   │   │
│   │   ├── lib/
│   │   │   ├── api.ts           # Fork with PPTX endpoints
│   │   │   └── session.ts       # Reuse (session management)
│   │   │
│   │   └── types/
│   │       └── index.ts         # Add PPTX types
│   │
│   └── package.json
│
└── README.md
```

### System Prompts

**Standard Mode (New Presentation):**
```
You are a presentation creation assistant. Help users create professional PowerPoint presentations.

WORKFLOW:
1. Understand the user's presentation goals (topic, audience, length)
2. Use create_presentation to start a new deck
3. Use add_slide to add slides with appropriate layouts
4. Use add_text, add_image, add_chart, add_table to populate content
5. Use save_presentation when the user is satisfied

DESIGN PRINCIPLES:
- Keep slides focused (one main idea per slide)
- Use consistent formatting throughout
- Limit text (bullet points, not paragraphs)
- Use visuals to support key points

You can call add_slide and content tools in parallel for efficiency.
```

**Continuation Mode (Editing):**
```
You are continuing to edit an existing presentation.

CRITICAL: Only modify what the user specifically requests.
DO NOT change slides or content unless explicitly asked.

Use list_slides to see current state before making changes.
Use get_slide_content for details about specific slides.
Stage changes with update tools, then save_presentation.
```

---

## Part 5: Implementation Plan

### Phase 1: Fork and Setup
1. Copy `form-filling-exp/` to `presentation_app/`
2. Update package names in `package.json` and `requirements.txt`
3. Add python-pptx, pdf2image, Pillow to requirements
4. Remove PDF-specific dependencies (PyMuPDF optional)
5. Test basic FastAPI + Next.js setup works

### Phase 2: Backend - PPTX Processor
1. Create `pptx_processor.py` with core operations:
   - `PresentationSession` class for state
   - Load/save presentations to bytes
   - Slide CRUD (add, delete, reorder)
   - Content manipulation (text, images, tables, charts)
   - Export to PDF (via LibreOffice or pdf2image)
   - Thumbnail generation (via Pillow)
2. Create dataclasses: `SlideInfo`, `ShapeInfo`, `PendingEdit`
3. Write unit tests for processor functions

### Phase 3: Backend - Agent Tools
1. Fork `agent.py`, replace PDF tools with presentation tools
2. Implement 15+ tool functions using pptx_processor
3. Update system prompts for presentation context
4. Add friendly tool descriptions for UI
5. Test each tool individually via API

### Phase 4: Backend - API Endpoints
1. Fork `main.py` endpoints:
   - `/analyze-presentation` (upload and analyze)
   - `/agent-stream` (main SSE endpoint)
   - `/session/{id}/download` (PPTX download)
   - `/session/{id}/pdf` (PDF export)
   - `/session/{id}/thumbnails` (slide previews)
2. Update session management for PPTX files
3. Add CORS and file upload handling
4. Test streaming works end-to-end

### Phase 5: Frontend - UI Components
1. Create `PptxViewer.tsx`:
   - Display current slide (image or embedded viewer)
   - Navigation controls (prev/next)
   - Zoom controls
2. Create `SlideGrid.tsx`:
   - Thumbnail grid of all slides
   - Click to select/navigate
   - Drag to reorder (optional)
3. Create `ExportMenu.tsx`:
   - Download PPTX button
   - Export PDF button
4. Update `page.tsx`:
   - Replace PDF viewer with PPTX components
   - Handle upload flow for PPTX files
   - Wire up session management
5. Style with Tailwind CSS

### Phase 6: Integration & Polish
1. End-to-end testing:
   - Create new presentation flow
   - Edit existing presentation flow
   - Multi-turn conversation
2. Error handling and edge cases
3. Loading states and progress indicators
4. Deployment configuration:
   - Update Render backend config
   - Update Vercel frontend config
5. Documentation and README

---

## Sources

### Form-Filling Repository Files
- `/Users/jerryliu/Programming/other/jerry-exp-2025-12-28/form-filling-exp/backend/agent.py` - Agent SDK patterns
- `/Users/jerryliu/Programming/other/jerry-exp-2025-12-28/form-filling-exp/backend/main.py` - FastAPI endpoints
- `/Users/jerryliu/Programming/other/jerry-exp-2025-12-28/form-filling-exp/backend/pdf_processor.py` - Processor patterns
- `/Users/jerryliu/Programming/other/jerry-exp-2025-12-28/form-filling-exp/web/src/app/page.tsx` - Frontend integration
- `/Users/jerryliu/Programming/other/jerry-exp-2025-12-28/form-filling-exp/web/src/lib/api.ts` - SSE streaming

### External Documentation
- [Anthropic Skills Repository](https://github.com/anthropics/skills) - Document skills including PPTX
- [Claude Agent SDK Skills Documentation](https://platform.claude.com/docs/en/agent-sdk/skills) - Skills integration
- [Claude Office Skills (PPTX)](https://github.com/tfriedel/claude-office-skills) - Office document workflows
- [PPTX Skill Definition](https://github.com/simonw/claude-skills/blob/initial/mnt/skills/public/pptx/SKILL.md) - Skill structure
- [python-pptx Documentation](https://python-pptx.readthedocs.io/) - Library reference
- [python-pptx GitHub](https://github.com/scanny/python-pptx) - Source and examples

### Competitive Research
- [Gamma.app](https://gamma.app) - AI presentation tool
- [Gamma App Review 2025](https://skywork.ai/skypage/en/Gamma-App-In-Depth-Review-2025-The-Ultimate-Guide-to-AI-Presentations/1973913493482172416)
- [Gamma vs Presentations.AI Comparison](https://slidespeak.co/comparison/gamma-vs-presentations-ai)
- [Claude Code PPTX Skill Guide](https://smartscope.blog/en/generative-ai/claude/claude-pptx-skill-practical-guide/)
