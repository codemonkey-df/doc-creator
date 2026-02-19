/**
 * DOCX Converter - Converts parsed markdown blocks to Word documents
 */

const fs = require('fs');
const path = require('path');
const minimist = require('minimist');
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
  TableCellBorderOptions,
  LevelFormat,
  PageBreak
} = require('docx');

const { parseMarkdown } = require('./md_parser');

/**
 * Convert inline formatting in text to TextRun arrays
 * @param {string} text - Text with inline formatting
 * @returns {TextRun[]} Array of TextRun objects
 */
function parseInlineFormatting(text) {
  if (!text) {
    return [new TextRun({ text: '' })];
  }

  const runs = [];
  let remaining = text;

  // Regex for bold (**text**) and `code`
  const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // Add any text before the match
    if (match.index > lastIndex) {
      runs.push(new TextRun({
        text: text.slice(lastIndex, match.index)
      }));
    }

    const matchText = match[0];
    if (matchText.startsWith('**') && matchText.endsWith('**')) {
      // Bold text
      runs.push(new TextRun({
        text: matchText.slice(2, -2),
        bold: true
      }));
    } else if (matchText.startsWith('`') && matchText.endsWith('`')) {
      // Inline code
      runs.push(new TextRun({
        text: matchText.slice(1, -1),
        font: 'Courier New'
      }));
    }

    lastIndex = match.index + matchText.length;
  }

  // Add remaining text after last match
  if (lastIndex < text.length) {
    runs.push(new TextRun({
      text: text.slice(lastIndex)
    }));
  }

  return runs.length > 0 ? runs : [new TextRun({ text: '' })];
}

/**
 * Convert a block to docx elements
 * @param {Object} block - Block object from md_parser
 * @returns {Paragraph} docx Paragraph
 */
function blockToParagraph(block) {
  switch (block.type) {
    case 'heading': {
      let headingLevel;
      switch (block.level) {
        case 1:
          headingLevel = HeadingLevel.HEADING_1;
          break;
        case 2:
          headingLevel = HeadingLevel.HEADING_2;
          break;
        case 3:
          headingLevel = HeadingLevel.HEADING_3;
          break;
        default:
          headingLevel = HeadingLevel.HEADING_1;
      }
      return new Paragraph({
        heading: headingLevel,
        children: [new TextRun({ text: block.text, bold: true })],
        outlineLevel: block.level
      });
    }

    case 'paragraph':
      return new Paragraph({
        children: parseInlineFormatting(block.text)
      });

    case 'code':
      return new Paragraph({
        children: [new TextRun({
          text: block.content,
          font: 'Courier New',
          size: 24 // 12pt = 24 half-points
        })],
        shading: {
          val: ShadingType.CLEAR,
          fill: 'E0E0E0'
        }
      });

    case 'bullet_list': {
      const children = block.items.map((item, index) =>
        new Paragraph({
          text: item,
          bullet: {
            level: 0
          }
        })
      );
      return children;
    }

    case 'numbered_list': {
      const children = block.items.map((item, index) =>
        new Paragraph({
          text: item,
          numbering: {
            reference: 'numbered-list',
            level: 0
          }
        })
      );
      return children;
    }

    case 'table': {
      const headerRow = new TableRow({
        children: block.headers.map(header =>
          new TableCell({
            children: [new Paragraph({
              children: [new TextRun({ text: header, bold: true })]
            })],
            shading: {
              val: ShadingType.CLEAR,
              fill: 'D0D0D0'
            }
          })
        )
      });

      const dataRows = block.rows.map(row =>
        new TableRow({
          children: row.map(cell =>
            new TableCell({
              children: [new Paragraph({
                children: [new TextRun({ text: cell })]
              })]
            })
          )
        })
      );

      return new Table({
        rows: [headerRow, ...dataRows],
        width: {
          type: WidthType.DXA,
          size: 10000
        }
      });
    }

    case 'blockquote':
      return new Paragraph({
        children: [new TextRun({ text: block.text, italics: true })],
        indent: {
          left: 720 // 0.5 inch
        }
      });

    case 'placeholder':
      return new Paragraph({
        children: [new TextRun({ text: `[${block.text}]`, italics: true })]
      });

    default:
      return new Paragraph({
        children: [new TextRun({ text: '' })]
      });
  }
}

