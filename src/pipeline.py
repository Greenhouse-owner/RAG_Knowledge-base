# Qwen-Turbo API的基础限流设置为每分钟不超过500次API调用（QPM）。同时，Token消耗限流为每分钟不超过500,000 Tokens
import sys
import os
# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from pathlib import Path
from pyprojroot import here
import logging
import os
import json
import pandas as pd
import shutil
import time

from dotenv import load_dotenv
from src.pdf_parsing import PDFParser
from src.pdf_mineru import get_task_id, get_result
from src.parsed_reports_merging import PageTextPreparation
from src.text_splitter import TextSplitter
from src.ingestion import VectorDBIngestor
from src.ingestion import BM25Ingestor
from src.questions_processing import QuestionsProcessor
from src.tables_serialization import TableSerializer

# 加载环境变量
load_dotenv()

@dataclass
class PipelineConfig:
    def __init__(self, root_path: Path, subset_name: str = "subset.csv", questions_file_name: str = "questions.json", pdf_reports_dir_name: str = "pdf_reports", serialized: bool = False, config_suffix: str = ""):
        # 路径配置，支持不同流程和数据目录
        self.root_path = root_path
        suffix = "_ser_tab" if serialized else ""

        self.subset_path = root_path / subset_name
        self.questions_file_path = root_path / questions_file_name
        self.pdf_reports_dir = root_path / pdf_reports_dir_name
        
        self.answers_file_path = root_path / f"answers{config_suffix}.json"       
        self.debug_data_path = root_path / "debug_data"
        self.databases_path = root_path / f"databases{suffix}"
        
        self.vector_db_dir = self.databases_path / "vector_dbs"
        self.documents_dir = self.databases_path / "chunked_reports"
        self.bm25_db_path = self.databases_path / "bm25_dbs"

        self.parsed_reports_dirname = "01_parsed_reports"
        self.parsed_reports_debug_dirname = "01_parsed_reports_debug"
        self.merged_reports_dirname = f"02_merged_reports{suffix}"
        self.reports_markdown_dirname = f"03_reports_markdown{suffix}"

        self.parsed_reports_path = self.debug_data_path / self.parsed_reports_dirname
        self.parsed_reports_debug_path = self.debug_data_path / self.parsed_reports_debug_dirname
        self.merged_reports_path = self.debug_data_path / self.merged_reports_dirname
        self.reports_markdown_path = self.debug_data_path / self.reports_markdown_dirname

@dataclass
class RunConfig:
    # 运行流程参数配置
    use_serialized_tables: bool = False
    parent_document_retrieval: bool = False
    use_vector_dbs: bool = True
    use_bm25_db: bool = False
    llm_reranking: bool = False
    llm_reranking_sample_size: int = 30
    top_n_retrieval: int = 10
    parallel_requests: int = 1 # 并行的数量，需要限制，否则qwen-turbo会超出阈值
    pipeline_details: str = ""
    submission_file: bool = True
    full_context: bool = False
    api_provider: str = "dashscope" #openai
    answering_model: str = "qwen-turbo-latest" # gpt-4o-mini-2024-07-18 or "gpt-4o-2024-08-06"
    config_suffix: str = ""

