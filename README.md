# Doc Creator

Doc Creator is a document creation pipeline that converts markdown files to formatted DOCX documents. The converter is implemented in Node.js and uses the `docx` library to generate Word documents.

To run the converter, you need **uv** for Python dependencies and **Node.js** with **npm** for the converter. 

First, install Python dependencies with `uv sync`, then install converter dependencies by running `npm install` in the `converter/` directory. The main application requires Python 3.11+ and Node.js 18+.


## Run app
In root dir please do

  1. `uv sync`
  2. `uv run -m src.main`

In TUI please use:
  1. To name document use `/title` 
  2. To add introduction `/intro ID` ( id of document to use )
  3. To add chapter `/chapter ID` ( id of document to use )
  4. Type `/generate` and check `/output` folder for results