/**
 * Define document styles
 * @returns {Object} Style definitions
 */
function createStyles() {
  return {
    headings: {
      heading1: {
        run: {
          bold: true,
          size: 48 // 24pt = 48 half-points
        },
        paragraph: {
          spacing: {
            after: 200
          }
        }
      },
      heading2: {
        run: {
          bold: true,
          size: 36 // 18pt = 36 half-points
        },
        paragraph: {
          spacing: {
            after: 120
          }
        }
      },
      heading3: {
        run: {
          bold: true,
          size: 28 // 14pt = 28 half-points
        },
        paragraph: {
          spacing: {
            after: 100
          }
        }
      }
    }
  };
}

/**
 * Build the document from parsed blocks
 * @param {Object[]} blocks - Array of block objects
 * @param {string} title - Document title
 * @returns {Document} docx Document
 */
function buildDocument(blocks, title) {
  const children = [];

  // Section 1 - Title Page
  children.push(
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({
          text: title || 'Document Title',
          size: 72, // 36pt
          bold: true
        })
      ]
    })
  );
  children.push(new Paragraph({ children: [new PageBreak()] }));

  // Section 2 - TOC Page
  children.push(
    new Paragraph({
      heading: HeadingLevel.HEADING_1,
      children: [new TextRun({ text: 'Table of Contents', bold: true })]
    })
  );
  children.push(
    new TableOfContents('TOC', {
      heading1Range: '1-3',
      stylesWithLevels: [
        { name: 'Heading1', styleId: 'Heading1' },
        { name: 'Heading2', styleId: 'Heading2' },
        { name: 'Heading3', styleId: 'Heading3' }
      ]
    })
  );
  children.push(new Paragraph({ children: [new PageBreak()] }));

  // Define numbering for numbered lists
  const numbering = {
    config: [
      {
        reference: 'numbered-list',
        levels: [
          {
            level: 0,
            format: LevelFormat.DECIMAL,
            text: '%1.',
            alignment: AlignmentType.LEFT
          }
        ]
      }
    ]
  };

  // Section 3+ - Content
  const contentElements = [];

  // Add document title as H1 at the start
  if (title) {
    contentElements.push(
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: title, bold: true })]
      })
    );
  }

  for (const block of blocks) {
    const elements = blockToParagraph(block);

    // Handle arrays of paragraphs (lists)
    if (Array.isArray(elements)) {
      contentElements.push(...elements);
    } else {
      contentElements.push(elements);
    }
  }

  const document = new Document({
    sections: [
      {
        properties: {},
        children: children
      },
      {
        properties: {},
        children: contentElements,
        numbering
      }
    ]
  });

  return document;
}

/**
 * Main function
 */
function main() {
  const args = minimist(process.argv.slice(2));

  const inputFile = args._[0];
  const title = args.title || '';
  const outputFile = args.output || 'output.docx';

  if (!inputFile) {
    console.error('Usage: node convert.js <input.md> [--title "Title"] [--output <output.docx>]');
    process.exit(1);
  }

  // Read input file
  const inputPath = path.resolve(inputFile);
  if (!fs.existsSync(inputPath)) {
    console.error(`Error: Input file not found: ${inputPath}`);
    process.exit(1);
  }

  const markdownContent = fs.readFileSync(inputPath, 'utf-8');

  // Parse markdown
  const blocks = parseMarkdown(markdownContent);

  // Build document
  const document = buildDocument(blocks, title);

  // Write output file
  Packer.toBuffer(document).then(buffer => {
    const outputPath = path.resolve(outputFile);
    fs.writeFileSync(outputPath, buffer);
    console.log(`Success: Document created at ${outputPath}`);
  }).catch(err => {
    console.error('Error creating document:', err);
    process.exit(1);
  });
}

main();
