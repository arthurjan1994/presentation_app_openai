"""
OpenAI Agent integration for presentation manipulation.

Defines tools for creating and editing presentations,
and provides the main agent streaming function using OpenAI SDK.
"""

import uuid
import logging
import json
import asyncio
from typing import Any, AsyncGenerator, Optional, List, Dict
from contextvars import ContextVar

from models import Presentation, Slide, SlideLayout, PendingEdit
from session import PresentationSession, session_manager

logger = logging.getLogger(__name__)

# Context variable for current session (async-safe)
_current_session: ContextVar[Optional[PresentationSession]] = ContextVar(
    'current_session',
    default=None
)


def get_current_session() -> Optional[PresentationSession]:
    """Get the current session from context."""
    return _current_session.get()


def set_current_session(session: Optional[PresentationSession]):
    """Set the current session in context."""
    _current_session.set(session)


# Global registries for tools
OPENAI_TOOLS: List[Dict[str, Any]] = []
TOOL_FUNCTIONS: Dict[str, Any] = {}


def python_type_to_json_type(py_type: Any) -> str:
    """Convert Python type to JSON schema type."""
    if py_type is str:
        return "string"
    if py_type is int:
        return "integer"
    if py_type is float:
        return "number"
    if py_type is bool:
        return "boolean"
    if py_type is dict:
        return "object"
    if py_type is list:
        return "array"
    return "string"


def tool(name: str, description: str, params: Dict[str, Any]):
    """Decorator to register a function as an OpenAI tool."""
    def decorator(func):
        TOOL_FUNCTIONS[name] = func

        properties = {}
        required = []

        for param_name, param_type in params.items():
            properties[param_name] = {"type": python_type_to_json_type(param_type)}
            # We make all parameters required to ensure the model provides them
            # This simplifies things. The model is usually smart enough to provide defaults if we explained them in description,
            # but for structured output, explicit is better.
            required.append(param_name)

        tool_def = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
        OPENAI_TOOLS.append(tool_def)
        return func
    return decorator


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

