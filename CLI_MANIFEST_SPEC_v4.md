# CLI Manifest Specification (v2)

> For LLM-based coding agents building Agent Aech CLI capabilities
>
> **Version:** 4 | **Last Updated:** 2026-01-09 12:45 PT

## Purpose

This manifest enables another LLM agent to use your CLI correctly. Write it as if explaining your CLI to a capable assistant who has never seen it before. Every field should answer: **What can I do with this? How do I do it? When should I use it?**

## Manifest Schema

```json
{
  "name": "cli-name",
  "type": "cli",
  "command": "aech-cli-name",
  "description": "What this CLI does, what inputs it accepts, what outputs it produces.",
  "actions": [
    {
      "name": "action-name",
      "description": "What this action does. Input: what it takes. Output: what it produces. Use when: the scenario.",
      "parameters": [
        {
          "name": "param-name",
          "type": "argument|option",
          "required": true|false,
          "description": "What this is, format/valid values, when to use it."
        }
      ]
    }
  ],
  "available_in_sandbox": true|false,
  "documentation": {
    "outputs": { ... },
    "notes": [ ... ]
  }
}
```

## Writing Effective Descriptions

Descriptions are the most important part of the manifest. They must enable action.

### Action Descriptions

An action description answers three questions:

1. **What does it do?** - The core function
2. **What are the inputs/outputs?** - File types, formats, locations
3. **When should I use it?** - The scenario that calls for this action

**Example - Document Translation:**
```json
{
  "name": "translate",
  "description": "Translate a Markdown document to another language. Input: Markdown file path. Output: translated file at <output-dir>/<stem>_<lang>.md and QA report at <output-dir>/<stem>_translation_report.md. Use when user needs a document in another language."
}
```

**Example - Email Update:**
```json
{
  "name": "update-message",
  "description": "Update email message properties: categories, flags, importance, read status. Input: message ID from list-messages. Output: JSON confirmation. Use when user wants to organize, flag, or mark emails."
}
```

**Example - Document Conversion:**
```json
{
  "name": "convert",
  "description": "Render document pages to PNG images. Input: PDF, DOCX, PPTX, or image file. Output: page_001.png, page_002.png, etc. in output directory. Use when user needs to view or process document pages as images."
}
```

### Parameter Descriptions

A parameter description must include:

1. **What it is** - The purpose of this parameter
2. **Format/Valid values** - Exact formats, allowed values, examples
3. **When to use it** (for optional params) - The scenario

**Example - Language Code:**
```json
{
  "name": "target-lang",
  "type": "argument",
  "required": true,
  "description": "Target language as ISO 639-1 code. Examples: fr (French), de (German), es (Spanish), ja (Japanese), zh (Chinese)."
}
```

**Example - Output Directory:**
```json
{
  "name": "output-dir",
  "type": "option",
  "required": true,
  "description": "Directory path where output files will be written. Must exist or will be created."
}
```

**Example - Flag Status:**
```json
{
  "name": "flag",
  "type": "option",
  "required": false,
  "description": "Set email flag status. Values: flagged (mark for follow-up), complete (mark as done), notFlagged (remove flag). Use to help user track action items."
}
```

**Example - Due Date:**
```json
{
  "name": "flag-due",
  "type": "option",
  "required": false,
  "description": "Due date for flagged email. Formats: ISO-8601 date (2024-12-31) or relative (today, tomorrow, this-week, next-week). Use with --flag flagged."
}
```

**Example - Repeatable Option:**
```json
{
  "name": "format",
  "type": "option",
  "required": false,
  "description": "Output format. Values: docx, pdf, pptx. Can be specified multiple times for multiple outputs. Defaults to docx and pdf if not specified."
}
```

## Key Requirements

### 1. Complete Parameter Coverage

Every parameter your CLI accepts must be in the manifest. The agent only knows what's in `actions[].parameters`.

Check your Typer function signature:
```python
@app.command("convert-markdown")
def convert_markdown(
    input_path: str,
    output_dir: str = typer.Option(..., "--output-dir"),
    format: list[str] = typer.Option(None, "--format"),
    reference_doc: str = typer.Option(None, "--reference-doc"),
):
```

All four parameters must appear in the manifest.

### 2. Exact Parameter Names

The manifest name must match the CLI flag exactly:
- `--output-dir` → `"name": "output-dir"`
- `--reference-doc` → `"name": "reference-doc"`

### 3. Descriptions Are Mandatory

