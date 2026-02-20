'use strict';

/**
 * Markdown Parser for DocForge
 * Parses markdown into a structured block array for DOCX conversion.
 * Handles: headings, paragraphs, bullet lists (nested), numbered lists, 
 * code blocks, blockquotes, tables, and horizontal rules.
 */

/**
 * Count leading spaces/tabs to determine list indent level
 */
function getLeadingSpaces(line) {
  const match = line.match(/^(\s*)/);
  return match ? match[1].length : 0;
}

/**
 * Main parse function - returns array of block objects
 */
function parseMarkdown(text) {
  const lines = text.split('\n');
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // Skip empty lines
    if (!trimmed) {
      i++;
      continue;
    }

    // Heading
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)/);
    if (headingMatch) {
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
      });
      i++;
      continue;
    }

    // Fenced code block
    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({
        type: 'code',
        lang,
        content: codeLines.join('\n'),
      });
      continue;
    }

    // Blockquote
    if (trimmed.startsWith('>')) {
      const quoteLines = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ''));
        i++;
      }
      blocks.push({
        type: 'blockquote',
        text: quoteLines.join(' '),
      });
      continue;
    }

    // Table (pipe-separated)
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const tableLines = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i].trim());
        i++;
      }
      // Parse table: first row = headers, second row = separator, rest = data
      const parseRow = (row) =>
        row
          .slice(1, -1) // remove outer pipes
          .split('|')
          .map((cell) => cell.trim());

      const headers = parseRow(tableLines[0]);
      const rows = tableLines
        .slice(2) // skip separator
        .map(parseRow);

      blocks.push({ type: 'table', headers, rows });
      continue;
    }

    // Bullet list (*, -, +)
    if (/^\s*[\*\-\+]\s/.test(line)) {
      const items = [];
      while (i < lines.length) {
        const l = lines[i];
        const isContinuation = l.trim() === '' ? false : true;
        const isBullet = /^\s*[\*\-\+]\s/.test(l);
        const isNested = /^\s+[\*\-\+]\s/.test(l) || /^\s{4,}/.test(l);

        if (!l.trim()) {
          // Check if next line is still a list item
          const next = lines[i + 1];
          if (!next || !/^\s*[\*\-\+]\s/.test(next)) break;
          i++;
          continue;
        }

        if (isBullet) {
          const spaces = getLeadingSpaces(l);
          // Level: 0 for top-level (0-3 spaces), 1 for (4-7), 2 for (8+)
          const level = Math.floor(spaces / 4);
          const text = l.trim().replace(/^[\*\-\+]\s+/, '');
          items.push({ text, level });
          i++;
        } else {
          break;
        }
      }
      blocks.push({ type: 'bullet_list', items });
      continue;
    }

    // Numbered list
    if (/^\s*\d+\.\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s/.test(lines[i])) {
        const spaces = getLeadingSpaces(lines[i]);
        const level = Math.floor(spaces / 4);
        const text = lines[i].trim().replace(/^\d+\.\s+/, '');
        items.push({ text, level });
        i++;
      }
      blocks.push({ type: 'numbered_list', items });
      continue;
    }

    // Horizontal rule
    if (/^[-*_]{3,}$/.test(trimmed)) {
      blocks.push({ type: 'hr' });
      i++;
      continue;
    }

    // Paragraph - collect until blank line or block element
    const paraLines = [];
    while (i < lines.length) {
      const l = lines[i];
      const t = l.trim();
      if (!t) break;
      if (/^#{1,6}\s/.test(t)) break;
      if (t.startsWith('```')) break;
      if (t.startsWith('>')) break;
      if (t.startsWith('|') && t.endsWith('|')) break;
      if (/^\s*[\*\-\+]\s/.test(l)) break;
      if (/^\s*\d+\.\s/.test(l)) break;
      if (/^[-*_]{3,}$/.test(t)) break;
      paraLines.push(t);
      i++;
    }
    if (paraLines.length) {
      blocks.push({ type: 'paragraph', text: paraLines.join(' ') });
    }
  }

  return blocks;
}

module.exports = { parseMarkdown };
