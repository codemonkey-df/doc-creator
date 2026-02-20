'use strict';

/**
 * DocForge DOCX Converter — v2
 *
 * Improvements over v1:
 * - Mermaid blocks: styled diagram info box with type detection + raw source preserved
 * - Code blocks: dark language label header strip (github-style)
 * - Empty code block: safe fallback, no crash
 * - Headings with inline code: parseInline applied to heading text
 * - Bold-only list items e.g. "**Key Tasks:**": trailing orphan ** cleaned up
 * - Consecutive blockquotes: spacing ensures visual separation
 * - Table cells: full inline formatting (bold, code, italic)
 */

const fs = require('fs');
const path = require('path');
const { parseMarkdown } = require('./md_parser');

const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  TableOfContents,
  Table,
  TableRow,
  TableCell,
  WidthType,
  AlignmentType,
  BorderStyle,
  ShadingType,
  PageBreak,
  LevelFormat,
  VerticalAlign,
} = require('docx');

const CONTENT_WIDTH = 9360; // US Letter with 1-inch margins

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
function createStyles() {
  return {
    default: {
      document: { run: { font: 'Calibri', size: 24 } },
    },
    paragraphStyles: [
      {
        id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 36, bold: true, font: 'Arial', color: '1A1A1A' },
        paragraph: { spacing: { before: 480, after: 160 }, keepNext: true, outlineLevel: 0 },
      },
      {
        id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 28, bold: true, font: 'Arial', color: '2E74B5' },
        paragraph: { spacing: { before: 400, after: 120 }, keepNext: true, outlineLevel: 1 },
      },
      {
        id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 24, bold: true, font: 'Arial', color: '1F4D78' },
        paragraph: { spacing: { before: 320, after: 80 }, keepNext: true, outlineLevel: 2 },
      },
      {
        id: 'Body', name: 'Body Text', basedOn: 'Normal', quickFormat: true,
        run: { size: 22, font: 'Calibri', color: '1F1F1F' },
        paragraph: { spacing: { after: 160, line: 276 } },
      },
      {
        id: 'CodeText', name: 'Code Text', basedOn: 'Normal',
        run: { font: 'Consolas', size: 18, color: '24292E' },
        paragraph: { spacing: { after: 20, before: 0, line: 240 } },
      },
      {
        id: 'Quote', name: 'Quote', basedOn: 'Normal',
        run: { italics: true, color: '444444', font: 'Calibri', size: 22 },
        paragraph: {
          indent: { left: 720 },
          spacing: { before: 120, after: 120 },
          border: { left: { style: BorderStyle.SINGLE, size: 24, color: '2E74B5', space: 240 } },
        },
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Numbering
// ---------------------------------------------------------------------------
function createNumbering() {
  return {
    config: [
      {
        reference: 'bullets',
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: '\u2022', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
          { level: 1, format: LevelFormat.BULLET, text: '\u25E6', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
          { level: 2, format: LevelFormat.BULLET, text: '\u25AA', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 2160, hanging: 360 } } } },
        ],
      },
      {
        reference: 'numbers',
        levels: [
          { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
          { level: 1, format: LevelFormat.LOWER_LETTER, text: '%2.', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
        ],
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Inline formatter — **bold**, *italic*, `code`, cleans orphan **
// ---------------------------------------------------------------------------
function parseInline(text) {
  if (!text) return [new TextRun({ text: '' })];
  const runs = [];
  const regex = /(\*\*[^*]+?\*\*|\*[^*\n]+?\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const plain = text.slice(lastIndex, match.index);
      if (plain) runs.push(new TextRun({ text: plain }));
    }
    const m = match[0];
    if (m.startsWith('**')) {
      runs.push(new TextRun({ text: m.slice(2, -2), bold: true }));
    } else if (m.startsWith('*')) {
      runs.push(new TextRun({ text: m.slice(1, -1), italics: true }));
    } else if (m.startsWith('`')) {
      runs.push(new TextRun({
        text: m.slice(1, -1), font: 'Consolas', size: 20, color: 'C7254E',
        shading: { fill: 'F9F2F4', val: ShadingType.CLEAR },
      }));
    }
    lastIndex = match.index + m.length;
  }

  if (lastIndex < text.length) {
    const remaining = text.slice(lastIndex).replace(/\*\*/g, '').replace(/(?<![a-zA-Z])\*(?![a-zA-Z])/g, '');
    if (remaining) runs.push(new TextRun({ text: remaining }));
  }

  return runs.length ? runs : [new TextRun({ text: '' })];
}

// ---------------------------------------------------------------------------
// Mermaid diagram type detector
// ---------------------------------------------------------------------------
function detectMermaidType(firstLine) {
  const fl = (firstLine || '').trim().toLowerCase();
  if (fl.startsWith('graph') || fl.startsWith('flowchart')) return 'Flowchart';
  if (fl.startsWith('sequencediagram')) return 'Sequence Diagram';
  if (fl.startsWith('classdiagram')) return 'Class Diagram';
  if (fl.startsWith('erdiagram')) return 'Entity-Relationship Diagram';
  if (fl.startsWith('gantt')) return 'Gantt Chart';
  if (fl.startsWith('pie')) return 'Pie Chart';
  if (fl.startsWith('statediagram')) return 'State Diagram';
  if (fl.startsWith('journey')) return 'User Journey';
  if (fl.startsWith('mindmap')) return 'Mind Map';
  if (fl.startsWith('timeline')) return 'Timeline';
  return 'Mermaid Diagram';
}

// ---------------------------------------------------------------------------
// Code / Mermaid block renderer
// ---------------------------------------------------------------------------
function renderCodeBlock(block) {
  const lang = (block.lang || '').trim().toLowerCase();
  const isMermaid = lang === 'mermaid';
  const contentLines = (block.content || ' ').split('\n');
  const hasContent = contentLines.some((l) => l.trim());
  const safeLines = hasContent ? contentLines : [' '];

  const thinBorder = { style: BorderStyle.SINGLE, size: 4, color: 'D0D7DE' };
  const blueBorder = { style: BorderStyle.SINGLE, size: 4, color: '2E74B5' };
  const nil = { style: BorderStyle.NIL };

  if (isMermaid) {
    const diagramType = detectMermaidType(contentLines[0]);
    return [
      new Table({
        width: { size: CONTENT_WIDTH, type: WidthType.DXA },
        columnWidths: [CONTENT_WIDTH],
        rows: [
          // Header row
          new TableRow({
            children: [new TableCell({
              shading: { fill: '2E74B5', val: ShadingType.CLEAR },
              margins: { top: 100, bottom: 100, left: 180, right: 180 },
              width: { size: CONTENT_WIDTH, type: WidthType.DXA },
              borders: { top: blueBorder, bottom: nil, left: blueBorder, right: blueBorder },
              children: [new Paragraph({ children: [
                new TextRun({ text: '\uD83D\uDCCA  Diagram \u2014 ' + diagramType, font: 'Arial', size: 18, bold: true, color: 'FFFFFF' }),
              ]})],
            })],
          }),
          // Note row
          new TableRow({
            children: [new TableCell({
              shading: { fill: 'EBF3FB', val: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 180, right: 180 },
              width: { size: CONTENT_WIDTH, type: WidthType.DXA },
              borders: { top: nil, bottom: nil, left: blueBorder, right: blueBorder },
              children: [new Paragraph({ children: [
                new TextRun({ text: 'Mermaid source \u2014 render at ', font: 'Calibri', size: 18, italics: true, color: '555555' }),
                new TextRun({ text: 'mermaid.live', font: 'Calibri', size: 18, italics: true, bold: true, color: '2E74B5' }),
                new TextRun({ text: ' or any Mermaid-enabled viewer.', font: 'Calibri', size: 18, italics: true, color: '555555' }),
              ]})],
            })],
          }),
          // Source row
          new TableRow({
            children: [new TableCell({
              shading: { fill: 'F0F4F8', val: ShadingType.CLEAR },
              margins: { top: 140, bottom: 140, left: 200, right: 200 },
              width: { size: CONTENT_WIDTH, type: WidthType.DXA },
              borders: { top: nil, bottom: blueBorder, left: blueBorder, right: blueBorder },
              children: safeLines.map((line) => new Paragraph({
                style: 'CodeText',
                children: [new TextRun({ text: line || ' ' })],
              })),
            })],
          }),
        ],
      }),
    ];
  }

  // Regular code block
  const rows = [];

  if (lang) {
    // Dark language label strip
    rows.push(new TableRow({
      children: [new TableCell({
        shading: { fill: '24292E', val: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 180, right: 180 },
        width: { size: CONTENT_WIDTH, type: WidthType.DXA },
        borders: { top: thinBorder, bottom: nil, left: thinBorder, right: thinBorder },
        children: [new Paragraph({ children: [
          new TextRun({ text: lang, font: 'Consolas', size: 16, bold: true, color: '8B949E' }),
        ]})],
      })],
    }));
  }

  // Code content
  rows.push(new TableRow({
    children: [new TableCell({
      shading: { fill: 'F6F8FA', val: ShadingType.CLEAR },
      margins: { top: 140, bottom: 140, left: 200, right: 200 },
      width: { size: CONTENT_WIDTH, type: WidthType.DXA },
      borders: lang
        ? { top: nil, bottom: thinBorder, left: thinBorder, right: thinBorder }
        : { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder },
      children: safeLines.map((line) => new Paragraph({
        style: 'CodeText',
        children: [new TextRun({ text: line || ' ' })],
      })),
    })],
  }));

  return [new Table({ width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: [CONTENT_WIDTH], rows })];
}

// ---------------------------------------------------------------------------
// Block → elements
// ---------------------------------------------------------------------------
function blockToElements(block, isFirst) {
  switch (block.type) {

    case 'heading': {
      const text = block.text.trim();
      let headingLevel;
      switch (block.level) {
        case 1: headingLevel = HeadingLevel.HEADING_1; break;
        case 2: headingLevel = HeadingLevel.HEADING_2; break;
        case 3: headingLevel = HeadingLevel.HEADING_3; break;
        default: headingLevel = HeadingLevel.HEADING_4;
      }
      const isChapter = block.level === 2 && /^chapter\s+\d+/i.test(text);
      const needsPageBreak = isChapter && !isFirst;
      const para = new Paragraph({ heading: headingLevel, children: parseInline(text) });
      return needsPageBreak ? [new Paragraph({ children: [new PageBreak()] }), para] : [para];
    }

    case 'paragraph':
      return [new Paragraph({ style: 'Body', children: parseInline(block.text) })];

    case 'code':
      return renderCodeBlock(block);

    case 'bullet_list':
      return block.items.map((item) =>
        new Paragraph({
          style: 'Body',
          numbering: { reference: 'bullets', level: Math.min(item.level || 0, 2) },
          children: parseInline(item.text),
        })
      );

    case 'numbered_list':
      return block.items.map((item) =>
        new Paragraph({
          style: 'Body',
          numbering: { reference: 'numbers', level: Math.min(item.level || 0, 1) },
          children: parseInline(item.text),
        })
      );

    case 'blockquote':
      return [new Paragraph({
        style: 'Quote',
        spacing: { before: 160, after: 160 },
        children: parseInline(block.text),
      })];

    case 'table': {
      const border = { style: BorderStyle.SINGLE, size: 4, color: 'C0C0C0' };
      const borders = { top: border, bottom: border, left: border, right: border };
      const colCount = block.headers.length;
      const colWidth = Math.floor(CONTENT_WIDTH / colCount);

      const headerRow = new TableRow({
        tableHeader: true,
        children: block.headers.map((h) =>
          new TableCell({
            borders, width: { size: colWidth, type: WidthType.DXA },
            margins: { top: 100, bottom: 100, left: 140, right: 140 },
            shading: { fill: 'D5E8F0', val: ShadingType.CLEAR },
            verticalAlign: VerticalAlign.CENTER,
            children: [new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: h, bold: true, font: 'Calibri', size: 22 })],
            })],
          })
        ),
      });

      const dataRows = (block.rows || []).map((row) =>
        new TableRow({
          children: row.map((cell) =>
            new TableCell({
              borders, width: { size: colWidth, type: WidthType.DXA },
              margins: { top: 80, bottom: 80, left: 140, right: 140 },
              children: [new Paragraph({ style: 'Body', children: parseInline(cell) })],
            })
          ),
        })
      );

      return [
        new Table({ width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: Array(colCount).fill(colWidth), rows: [headerRow, ...dataRows] }),
        new Paragraph({ children: [], spacing: { after: 160 } }),
      ];
    }

    case 'hr':
      return [new Paragraph({
        children: [],
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'DDDDDD', space: 1 } },
        spacing: { before: 120, after: 120 },
      })];

    default:
      return [];
  }
}