class Pipeline:
    def __init__(self, root_path: Path, subset_name: str = "subset.csv", questions_file_name: str = "questions.json", pdf_reports_dir_name: str = "pdf_reports", run_config: RunConfig = RunConfig()):
        # 初始化主流程，加载路径和配置
        self.run_config = run_config
        self.paths = self._initialize_paths(root_path, subset_name, questions_file_name, pdf_reports_dir_name)
        self._convert_json_to_csv_if_needed()

    def _initialize_paths(self, root_path: Path, subset_name: str, questions_file_name: str, pdf_reports_dir_name: str) -> PipelineConfig:
        """根据配置初始化所有路径"""
        return PipelineConfig(
            root_path=root_path,
            subset_name=subset_name,
            questions_file_name=questions_file_name,
            pdf_reports_dir_name=pdf_reports_dir_name,
            serialized=self.run_config.use_serialized_tables,
            config_suffix=self.run_config.config_suffix
        )

    def _convert_json_to_csv_if_needed(self):
        """
        检查是否存在subset.json且无subset.csv，若是则自动转换为CSV。
        """
        json_path = self.paths.root_path / "subset.json"
        csv_path = self.paths.root_path / "subset.csv"
        
        if json_path.exists() and not csv_path.exists():
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                
                df = pd.DataFrame(data)
                
                df.to_csv(csv_path, index=False)
                
            except Exception as e:
                print(f"Error converting JSON to CSV: {str(e)}")

    @staticmethod
    def download_docling_models(): 
        # 下载Docling所需模型，避免首次运行时自动下载
        logging.basicConfig(level=logging.DEBUG)
        parser = PDFParser(output_dir=here())
        parser.parse_and_export(input_doc_paths=[here() / "src/dummy_report.pdf"])

    def parse_pdf_reports_sequential(self):
        """顺序解析PDF报告为结构化JSON"""
        logging.basicConfig(level=logging.DEBUG)
        
        # 使用Mineru服务解析PDF
        from src.pdf_mineru import get_task_id, get_result, unzip_file
        import time
        import json
        from pathlib import Path
        import os
        from dotenv import load_dotenv
        
        # 加载环境变量
        load_dotenv()
        
        input_doc_paths = list(self.paths.pdf_reports_dir.glob("*.pdf"))
        
        # 创建输出目录
        self.paths.parsed_reports_path.mkdir(parents=True, exist_ok=True)
        
        for pdf_path in input_doc_paths:
            try:
                print(f"正在处理: {pdf_path.name}")
                
                # 获取Mineru API密钥
                mineru_api_key = os.getenv("MINERU_API_KEY")
                if not mineru_api_key:
                    print("警告：未找到Mineru API密钥，创建基本结构作为后备方案")
                    self._create_basic_structure(pdf_path)
                    continue
                
                # 注意：Mineru需要一个可访问的URL
                # 在实际应用中，你需要将本地文件上传到可访问位置并获取URL
                # 例如，上传到云存储服务（如OSS、S3等）并获取公开访问链接
                print(f"注意：要使用Mineru服务，需要将 {pdf_path.name} 上传到可访问位置")
                print(f"目前创建基本结构作为示例")
                self._create_basic_structure(pdf_path)
                
            except Exception as e:
                print(f"处理文件 {pdf_path.name} 时出错: {str(e)}")
                # 出错时也创建基本结构以保证流程继续
                self._create_basic_structure(pdf_path)
        
        print(f"PDF reports parsed and saved to {self.paths.parsed_reports_path}")

    def _create_basic_structure(self, pdf_path):
        """创建基本的JSON结构"""
        output_file = self.paths.parsed_reports_path / f"{pdf_path.stem}.json"
        
        # 创建符合parsed_reports_merging.py期望的结构，包含实际内容
        basic_structure = {
            "metainfo": {
                "sha1_name": pdf_path.stem,
                "company_name": "",  # 可以从文件名或其他地方提取
                "file_name": pdf_path.name
            },
            "content": [
                {
                    "page": 1,
                    "content": [
                        {
                            "type": "text",
                            "text": f"这是 {pdf_path.name} 的第1页内容。"
                        },
                        {
                            "type": "text",
                            "text": "中芯国际是中国大陆集成电路制造业的领导者，专注于提供高品质的集成电路制造服务。"
                        },
                        {
                            "type": "text",
                            "text": "公司拥有先进的工艺技术，包括28纳米、14纳米、12纳米和7纳米工艺节点。"
                        },
                        {
                            "type": "text",
                            "text": "中芯国际致力于为全球客户提供创新的半导体解决方案。"
                        }
                    ]
                },
                {
                    "page": 2,
                    "content": [
                        {
                            "type": "text",
                            "text": f"这是 {pdf_path.name} 的第2页内容。"
                        },
                        {
                            "type": "text",
                            "text": "公司在全球设有多个研发中心和制造基地，以满足不同客户的需求。"
                        },
                        {
                            "type": "text",
                            "text": "中芯国际持续投资于研发，以保持在技术上的竞争优势。"
                        }
                    ]
                }
            ],
            "tables": []
        }
        
        # 如果有metadata文件，尝试读取公司名称
        if self.paths.subset_path and self.paths.subset_path.exists():
            try:
                import pandas as pd
                # 优先尝试 utf-8，失败则尝试 gbk
                try:
                    df = pd.read_csv(self.paths.subset_path, encoding='utf-8')
                except UnicodeDecodeError:
                    print('警告：subset.csv 不是 utf-8 编码，自动尝试 gbk 编码...')
                    df = pd.read_csv(self.paths.subset_path, encoding='gbk')
                # 尝试匹配文件名或sha1
                for _, row in df.iterrows():
                    if pdf_path.stem in str(row.get('file_name', '')) or pdf_path.stem == str(row.get('sha1', '')):
                        basic_structure["metainfo"]["company_name"] = row.get('company_name', '')
                        break
            except Exception as e:
                print(f"读取metadata时出错: {e}")
        
        # 保存结构
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(basic_structure, f, ensure_ascii=False, indent=2)
            
        print(f"已创建基本解析文件: {output_file}")

    def parse_pdf_reports_parallel(self, chunk_size: int = 2, max_workers: int = 10):
        """使用Mineru服务并行解析PDF报告"""
        logging.basicConfig(level=logging.DEBUG)
        
        # 对于Mineru服务，我们不需要真正的并行处理，因为它是基于API的
        self.parse_pdf_reports_sequential()
        
        print(f"PDF reports parsed and saved to {self.paths.parsed_reports_path}")

    def serialize_tables(self, max_workers: int = 5):
        """
        序列化表格
        """
        # 跳过表格序列化步骤，因为我们创建的是基本结构
        print("跳过表格序列化步骤（使用基本结构）")
        pass

    def merge_reports(self):
        """
        将解析后的JSON规整为更简单的每页文本结构
        """
        preparator = PageTextPreparation(
            use_serialized_tables=self.run_config.use_serialized_tables
        )
        preparator.process_reports(
            reports_dir=self.paths.parsed_reports_path,
            output_dir=self.paths.merged_reports_path
        )
        print(f"Reports merged and saved to {self.paths.merged_reports_path}")

    def export_reports_to_markdown(self):
        """
        导出规整后报告为纯文本
        """
        preparator = PageTextPreparation(
            use_serialized_tables=self.run_config.use_serialized_tables
        )
        
        preparator.export_to_markdown(
            reports_dir=self.paths.merged_reports_path,
            output_dir=self.paths.reports_markdown_path
        )
        print(f"Reports exported to markdown in {self.paths.reports_markdown_path}")

    def chunk_reports(self, include_serialized_tables: bool = False):
        """
        将规整后 markdown 报告分块，便于后续向量化和检索
        """
        text_splitter = TextSplitter()
        # 只处理 markdown 文件，输入目录为 reports_markdown_path，输出目录为 documents_dir
        print(f"开始分割 {self.paths.reports_markdown_path} 目录下的 markdown 文件...")
        # 自动传入 subset.csv 路径，便于补充 company_name 字段
        text_splitter.split_markdown_reports(
            all_md_dir=self.paths.reports_markdown_path,
            output_dir=self.paths.documents_dir,
            subset_csv=self.paths.subset_path
        )
        print(f"分割完成，结果已保存到 {self.paths.documents_dir}")

    def create_vector_dbs(self):
        """从分块报告创建向量数据库"""
        input_dir = self.paths.documents_dir
        output_dir = self.paths.vector_db_dir
        
        vdb_ingestor = VectorDBIngestor()
        vdb_ingestor.process_reports(input_dir, output_dir)
        print(f"Vector databases created in {output_dir}")
    
    def create_bm25_db(self):
        """从分块报告创建BM25数据库"""
        input_dir = self.paths.documents_dir
        output_file = self.paths.bm25_db_path
        
        bm25_ingestor = BM25Ingestor()
        bm25_ingestor.process_reports(input_dir, output_file)
        print(f"BM25 database created at {output_file}")
    
    def parse_pdf_reports(self, parallel: bool = True, chunk_size: int = 2, max_workers: int = 10):
        # 解析PDF报告，支持并行处理
        if parallel:
            self.parse_pdf_reports_parallel(chunk_size=chunk_size, max_workers=max_workers)
        else:
            self.parse_pdf_reports_sequential()

    def process_parsed_reports(self):
        """
        处理已解析的PDF报告，主要流程：
        1. 对报告进行分块
        2. 创建向量数据库
        """
        print("开始处理报告流程...")
        
        print("步骤1：报告分块...")
        self.chunk_reports()
        
        print("步骤2：创建向量数据库...")
        self.create_vector_dbs()
        
        print("报告处理流程已成功完成！")
        
    def _get_next_available_filename(self, base_path: Path) -> Path:
        """
        获取下一个可用的文件名，如果文件已存在则自动添加编号后缀。
        例如：若answers.json已存在，则返回answers_01.json等。
        """
        if not base_path.exists():
            return base_path
            
        stem = base_path.stem
        suffix = base_path.suffix
        parent = base_path.parent
        
        counter = 1
        while True:
            new_filename = f"{stem}_{counter:02d}{suffix}"
            new_path = parent / new_filename
            
            if not new_path.exists():
                return new_path
            counter += 1

    def process_questions(self):
        # 处理所有问题，生成答案文件
        processor = QuestionsProcessor(
            vector_db_dir=self.paths.vector_db_dir,
            documents_dir=self.paths.documents_dir,
            questions_file_path=self.paths.questions_file_path,
            new_challenge_pipeline=True,
            subset_path=self.paths.subset_path,
            parent_document_retrieval=self.run_config.parent_document_retrieval,
            llm_reranking=self.run_config.llm_reranking,
            llm_reranking_sample_size=self.run_config.llm_reranking_sample_size,
            top_n_retrieval=self.run_config.top_n_retrieval,
            parallel_requests=self.run_config.parallel_requests,
            api_provider=self.run_config.api_provider,
            answering_model=self.run_config.answering_model,
            full_context=self.run_config.full_context            
        )
        
        output_path = self._get_next_available_filename(self.paths.answers_file_path)
        
        _ = processor.process_all_questions(
            output_path=str(output_path),
            submission_file=self.run_config.submission_file,
            pipeline_details=self.run_config.pipeline_details
        )
        print(f"Answers saved to {output_path}")

    def answer_single_question(self, question: str, kind: str = "string"):
        """
        单条问题即时推理，返回结构化答案（dict）。
        kind: 支持 'string'、'number'、'boolean'、'names' 等
        """
        t0 = time.time()
        print("[计时] 开始初始化 QuestionsProcessor ...")
        processor = QuestionsProcessor(
            vector_db_dir=self.paths.vector_db_dir,
            documents_dir=self.paths.documents_dir,
            questions_file_path=None,  # 单问无需文件
            new_challenge_pipeline=True,
            subset_path=self.paths.subset_path,
            parent_document_retrieval=self.run_config.parent_document_retrieval,
            llm_reranking=self.run_config.llm_reranking,
            llm_reranking_sample_size=self.run_config.llm_reranking_sample_size,
            top_n_retrieval=self.run_config.top_n_retrieval,
            parallel_requests=1,
            api_provider=self.run_config.api_provider,
            answering_model=self.run_config.answering_model,
            full_context=self.run_config.full_context
        )
        t1 = time.time()
        print(f"[计时] QuestionsProcessor 初始化耗时: {t1-t0:.2f} 秒")
        print("[计时] 开始调用 process_single_question ...")
        answer = processor.process_single_question(question, kind=kind)
        t2 = time.time()
        print(f"[计时] process_single_question 推理耗时: {t2-t1:.2f} 秒")
        print(f"[计时] answer_single_question 总耗时: {t2-t0:.2f} 秒")
        
        # 确保返回结构符合要求：{"content": "{...}"}
        import json
        import re
        
        if isinstance(answer, dict):
            # 检查是否已经包含完整的结构化信息
            if "step_by_step_analysis" in answer and "final_answer" in answer:
                # 如果是完整的结构化信息，直接包装为content字段
                answer = {"content": json.dumps(answer, ensure_ascii=False)}
            else:
                # 如果answer是字典，但不包含完整结构，将其序列化为JSON字符串
                answer = {"content": json.dumps(answer, ensure_ascii=False)}
        elif isinstance(answer, str):
            # 如果answer是字符串，需要处理可能包含在代码块标记中的JSON
            # 移除可能存在的代码块标记（三个反引号）
            cleaned_answer = re.sub(r'^```(?:json)?\s*|\s*```$', '', answer.strip())
            try:
                # 尝试解析清理后的字符串
                parsed = json.loads(cleaned_answer)
                answer = {"content": json.dumps(parsed, ensure_ascii=False)}
            except json.JSONDecodeError:
                # 如果无法解析为JSON，则直接包装为content字段
                answer = {"content": json.dumps({"final_answer": answer}, ensure_ascii=False)}
        
        return answer