@tool("create_presentation", "Create a new presentation. Title is required.", {"title": str})
async def tool_create_presentation(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new presentation with the given title."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}

    title = args.get("title", "Untitled Presentation")
    session.presentation = Presentation(title=title)
    session.pending_edits = []
    session.applied_edits = []

    return {"success": True, "title": title, "slide_count": 0}


@tool("add_slide", "Add a new slide with HTML content. Position and layout are optional (use -1 for position if unknown, 'blank' for layout).", {
    "html": str,
    "position": int,
    "layout": str
})
async def tool_add_slide(args: dict[str, Any]) -> dict[str, Any]:
    """Add a new slide to the presentation."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}
    if not session.presentation:
        return {"error": "No presentation created. Use create_presentation first."}

    html = args.get("html", "")
    position = args.get("position")
    layout_str = args.get("layout", "blank")

    # Handle -1 or None as "append"
    if position == -1:
        position = None

    try:
        layout = SlideLayout(layout_str)
    except ValueError:
        layout = SlideLayout.BLANK

    # Count pending ADD edits to calculate correct index
    pending_add_count = sum(1 for e in session.pending_edits if e.operation == "ADD")
    current_slide_count = len(session.presentation.slides)

    # Determine position
    if position is None or position >= (current_slide_count + pending_add_count):
        index = current_slide_count + pending_add_count
    else:
        index = max(0, position)

    # Create pending edit
    edit = PendingEdit(
        edit_id=str(uuid.uuid4()),
        slide_index=index,
        operation="ADD",
        params={"html": html, "layout": layout.value},
        preview=f"Add slide at position {index + 1}"
    )
    session.pending_edits.append(edit)

    return {"success": True, "slide_index": index, "edit_id": edit.edit_id}


@tool("update_slide", "Update an existing slide's HTML content", {
    "slide_index": int,
    "html": str
})
async def tool_update_slide(args: dict[str, Any]) -> dict[str, Any]:
    """Update the content of an existing slide."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}
    if not session.presentation:
        return {"error": "No presentation loaded"}

    slide_index = args.get("slide_index", 0)
    html = args.get("html", "")

    if slide_index < 0 or slide_index >= len(session.presentation.slides):
        return {"error": f"Invalid slide index: {slide_index}"}

    edit = PendingEdit(
        edit_id=str(uuid.uuid4()),
        slide_index=slide_index,
        operation="UPDATE",
        params={"html": html},
        preview=f"Update slide {slide_index + 1}"
    )
    session.pending_edits.append(edit)

    return {"success": True, "slide_index": slide_index, "edit_id": edit.edit_id}


@tool("delete_slide", "Delete a slide from the presentation", {"slide_index": int})
async def tool_delete_slide(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a slide from the presentation."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}
    if not session.presentation:
        return {"error": "No presentation loaded"}

    slide_index = args.get("slide_index", 0)

    if slide_index < 0 or slide_index >= len(session.presentation.slides):
        return {"error": f"Invalid slide index: {slide_index}"}

    edit = PendingEdit(
        edit_id=str(uuid.uuid4()),
        slide_index=slide_index,
        operation="DELETE",
        params={},
        preview=f"Delete slide {slide_index + 1}"
    )
    session.pending_edits.append(edit)

    return {"success": True, "slide_index": slide_index, "edit_id": edit.edit_id}


@tool("reorder_slides", "Move a slide to a new position", {
    "from_index": int,
    "to_index": int
})
async def tool_reorder_slides(args: dict[str, Any]) -> dict[str, Any]:
    """Reorder slides in the presentation."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}
    if not session.presentation:
        return {"error": "No presentation loaded"}

    from_index = args.get("from_index", 0)
    to_index = args.get("to_index", 0)
    num_slides = len(session.presentation.slides)

    if from_index < 0 or from_index >= num_slides:
        return {"error": f"Invalid from_index: {from_index}"}
    if to_index < 0 or to_index >= num_slides:
        return {"error": f"Invalid to_index: {to_index}"}

    edit = PendingEdit(
        edit_id=str(uuid.uuid4()),
        slide_index=from_index,
        operation="REORDER",
        params={"to_index": to_index},
        preview=f"Move slide {from_index + 1} to position {to_index + 1}"
    )
    session.pending_edits.append(edit)

    return {"success": True, "from_index": from_index, "to_index": to_index}


@tool("list_slides", "List all slides in the presentation. No parameters required.", {"dummy": str})
async def tool_list_slides(args: dict[str, Any]) -> dict[str, Any]:
    """List all slides with their index and content preview."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}
    if not session.presentation:
        return {"slides": [], "count": 0}

    import re
    slides = []
    for slide in session.presentation.slides:
        # Create a preview by stripping HTML and truncating
        preview = slide.html[:200].replace('<', ' <').replace('>', '> ')
        preview = re.sub(r'<[^>]+>', '', preview).strip()
        preview = ' '.join(preview.split())[:100]

        slides.append({
            "index": slide.index,
            "layout": slide.layout.value,
            "preview": preview,
            "has_notes": bool(slide.notes)
        })

    return {"slides": slides, "count": len(slides)}


@tool("get_slide", "Get full details of a specific slide", {"slide_index": int})
async def tool_get_slide(args: dict[str, Any]) -> dict[str, Any]:
    """Get the full HTML content and details of a slide."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}
    if not session.presentation:
        return {"error": "No presentation loaded"}

    slide_index = args.get("slide_index", 0)

    if slide_index < 0 or slide_index >= len(session.presentation.slides):
        return {"error": f"Invalid slide index: {slide_index}"}

    slide = session.presentation.slides[slide_index]
    return {
        "index": slide.index,
        "html": slide.html,
        "layout": slide.layout.value,
        "notes": slide.notes
    }


@tool("set_theme", "Set the presentation theme (colors, fonts)", {"theme": dict})
async def tool_set_theme(args: dict[str, Any]) -> dict[str, Any]:
    """Set the presentation theme."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}
    if not session.presentation:
        return {"error": "No presentation created"}

    theme = args.get("theme", {})
    session.presentation.theme = theme

    return {"success": True, "theme": theme}


@tool("get_pending_edits", "Get all pending edits that haven't been committed. No parameters required.", {"dummy": str})
async def tool_get_pending_edits(args: dict[str, Any]) -> dict[str, Any]:
    """Get all pending edits."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}

    edits = [
        {
            "edit_id": e.edit_id,
            "slide_index": e.slide_index,
            "operation": e.operation,
            "preview": e.preview
        }
        for e in session.pending_edits
    ]

    return {"edits": edits, "count": len(edits)}


@tool("commit_edits", "Apply all pending edits to the presentation. No parameters required.", {"dummy": str})
async def tool_commit_edits(args: dict[str, Any]) -> dict[str, Any]:
    """Apply all pending edits."""
    session = get_current_session()
    if not session:
        return {"error": "No active session"}
    if not session.presentation:
        return {"error": "No presentation created"}

    applied_count = 0

    for edit in session.pending_edits:
        try:
            if edit.operation == "ADD":
                # Add new slide
                slide = Slide(
                    index=edit.slide_index,
                    html=edit.params.get("html", ""),
                    layout=SlideLayout(edit.params.get("layout", "blank"))
                )
                # Insert at position
                if edit.slide_index >= len(session.presentation.slides):
                    session.presentation.slides.append(slide)
                else:
                    session.presentation.slides.insert(edit.slide_index, slide)
                # Re-index all slides
                for i, s in enumerate(session.presentation.slides):
                    s.index = i

            elif edit.operation == "UPDATE":
                if 0 <= edit.slide_index < len(session.presentation.slides):
                    session.presentation.slides[edit.slide_index].html = edit.params.get("html", "")

            elif edit.operation == "DELETE":
                if 0 <= edit.slide_index < len(session.presentation.slides):
                    del session.presentation.slides[edit.slide_index]
                    # Re-index
                    for i, s in enumerate(session.presentation.slides):
                        s.index = i

            elif edit.operation == "REORDER":
                to_index = edit.params.get("to_index", 0)
                if 0 <= edit.slide_index < len(session.presentation.slides):
                    slide = session.presentation.slides.pop(edit.slide_index)
                    session.presentation.slides.insert(to_index, slide)
                    # Re-index
                    for i, s in enumerate(session.presentation.slides):
                        s.index = i

            session.applied_edits.append(edit.to_dict())
            applied_count += 1

        except Exception as e:
            logger.error(f"Error applying edit {edit.edit_id}: {e}")

    # Clear pending edits
    session.pending_edits = []

    # Save session
    session_manager.save_session(session)

    return {
        "success": True,
        "applied_count": applied_count,
        "total_slides": len(session.presentation.slides)
    }


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

SYSTEM_PROMPT_NEW = """You are a presentation creation assistant. Create professional slides using HTML.

WORKFLOW:
1. Use create_presentation to start a new presentation with a title
2. Use add_slide to add slides with HTML content
3. Use commit_edits to finalize and save all changes

CRITICAL - SLIDE DIMENSIONS:
- Slides are EXACTLY 960px wide x 540px tall (16:9 aspect ratio)
- ALL content MUST fit within these bounds - no overflow allowed
- Your root div MUST have: width: 960px; height: 540px; overflow: hidden;
- Use box-sizing: border-box to include padding in dimensions

HTML TEMPLATE (USE THIS STRUCTURE):
<div style="width: 960px; height: 540px; padding: 40px; box-sizing: border-box; overflow: hidden; font-family: Arial, sans-serif;">
  <h1 style="color: #1a73e8; margin: 0 0 20px 0; font-size: 36px;">Slide Title</h1>
  <ul style="font-size: 22px; line-height: 1.5; margin: 0; padding-left: 24px;">
    <li>First key point</li>
    <li>Second key point</li>
    <li>Third key point</li>
  </ul>
</div>

DESIGN RULES:
- Root container: ALWAYS 960x540px with overflow:hidden
- Title: max 36px font, single line preferred
- Body text: 18-24px font size
- Padding: 40px on all sides (leaves 880x460px for content)
- Maximum 5-6 bullet points per slide
- If using cards/grids, calculate sizes to fit within bounds
- Test mentally: will this content fit in 880x460px usable area?

You can call add_slide multiple times in parallel for efficiency when creating multiple slides.
Always call commit_edits when done to save the presentation."""

SYSTEM_PROMPT_CONTINUATION = """You are editing an existing presentation.

CRITICAL: Only modify slides the user specifically requests.
DO NOT change slides that weren't mentioned unless explicitly asked.

CRITICAL - SLIDE DIMENSIONS:
- Slides are EXACTLY 960px wide x 540px tall (16:9 aspect ratio)
- ALL content MUST fit within these bounds - no overflow allowed
- Root div MUST have: width: 960px; height: 540px; overflow: hidden; box-sizing: border-box;

WORKFLOW:
1. Use list_slides to see all current slides
2. Use get_slide to see details of specific slides
3. Use update_slide or add_slide to make changes
4. Use commit_edits to save changes

Use list_slides first to understand the current state before making any changes."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _extract_slide_title_from_html(html: str) -> str:
    """Extract the title/heading from slide HTML content."""
    import re
    if not html:
        return None

    heading_match = re.search(r'<h[12][^>]*>([^<]+)</h[12]>', html, re.IGNORECASE)
    if heading_match:
        title = heading_match.group(1).strip()
        title = ' '.join(title.split())
        if len(title) > 60:
            title = title[:57] + "..."
        return title

    text = re.sub(r'<[^>]+>', ' ', html)
    text = ' '.join(text.split()).strip()
    if text:
        first_part = text[:60]
        if len(text) > 60:
            first_part = first_part.rsplit(' ', 1)[0] + "..."
        return first_part

    return None


def _extract_slide_content_from_html(html: str) -> str:
    """Extract full readable text content from slide HTML for display."""
    import re
    if not html:
        return None

    list_items = re.findall(r'<li[^>]*>(.*?)</li>', html, re.IGNORECASE | re.DOTALL)
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
    content_parts = []

    for item in list_items:
        item = re.sub(r'<[^>]+>', ' ', item)
        item = ' '.join(item.split()).strip()
        if item:
            content_parts.append(f"• {item}")

    if not content_parts:
        for para in paragraphs:
            para = re.sub(r'<[^>]+>', ' ', para)
            para = ' '.join(para.split()).strip()
            if para:
                content_parts.append(para)

    if not content_parts:
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<h[12][^>]*>.*?</h[12]>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'</(?:div|p|li|br)[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        lines = [' '.join(line.split()).strip() for line in text.split('\n')]
        lines = [line for line in lines if line]
        if lines:
            content_parts = lines

    if content_parts:
        result = '\n'.join(content_parts)
        if len(result) > 500:
            result = result[:497] + "..."
        return result

    return None


def _get_friendly_tool_description(tool_name: str, tool_input: dict) -> tuple[str, str]:
    """Convert a tool call into a user-friendly description and details."""
    if not isinstance(tool_input, dict):
        return None, None

    if "create_presentation" in tool_name:
        title = tool_input.get("title", "Untitled")
        return f"Creating presentation: {title}", None
    elif "add_slide" in tool_name:
        html = tool_input.get("html", "")
        slide_title = _extract_slide_title_from_html(html)
        slide_content = _extract_slide_content_from_html(html)
        friendly = f"Adding slide: {slide_title}" if slide_title else "Adding a new slide..."
        return friendly, slide_content
    elif "update_slide" in tool_name:
        idx = tool_input.get("slide_index", 0)
        html = tool_input.get("html", "")
        slide_title = _extract_slide_title_from_html(html)
        slide_content = _extract_slide_content_from_html(html)
        friendly = f"Updating slide {idx + 1}: {slide_title}" if slide_title else f"Updating slide {idx + 1}..."
        return friendly, slide_content
    elif "delete_slide" in tool_name:
        idx = tool_input.get("slide_index", 0)
        return f"Deleting slide {idx + 1}", None
    elif "list_slides" in tool_name:
        return "Listing all slides...", None
    elif "get_slide" in tool_name:
        idx = tool_input.get("slide_index", 0)
        return f"Getting slide {idx + 1} details...", None
    elif "commit_edits" in tool_name:
        return "Saving changes...", None
    elif "set_theme" in tool_name:
        return "Setting presentation theme...", None

    return None, None


# =============================================================================
# AGENT STREAMING
# =============================================================================

async def run_agent_stream(
    instructions: str,
    is_continuation: bool = False,
    resume_session_id: Optional[str] = None,
    user_session_id: Optional[str] = None,
    context_files: Optional[list[dict]] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = "gpt-3.5-turbo",
) -> AsyncGenerator[dict, None]:
    """
    Run the agent and stream results using OpenAI SDK.

    Args:
        instructions: User instructions
        is_continuation: Whether this is continuing a previous session
        resume_session_id: Session ID (for multi-turn)
        user_session_id: Backend session ID
        context_files: Parsed context files
        api_key: OpenAI API key
        base_url: OpenAI Base URL
        model: Model ID
    """
    if not api_key:
        yield {"type": "error", "error": "API key is required"}
        return

    # Import OpenAI here to handle dependencies
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield {"type": "error", "error": "openai package not installed"}
        return

    # Get or create session
    session = session_manager.get_or_create_session(user_session_id)

    if context_files:
        session.context_files = context_files

    set_current_session(session)

    yield {"type": "init", "message": "Starting agent...", "session_id": session.session_id}
    yield {"type": "status", "message": "Connecting to OpenAI..."}

    try:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = AsyncOpenAI(**client_kwargs)

        # Build System Prompt
        system_prompt = SYSTEM_PROMPT_CONTINUATION if is_continuation else SYSTEM_PROMPT_NEW

        if session.context_files:
            context_text = "\n\n".join([
                f"=== {f['filename']} ===\n{f['text']}"
                for f in session.context_files if f.get('text')
            ])
            if context_text:
                system_prompt += f"\n\nCONTEXT FILES:\n{context_text}"

        if session.style_template and session.style_template.get("text"):
            system_prompt += f"\n\nSTYLE TEMPLATE REFERENCE:"
            system_prompt += f"\nFilename: {session.style_template['filename']}"
            system_prompt += f"\nTemplate content:\n{session.style_template['text']}"

            if session.style_template.get("screenshots"):
                system_prompt += f"\n\nStyle reference screenshots will be provided in the user message."

        # Initialize messages
        messages = [{"role": "system", "content": system_prompt}]

        # Build User Message (Multimodal)
        user_content = []

        # Add template screenshots if available
        if session.style_template and session.style_template.get("screenshots"):
            screenshots = session.style_template["screenshots"]
            user_content.append({
                "type": "text",
                "text": f"STYLE TEMPLATE REFERENCE SCREENSHOTS:\nThe following {len(screenshots)} screenshots show the visual style you should emulate:"
            })

            for i, screenshot in enumerate(screenshots):
                user_content.append({
                    "type": "text",
                    "text": f"\nSlide {screenshot.get('index', i) + 1}:"
                })
                # OpenAI uses "image_url" with base64
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{screenshot['data']}"
                    }
                })

        user_content.append({"type": "text", "text": instructions})

        messages.append({"role": "user", "content": user_content})

        # Main Loop
        message_count = 0
        final_result_text = ""

        while True:
            print(f"[Agent Stream] Sending request to {model}...")
            yield {"type": "status", "message": "Thinking..."}

            response_stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
                stream=True
            )

            current_tool_calls = {} # index -> {id, name, args_parts}
            current_content = ""

            async for chunk in response_stream:
                delta = chunk.choices[0].delta

                # Handle text content
                if delta.content:
                    current_content += delta.content
                    final_result_text += delta.content
                    yield {
                        "type": "assistant",
                        "text": delta.content
                    }

                # Handle tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": ""
                            }

                        if tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if tc.function.name:
                            current_tool_calls[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            current_tool_calls[idx]["arguments"] += tc.function.arguments

            # End of stream for this turn
            message_count += 1

            # Append assistant message to history
            assistant_msg = {
                "role": "assistant",
                "content": current_content
            }

            if current_tool_calls:
                assistant_msg["tool_calls"] = []
                for idx in sorted(current_tool_calls.keys()):
                    tc_data = current_tool_calls[idx]
                    assistant_msg["tool_calls"].append({
                        "id": tc_data["id"],
                        "type": "function",
                        "function": {
                            "name": tc_data["name"],
                            "arguments": tc_data["arguments"]
                        }
                    })

            messages.append(assistant_msg)

            # If no tool calls, we are done
            if not current_tool_calls:
                break

            # Execute tools
            yield {"type": "status", "message": "Executing tools..."}

            tool_outputs_for_log = []

            for idx in sorted(current_tool_calls.keys()):
                tc_data = current_tool_calls[idx]
                tool_name = tc_data["name"]
                tool_id = tc_data["id"]
                tool_args_str = tc_data["arguments"]

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}
                    print(f"Failed to parse tool arguments: {tool_args_str}")

                # Notify frontend of tool use
                friendly, details = _get_friendly_tool_description(tool_name, tool_args)

                yield {
                    "type": "tool_use",
                    "tool_calls": [{
                        "name": tool_name,
                        "input": tool_args,
                        "friendly": friendly,
                        "details": details
                    }]
                }
                if friendly:
                    yield {"type": "tool_use", "friendly": [friendly]}
                if details:
                    yield {"type": "tool_use", "details": [details]}

                # Execute tool
                func = TOOL_FUNCTIONS.get(tool_name)
                if func:
                    try:
                        result = await func(tool_args)
                    except Exception as e:
                        result = {"error": str(e)}
                else:
                    result = {"error": f"Tool {tool_name} not found"}

                tool_outputs_for_log.append(result)

                # Append tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": json.dumps(result)
                })

            # Continue loop to let model react to tool outputs

    except Exception as e:
        print(f"[Agent Stream] Error: {e}")
        import traceback
        traceback.print_exc()
        yield {"type": "error", "error": f"Agent error: {str(e)}"}
        return

    finally:
        set_current_session(None)

    # Save session state
    # session.claude_session_id = ... # No persistent session ID needed for OpenAI REST API, we manage history in 'messages'
    session_manager.save_session(session)

    # Yield final summary
    yield {
        "type": "complete",
        "success": True,
        "result": final_result_text,
        "message_count": message_count,
        "session_id": session.session_id, # Return our session ID
        "user_session_id": session.session_id,
        "slide_count": len(session.presentation.slides) if session.presentation else 0
    }
