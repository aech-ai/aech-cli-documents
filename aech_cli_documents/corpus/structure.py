"""Markdown structure extraction - parse headers into hierarchical tree."""

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TreeNode:
    """A node in the document structure tree."""

    id: str
    level: int  # 1-6 for H1-H6
    title: str
    content: str = ""  # Content between this header and next header/child
    start_line: int = 0
    end_line: int = 0
    parent: Optional["TreeNode"] = None
    children: list["TreeNode"] = field(default_factory=list)

    @property
    def path(self) -> str:
        """Generate hierarchical path like '3.2.1'."""
        if self.parent is None:
            # Root node or top-level
            if self.parent is None and self.level == 0:
                return ""
            index = 1
            return str(index)

        # Find position among siblings
        siblings = self.parent.children
        index = siblings.index(self) + 1

        parent_path = self.parent.path
        if parent_path:
            return f"{parent_path}.{index}"
        return str(index)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "level": self.level,
            "title": self.title,
            "path": self.path,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class DocumentTree:
    """Hierarchical document structure."""

    root: TreeNode
    all_nodes: list[TreeNode] = field(default_factory=list)

    def get_node_by_path(self, path: str) -> Optional[TreeNode]:
        """Get a node by its path (e.g., '3.2.1')."""
        for node in self.all_nodes:
            if node.path == path:
                return node
        return None

    def get_node_by_id(self, node_id: str) -> Optional[TreeNode]:
        """Get a node by its ID."""
        for node in self.all_nodes:
            if node.id == node_id:
                return node
        return None

    def leaf_sections(self) -> list[TreeNode]:
        """Get all leaf nodes (sections with no children)."""
        return [node for node in self.all_nodes if not node.children]

    def get_siblings(self, node: TreeNode) -> list[TreeNode]:
        """Get sibling nodes."""
        if node.parent is None:
            return [n for n in self.all_nodes if n.parent is None and n != node]
        return [n for n in node.parent.children if n != node]

    def to_outline(self, include_content: bool = False) -> str:
        """Generate a text outline of the document structure."""
        lines = []

        def walk(node: TreeNode, depth: int = 0):
            if node.level > 0:  # Skip root
                indent = "  " * (node.level - 1)
                path = node.path
                lines.append(f"{indent}{path}. {node.title}")
                if include_content and node.content:
                    content_preview = node.content[:100].replace("\n", " ")
                    lines.append(f"{indent}   [{content_preview}...]")
            for child in node.children:
                walk(child, depth + 1)

        walk(self.root)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return self.root.to_dict()


# Regex to match markdown headers
HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# Code block detection (to skip headers in code blocks)
CODE_BLOCK_PATTERN = re.compile(r'```[\s\S]*?```', re.MULTILINE)


def extract_structure(markdown: str, document_id: Optional[str] = None) -> DocumentTree:
    """
    Extract hierarchical structure from markdown content.

    Args:
        markdown: Markdown content
        document_id: Optional document ID prefix for node IDs

    Returns:
        DocumentTree with hierarchical structure
    """
    doc_prefix = document_id or str(uuid.uuid4())[:8]

    # Find all code blocks to exclude them from header search
    code_blocks = []
    for match in CODE_BLOCK_PATTERN.finditer(markdown):
        code_blocks.append((match.start(), match.end()))

    def is_in_code_block(pos: int) -> bool:
        for start, end in code_blocks:
            if start <= pos < end:
                return True
        return False

    # Split into lines for line number tracking
    lines = markdown.split('\n')
    line_offsets = []
    offset = 0
    for line in lines:
        line_offsets.append(offset)
        offset += len(line) + 1  # +1 for newline

    # Find all headers (not in code blocks)
    headers = []
    for match in HEADER_PATTERN.finditer(markdown):
        if not is_in_code_block(match.start()):
            # Find line number
            line_num = 0
            for i, line_offset in enumerate(line_offsets):
                if line_offset > match.start():
                    break
                line_num = i

            level = len(match.group(1))
            title = match.group(2).strip()
            headers.append({
                "level": level,
                "title": title,
                "start": match.start(),
                "end": match.end(),
                "line": line_num,
            })

    # Create root node
    root = TreeNode(
        id=f"{doc_prefix}_root",
        level=0,
        title="Document Root",
        start_line=0,
        end_line=len(lines),
    )

    all_nodes = [root]

    if not headers:
        # No headers - entire document is content under root
        root.content = markdown
        return DocumentTree(root=root, all_nodes=all_nodes)

    # Build tree
    # Keep track of the current "parent stack" at each level
    parent_stack = {0: root}

    for i, header in enumerate(headers):
        level = header["level"]
        title = header["title"]
        start_line = header["line"]

        # Determine end line (start of next header or end of document)
        if i + 1 < len(headers):
            end_line = headers[i + 1]["line"]
            content_end = headers[i + 1]["start"]
        else:
            end_line = len(lines)
            content_end = len(markdown)

        # Extract content (text between this header and next header)
        content_start = header["end"] + 1  # Skip header line
        content = markdown[content_start:content_end].strip()

        # Create node
        node = TreeNode(
            id=f"{doc_prefix}_{i}",
            level=level,
            title=title,
            content=content,
            start_line=start_line,
            end_line=end_line,
        )

        # Find parent (closest ancestor with lower level)
        parent_level = level - 1
        while parent_level >= 0 and parent_level not in parent_stack:
            parent_level -= 1

        parent = parent_stack.get(parent_level, root)
        node.parent = parent
        parent.children.append(node)

        # Update parent stack
        parent_stack[level] = node
        # Remove deeper levels from stack
        for l in list(parent_stack.keys()):
            if l > level:
                del parent_stack[l]

        all_nodes.append(node)

    # Add any content before first header to root
    first_header_start = headers[0]["start"]
    preamble = markdown[:first_header_start].strip()
    if preamble:
        root.content = preamble

    return DocumentTree(root=root, all_nodes=all_nodes)


def count_tokens_approx(text: str) -> int:
    """Approximate token count (rough estimate: 4 chars per token)."""
    return len(text) // 4