// ---------------------------------------------------------------------------
// Build Document
// ---------------------------------------------------------------------------
function buildDocument(blocks, rawTitle) {
  const finalTitle = rawTitle || 'Untitled Document';
  const children = [];

  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 2880, after: 480 },
    children: [new TextRun({ text: finalTitle, size: 72, bold: true, font: 'Arial', color: '000000' })],
  }));
  children.push(new Paragraph({ children: [new PageBreak()] }));

  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new TextRun({ text: 'Table of Contents', size: 36, bold: true, font: 'Arial' })],
  }));
  children.push(new TableOfContents('TOC', { hyperlink: true, headingStyleRange: '1-3' }));
  children.push(new Paragraph({ children: [new PageBreak()] }));

  blocks.forEach((block, idx) => {
    children.push(...blockToElements(block, idx === 0));
  });

  return new Document({
    styles: createStyles(),
    numbering: createNumbering(),
    features: { updateFields: true },
    sections: [{
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      children,
    }],
  });
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------
function main() {
  const argv = process.argv.slice(2);
  const args = { _: [], title: '', output: 'output.docx' };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--title' && argv[i + 1]) args.title = argv[++i];
    else if (argv[i] === '--output' && argv[i + 1]) args.output = argv[++i];
    else if (!argv[i].startsWith('--')) args._.push(argv[i]);
  }

  const inputFile = args._[0];
  if (!inputFile) {
    console.error('Usage: node convert.js <input.md> [--title "Title"] [--output out.docx]');
    process.exit(1);
  }

  const inputPath = path.resolve(inputFile);
  if (!fs.existsSync(inputPath)) {
    console.error('Input file not found: ' + inputPath);
    process.exit(1);
  }

  const blocks = parseMarkdown(fs.readFileSync(inputPath, 'utf-8'));
  const doc = buildDocument(blocks, args.title);

  Packer.toBuffer(doc)
    .then((buffer) => {
      const outputPath = path.resolve(args.output);
      fs.writeFileSync(outputPath, buffer);
      console.log('✓ Saved: ' + outputPath);
      console.log('  TIP: Right-click TOC in Word → Update Field → Update entire table');
    })
    .catch((err) => { console.error('Error:', err); process.exit(1); });
}

main();