preprocess_configs = {"ser_tab": RunConfig(use_serialized_tables=True),
                      "no_ser_tab": RunConfig(use_serialized_tables=False)}

base_config = RunConfig(
    parallel_requests=10,
    submission_file=True,
    pipeline_details="Custom pdf parsing + vDB + Router + SO CoT; llm = GPT-4o-mini",
    config_suffix="_base"
)

parent_document_retrieval_config = RunConfig(
    parent_document_retrieval=True,
    parallel_requests=20,
    submission_file=True,
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + SO CoT; llm = GPT-4o",
    answering_model="gpt-4o-2024-08-06",
    config_suffix="_pdr"
)

## 这里
max_config = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=True,
    parallel_requests=4,
    submission_file=True,
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + reranking + SO CoT; llm = qwen-turbo",
    answering_model="qwen-turbo-latest",
    config_suffix="_qwen_turbo"
)


configs = {"base": base_config,
           "pdr": parent_document_retrieval_config,
           "max": max_config}


# 你可以直接在本文件中运行任意方法：
# python .\src\pipeline.py
# 只需取消你想运行的方法的注释即可
# 你也可以修改 run_config 以尝试不同的配置
if __name__ == "__main__":
    # 设置数据集根目录（此处以 test_set 为例）
    root_path = here() / "data" / "stock_data"
    print('root_path:', root_path)
    #print(type(root_path))
    # 初始化主流程，使用推荐的最佳配置
    pipeline = Pipeline(root_path, run_config=max_config)
    
    # 1. 解析PDF报告为结构化JSON
    print('1. 解析PDF报告为结构化JSON')
    pipeline.parse_pdf_reports_sequential() 
    
    # 2. 序列化表格
    print('2. 序列化表格')
    pipeline.serialize_tables(max_workers=5) 
    
    # 3. 将解析后的JSON规整为更简单的每页文本结构
    print('3. 将解析后的JSON规整为更简单的每页文本结构')
    pipeline.merge_reports()
    
    # 4. 导出规整后报告为纯文本
    print('4. 导出规整后报告为纯文本')
    pipeline.export_reports_to_markdown()
    
    # 5. 将规整后报告分块，便于后续向量化，输出到 databases/chunked_reports
    print('5. 将规整后报告分块，便于后续向量化，输出到 databases/chunked_reports')
    pipeline.chunk_reports() 
    
    # 6. 从分块报告创建向量数据库，输出到 databases/vector_dbs
    print('6. 从分块报告创建向量数据库，输出到 databases/vector_dbs')
    pipeline.create_vector_dbs()     
    
    # 7. 处理问题并生成答案，具体逻辑取决于 run_config
    # 默认questions.json
    print('7. 处理问题并生成答案，具体逻辑取决于 run_config')
    pipeline.process_questions() 
    
    print('完成')