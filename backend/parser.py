"""
LlamaParse integration for parsing context files.

Supports parsing various document formats (PDF, DOCX, etc.)
to extract text content for presentation context.
"""

import os
import logging
from typing import AsyncGenerator

# Apply nest_asyncio to allow nested event loops (needed for LlamaParse)
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass  # nest_asyncio not installed, some features may not work

logger = logging.getLogger(__name__)

# Check if LlamaParse is available
try:
    from llama_cloud_services import LlamaParse
    LLAMAPARSE_AVAILABLE = True
except ImportError:
    LLAMAPARSE_AVAILABLE = False
    logger.warning("llama-cloud-services not installed. File parsing will be limited.")


async def parse_files_stream(
    files: list[dict],
    parse_mode: str = "cost_effective"
) -> AsyncGenerator[dict, None]:
    """
    Parse uploaded files and stream progress.

    Args:
        files: List of dicts with 'filename', 'content' (bytes), 'content_type'
        parse_mode: Parsing mode ('cost_effective' or 'premium')

    Yields:
        Progress and result events
    """
    if not files:
        yield {"type": "complete", "results": []}
        return

    results = []
    total = len(files)

    for idx, file_data in enumerate(files):
        filename = file_data["filename"]
        content = file_data["content"]
        content_type = file_data.get("content_type", "")

        yield {
            "type": "progress",
            "current": idx + 1,
            "total": total,
            "filename": filename,
            "status": "parsing"
        }

        try:
            # Try LlamaParse first if available
            if LLAMAPARSE_AVAILABLE and os.environ.get("LLAMA_CLOUD_API_KEY"):
                parsed_text = await parse_with_llama(content, filename, parse_mode)
            else:
                # Fallback to basic parsing
                parsed_text = parse_basic(content, filename, content_type)

            results.append({
                "filename": filename,
                "text": parsed_text,
                "success": True
            })

            yield {
                "type": "progress",
                "current": idx + 1,
                "total": total,
                "filename": filename,
                "status": "complete"
            }

        except Exception as e:
            logger.error(f"Error parsing {filename}: {e}")
            results.append({
                "filename": filename,
                "text": "",
                "success": False,
                "error": str(e)
            })

            yield {
                "type": "progress",
                "current": idx + 1,
                "total": total,
                "filename": filename,
                "status": "error",
                "error": str(e)
            }

    yield {"type": "complete", "results": results}


async def parse_with_llama(
    content: bytes,
    filename: str,
    parse_mode: str
) -> str:
    """Parse file using LlamaParse."""
    from llama_cloud_services import LlamaParse

    parser = LlamaParse(
        result_type="markdown",
        parsing_instruction="Extract all text content for use in presentation slides."
    )

    # Write to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as f:
        f.write(content)
        temp_path = f.name

    try:
        documents = await parser.aload_data(temp_path)
        return "\n\n".join(doc.text for doc in documents)
    finally:
        import os
        os.unlink(temp_path)


def parse_basic(content: bytes, filename: str, content_type: str) -> str:
    """Basic parsing fallback for common formats."""
    ext = filename.lower().split('.')[-1] if '.' in filename else ''

    # Plain text files
    if ext in ['txt', 'md', 'markdown'] or 'text/' in content_type:
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError:
            return content.decode('latin-1')

    # For other formats, return a placeholder
    return f"[Content from {filename} - requires LlamaParse for full extraction]"