Every action and every parameter needs a description. No exceptions. A manifest without descriptions is unusable.

### 4. Behavior Over Implementation

Describe what the CLI does for the user, not how it works internally. Don't mention libraries, engines, or technical internals.

### 5. JSON Output Only

All CLI commands output JSON. No format flags. The agent parses JSON directly.

### 6. No Hidden Commands

Commands marked `hidden=True` in Typer are for internal use and must not appear in the manifest.

## Complete Example

```json
{
  "name": "documents",
  "type": "cli",
  "command": "aech-cli-documents",
  "description": "Convert documents between formats. Accepts PDFs, Office files, and images. Produces PNG page images, Markdown text, or Office/PDF outputs.",
  "actions": [
    {
      "name": "convert",
      "description": "Render document pages to PNG images. Input: PDF, DOCX, PPTX, or image file. Output: page_001.png, page_002.png, etc. Returns JSON with list of image paths. Use when user needs to view or analyze document pages.",
      "parameters": [
        {
          "name": "input_path",
          "type": "argument",
          "required": true,
          "description": "Path to the document file to convert. Accepts PDF, DOCX, PPTX, XLS, or image files."
        },
        {
          "name": "output-dir",
          "type": "option",
          "required": true,
          "description": "Directory where PNG images will be written. Will be created if it doesn't exist."
        }
      ]
    },
    {
      "name": "convert-to-markdown",
      "description": "Extract document text as Markdown. Input: PDF or Office file. Output: <stem>.md file with extracted text. Returns JSON with output path. Use when user needs document content as editable text.",
      "parameters": [
        {
          "name": "input_path",
          "type": "argument",
          "required": true,
          "description": "Path to the document file. Accepts PDF, DOCX, PPTX, XLS, DOC, PPT, XLS."
        },
        {
          "name": "output-dir",
          "type": "option",
          "required": true,
          "description": "Directory where the Markdown file will be written."
        }
      ]
    },
    {
      "name": "convert-markdown",
      "description": "Render Markdown to Office or PDF formats. Input: Markdown file. Output: DOCX and PDF by default, or specified formats. Returns JSON with output paths. Use when user needs a polished document from Markdown source.",
      "parameters": [
        {
          "name": "input_path",
          "type": "argument",
          "required": true,
          "description": "Path to the Markdown (.md) file to convert."
        },
        {
          "name": "output-dir",
          "type": "option",
          "required": true,
          "description": "Directory where output files will be written."
        },
        {
          "name": "format",
          "type": "option",
          "required": false,
          "description": "Output format. Values: docx, pdf, pptx. Can be repeated (--format docx --format pdf). Defaults to docx and pdf."
        },
        {
          "name": "reference-doc",
          "type": "option",
          "required": false,
          "description": "Template file for styling. Use a .docx template for Word output or .pptx for PowerPoint. Applies fonts, colors, and layout from the template."
        }
      ]
    }
  ],
  "documentation": {
    "outputs": {
      "page_images": {
        "path": "<output-dir>/page_###.png",
        "description": "Numbered PNG pages from convert command"
      },
      "markdown_file": {
        "path": "<output-dir>/<stem>.md",
        "description": "Markdown file from convert-to-markdown command"
      }
    },
    "notes": [
      "All commands return JSON to stdout with output file paths",
      "Check exit code for success (0) or failure (non-zero)"
    ]
  },
  "available_in_sandbox": true
}
```

## Self-Test

Before finalizing your manifest, ask:

> **Could an agent with no other context correctly use this CLI?**

Read each action and parameter. If the description doesn't tell you exactly what to pass and when, improve it.

## Validation Checklist

- [ ] Every non-hidden Typer command has a matching action
- [ ] Every function parameter is in the manifest
- [ ] Parameter names match CLI flags exactly (hyphens, not underscores)
- [ ] Every action has a description with what/input/output/when
- [ ] Every parameter has a description with format and valid values
- [ ] No library names or implementation details in descriptions
- [ ] Test: `aech-cli-name action --help` matches manifest

## How the Agent Uses This

At runtime, the agent receives:

```
DOCUMENTS: Convert documents between formats.
  Command: `aech-cli-documents`
  Actions:
  - convert: Render document pages to PNG images. Input: PDF, DOCX...
    Usage: aech-cli-documents convert <input_path> --output-dir <value>
```

This formatted view is everything the agent knows. Clear descriptions mean correct usage. Vague descriptions mean guessing and errors.
