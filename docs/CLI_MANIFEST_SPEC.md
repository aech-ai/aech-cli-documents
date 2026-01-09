# CLI Manifest Specification

> For LLM-based coding agents building Agent Aech CLI capabilities
>
> **Last Updated:** 2026-01-09

## Audience

This document is for **LLM coding agents** (Claude, GPT, etc.) that are creating or updating CLI capabilities for Agent Aech. The manifest you create will be parsed by another LLM agent at runtime - accuracy is critical.

## Why This Matters

The manifest is the **single source of truth** for what your CLI can do. At runtime:

1. `format_capabilities_manifest()` parses your `actions[]` array
2. It builds a system prompt showing available commands and parameters
3. The agent uses ONLY what's in that prompt - nothing else

**If a parameter isn't in `actions[].parameters`, the agent won't know it exists.**

## Anti-Hallucination Rules

These rules prevent the runtime agent from inventing parameters or misusing your CLI:

### 1. Complete Parameter Lists

Every parameter your CLI accepts MUST be in the manifest. Check your Typer decorators:

```python
@app.command("my-action")
def my_action(
    input_path: str,  # <- This is an argument
    output_dir: str = typer.Option(..., "--output-dir"),  # <- Required option
    format: str = typer.Option(None, "--format"),  # <- Optional option
):
```

Manifest MUST include ALL THREE:

```json
{
  "name": "my-action",
  "parameters": [
    {"name": "input_path", "type": "argument", "required": true},
    {"name": "output_dir", "type": "option", "required": true},
    {"name": "format", "type": "option", "required": false}
  ]
}
```

### 2. No Implementation Details in Descriptions

**BAD** - Mentions libraries, creates hallucination risk:
```json
{
  "description": "Convert PDF using pdf2image and Pillow, then run through Pandoc with xelatex engine"
}
```

**GOOD** - Describes what it does, not how:
```json
{
  "description": "Convert PDF to PNG images, one per page"
}
```

Why: The agent might try `--pdf-engine xelatex` because you mentioned xelatex, even if that's not a CLI parameter.

### 3. No Duplicate Information

The `documentation` section is for supplementary info only. Never duplicate parameter info there:

**BAD** - Creates confusion about which params exist:
```json
{
  "actions": [...],
  "documentation": {
    "inputs": {
      "output_dir": "Where files go",
      "pdf_engine": "PDF engine to use"  // <- Not in actions!
    }
  }
}
```

**GOOD** - Documentation adds context, not parameter lists:
```json
{
  "actions": [...],
  "documentation": {
    "outputs": {
      "images": {"path": "output_dir/page_###.png"}
    },
    "notes": ["Returns JSON to stdout"]
  }
}
```

### 4. Parameter Names Must Match CLI Exactly

If your Typer option is `--output-dir`, the manifest name is `output-dir` (not `output_dir`):

```python
output_dir: str = typer.Option(..., "--output-dir", "-o")
```

```json
{"name": "output-dir", "type": "option", "required": true}
```

### 5. Hidden Commands

Commands marked `hidden=True` in Typer should NOT appear in the manifest. They're for internal/privileged use only.

## Manifest Schema

### Required Fields

```json
{
  "name": "string",        // Short name: "documents", "msgraph"
  "type": "cli",           // Always "cli" for CLI capabilities
  "command": "string",     // Full command: "aech-cli-documents"
  "actions": [...]         // Array of available commands
}
```

### Action Schema

```json
{
  "name": "action-name",           // Command name as invoked
  "description": "string",         // What it does (1-2 sentences, no library names)
  "parameters": [
    {
      "name": "param-name",        // Exact CLI name (--output-dir -> "output-dir")
      "type": "argument|option",   // Positional or flag
      "required": true|false,      // Is it mandatory?
      "description": "string"      // Optional: what this param does
    }
  ]
}
```

### Optional Fields