async def parse_template_with_screenshots(
    content: bytes,
    filename: str,
    tier: str = "cost_effective",
) -> dict:
    """
    Parse presentation template with screenshot extraction.

    Args:
        content: File content as bytes
        filename: Original filename
        tier: Parsing tier ('cost_effective' or 'agentic_plus')

    Returns:
        {
            "filename": str,
            "text": str,
            "screenshots": [{"index": int, "data": str (base64)}],
            "success": bool,
            "error": str | None
        }
    """
    import tempfile
    import base64
    import re

    if not LLAMAPARSE_AVAILABLE or not os.environ.get("LLAMA_CLOUD_API_KEY"):
        return {
            "filename": filename,
            "text": "",
            "screenshots": [],
            "success": False,
            "error": "LlamaParse not available for template parsing. Set LLAMA_CLOUD_API_KEY."
        }

    try:
        from llama_cloud_services import LlamaParse

        # Configure LlamaParse with new tier-based API
        parser = LlamaParse(
            tier=tier,
            version="latest",
            output_tables_as_HTML=True,
            precise_bounding_box=True,
            page_separator="\n\n---\n\n",
            take_screenshot=True,
        )

        # Write to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as f:
            f.write(content)
            temp_path = f.name

        try:
            # Parse document - use aparse to get JobResult object
            result = await parser.aparse(temp_path)

            # Get text content from markdown documents
            markdown_docs = result.get_markdown_documents(split_by_page=False)
            text_content = "\n\n".join(doc.text for doc in markdown_docs) if markdown_docs else ""

            # Extract screenshots using async method to fetch image data
            screenshots = []

            # Create a debug directory to save screenshots
            debug_dir = "/tmp/template_screenshots"
            os.makedirs(debug_dir, exist_ok=True)
            logger.info(f"Saving debug screenshots to: {debug_dir}")

            # Pattern to match full page screenshots: page_N.jpg (1-indexed)
            page_screenshot_pattern = re.compile(r'^page_(\d+)\.jpg$')

            try:
                if result.pages:
                    logger.info(f"Found {len(result.pages)} pages in result")

                    # Collect only full page screenshots from all pages
                    page_screenshots = []
                    for page_idx, page in enumerate(result.pages):
                        if hasattr(page, 'images') and page.images:
                            logger.info(f"Page {page_idx}: found {len(page.images)} images")
                            for img in page.images:
                                # Handle SDK objects - access .name attribute
                                img_name = getattr(img, 'name', None)
                                if img_name is None and hasattr(img, '__getitem__'):
                                    # Fallback to dict access if needed
                                    img_name = img.get('name') if isinstance(img, dict) else None

                                if img_name:
                                    match = page_screenshot_pattern.match(img_name)
                                    if match:
                                        # page_N.jpg is 1-indexed, convert to 0-indexed
                                        page_num = int(match.group(1)) - 1
                                        page_screenshots.append({
                                            "page_idx": page_num,
                                            "name": img_name
                                        })
                                        logger.info(f"Found full page screenshot: {img_name} for page {page_num}")
                        else:
                            logger.info(f"Page {page_idx}: no images found")

                    logger.info(f"Total full page screenshots found: {len(page_screenshots)}")

                    # Sort by page index and select representative screenshots (up to 5)
                    page_screenshots.sort(key=lambda x: x["page_idx"])

                    if page_screenshots:
                        max_screenshots = 5
                        step = max(1, len(page_screenshots) // max_screenshots)
                        selected = page_screenshots[::step][:max_screenshots]
                        logger.info(f"Selecting {len(selected)} page screenshots")

                        for img_info in selected:
                            img_name = img_info["name"]
                            try:
                                # Use async method to get image data
                                logger.info(f"Fetching image: {img_name}")
                                img_data = await result.aget_image_data(img_name)
                                if img_data:
                                    # Save to debug directory
                                    debug_path = os.path.join(debug_dir, img_name)
                                    with open(debug_path, 'wb') as f:
                                        f.write(img_data)
                                    logger.info(f"Saved debug image to: {debug_path}")

                                    # img_data should be bytes, encode to base64
                                    img_base64 = base64.b64encode(img_data).decode('utf-8')
                                    screenshots.append({
                                        "index": img_info["page_idx"],
                                        "data": img_base64,
                                    })
                                    logger.info(f"Successfully fetched image {img_name} ({len(img_data)} bytes)")
                                else:
                                    logger.warning(f"No data returned for image {img_name}")
                            except Exception as img_err:
                                logger.warning(f"Could not fetch image {img_name}: {img_err}")
                else:
                    logger.info("No pages in result")

                logger.info(f"Final screenshot count: {len(screenshots)}")

            except Exception as e:
                logger.warning(f"Could not extract screenshots: {e}")
                # Continue without screenshots - text is still valuable

            return {
                "filename": filename,
                "text": text_content,
                "screenshots": screenshots,
                "success": True,
                "error": None
            }

        finally:
            os.unlink(temp_path)

    except Exception as e:
        logger.error(f"Error parsing template {filename}: {e}")
        return {
            "filename": filename,
            "text": "",
            "screenshots": [],
            "success": False,
            "error": str(e)
        }
