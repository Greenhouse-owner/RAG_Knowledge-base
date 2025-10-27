# RAG Question Answering System

This project is a Retrieval-Augmented Generation (RAG) based question answering system specifically designed to answer questions about company annual reports. The system combines the following technologies:

- Custom PDF parsing with Mineru service (instead of Docling)
- Vector search with parent document retrieval
- LLM reranking for improved context relevance
- Structured output prompting with chain-of-thought reasoning
- Query routing for multi-company comparisons

## Disclaimer

This is a RAG system for processing company annual reports, and the code may have imperfections:

- The code may have rough edges and temporary workarounds
- Minimal error handling and virtually no testing
- You'll need your own OpenAI/Gemini API keys
- You'll need your own Mineru API key for PDF parsing
- GPU can significantly accelerate PDF parsing (high-performance graphics card recommended)

If you're looking for production-ready code, this might not be the best choice. However, if you want to explore different RAG techniques and implementations, you can refer to this project.

## Quick Start

Clone and setup:
```bash
git clone https://github.com/IlyaRice/RAG-Challenge-2.git
cd RAG-Challenge-2
python -m venv venv
venv\Scripts\Activate.ps1  # Windows (PowerShell)
pip install -e . -r requirements.txt
```

Rename `env` to `.env` and add your API keys. Note that we use Mineru service for PDF parsing, so you'll need a Mineru API key.

## Test Dataset

The repository includes a test dataset:

- The `data/stock_data/` directory contains annual reports and related questions for multiple companies

You can use this dataset to:
- Study example questions and reports
- Run the full pipeline with provided PDFs
- Use pre-processed data to directly enter specific processing stages

## Usage

You can run any part of the pipeline by uncommenting the method you want to run in `src/pipeline.py` and executing:
```bash
python .\src\pipeline.py
```

You can also run any pipeline stage using `main.py`, but you need to run it from the directory containing your data:
```bash
cd .\data\stock_data\
python ..\..\main.py process-questions --config max_nst_o3m
```

### CLI Commands

Get help on available commands:
```bash
python main.py --help
```

Available commands:
- `download-models` - Download required docling models
- `parse-pdfs` - Parse PDF reports with parallel processing options
- `serialize-tables` - Process tables in parsed reports
- `process-reports` - Run the full pipeline on parsed reports
- `process-questions` - Process questions using specified config

Each command has its own options. For example:
```bash
python main.py parse-pdfs --help
# Shows options like --parallel/--sequential, --chunk-size, --max-workers

python main.py process-reports --config ser_tab
# Process reports with serialized tables config
```

## Configuration

- `max` - Best performing configuration using Qwen-Turbo model
- `pdr` - Configuration using parent document retrieval
- `base` - Basic configuration

Check `pipeline.py` for more configurations and details.

## Web Interface

The project includes a web interface based on Streamlit, which can be started with the following command:
```bash
streamlit run app_streamlit.py
```

Before using the web interface, please ensure:
1. PDF annual reports are placed in the `data/stock_data/pdf_reports` directory
2. Run `python src/pipeline.py` to complete the data processing pipeline

## License

MIT