```json
{
  "available_in_sandbox": true,    // Can run in sandboxed worker
  "daemon": {                      // For stateful CLIs with daemons
    "container": "daemon-name",
    "port": 8000
  },
  "documentation": {
    "outputs": {...},              // What files/data the CLI produces
    "notes": [...]                 // Additional guidance for agents
  }
}
```

## Complete Example

Here's a well-formed manifest:

```json
{
  "name": "documents",
  "type": "cli",
  "command": "aech-cli-documents",
  "description": "Convert documents between formats. Accepts PDFs, Office files, and images.",
  "actions": [
    {
      "name": "convert",
      "description": "Render document pages to PNG images. Returns JSON with image paths.",
      "parameters": [
        {
          "name": "input_path",
          "type": "argument",
          "required": true
        },
        {
          "name": "output-dir",
          "type": "option",
          "required": true,
          "description": "Directory for output images"
        }
      ]
    },
    {
      "name": "convert-markdown",
      "description": "Render Markdown to Office/PDF. Defaults to DOCX and PDF.",
      "parameters": [
        {
          "name": "input_path",
          "type": "argument",
          "required": true
        },
        {
          "name": "output-dir",
          "type": "option",
          "required": true
        },
        {
          "name": "format",
          "type": "option",
          "required": false,
          "description": "Output format (docx, pdf, pptx). Repeatable."
        },
        {
          "name": "reference-doc",
          "type": "option",
          "required": false,
          "description": "Template for Office styling"
        }
      ]
    }
  ],
  "documentation": {
    "outputs": {
      "images": {
        "path": "output-dir/page_###.png",
        "description": "Numbered PNG files from convert command"
      }
    },
    "notes": [
      "All commands return JSON to stdout",
      "Use exit code to check success/failure"
    ]
  },
  "available_in_sandbox": true
}
```

## Generating Manifests

Use the manifest generator for accuracy:

```bash
cd your-cli-project
python generate_manifest.py aech_cli_yourname
```

This introspects your Typer app and extracts parameters automatically. **Always review the output** - the generator may miss edge cases.

## Validation Checklist

Before committing your manifest:

- [ ] Every Typer `@app.command()` (non-hidden) has a matching action
- [ ] Every parameter in the function signature is in `parameters[]`
- [ ] Parameter names match the CLI flags exactly
- [ ] Descriptions don't mention library names (Pandoc, pdf2image, etc.)
- [ ] No `documentation.inputs` section duplicating parameter info
- [ ] `required` field matches whether the param has a default value
- [ ] Tested: `aech-cli-yourname --help` output matches manifest

## How the Agent Sees Your Manifest

The runtime agent receives a formatted version like this:

```
DOCUMENTS: Convert documents between formats.
  Command: `aech-cli-documents`
  Actions:
  - convert: Render document pages to PNG images.
    Usage: aech-cli-documents convert <input_path> --output-dir <output-dir>
  - convert-markdown: Render Markdown to Office/PDF.
    Usage: aech-cli-documents convert-markdown <input_path> --output-dir <output-dir> [format] [reference-doc]
```

This is ALL the agent knows. If something isn't here, the agent will either:
1. Not use it (best case)
2. Hallucinate it exists (worst case - causes errors)

## Common Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Missing optional params | Agent can't use advanced features | Add all params to manifest |
| Library names in descriptions | Agent tries library-specific options | Describe behavior, not implementation |
| `documentation.inputs` duplicating `actions` | Conflicting info causes confusion | Remove `documentation.inputs` |
| Wrong param names | Commands fail at runtime | Match exact CLI flag names |
| Including hidden commands | Exposes internal/unsafe operations | Only include non-hidden commands |

## Testing Your Manifest

```bash
# 1. Verify JSON is valid
cat manifest.json | jq .

# 2. Compare to actual CLI help
aech-cli-yourname --help
aech-cli-yourname action-name --help

# 3. Test each action works as documented
aech-cli-yourname action-name arg --option value
```

## Questions?

If you're an LLM agent reading this and something is unclear, ask the user to clarify before proceeding. An incorrect manifest causes runtime failures that are hard to debug.
