import os
import json
import pickle
from typing import List, Union
from pathlib import Path
from tqdm import tqdm
import hashlib
import logging

from dotenv import load_dotenv
load_dotenv()  # 确保加载环境变量

from openai import OpenAI
from rank_bm25 import BM25Okapi
import faiss
import numpy as np
from tenacity import retry, wait_fixed, stop_after_attempt
import dashscope
from dashscope import TextEmbedding
import unicodedata
import re

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# BM25Ingestor：BM25索引构建与保存工具
class BM25Ingestor:
    def __init__(self):
        pass

    def create_bm25_index(self, chunks: List[str]) -> BM25Okapi:
        """从文本块列表创建BM25索引"""
        tokenized_chunks = [chunk.split() for chunk in chunks]
        return BM25Okapi(tokenized_chunks)
    
    def process_reports(self, all_reports_dir: Path, output_dir: Path):
        """
        批量处理所有报告，生成并保存BM25索引。
        参数：
            all_reports_dir (Path): 存放JSON报告的目录
            output_dir (Path): 保存BM25索引的目录
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        all_report_paths = list(all_reports_dir.glob("*.json"))

        for report_path in tqdm(all_report_paths, desc="Processing reports for BM25"):
            # 加载报告
            with open(report_path, 'r', encoding='utf-8') as f:
                report_data = json.load(f)
                
            # 提取文本块并创建BM25索引
            text_chunks = [chunk['text'] for chunk in report_data['content']['chunks']]
            bm25_index = self.create_bm25_index(text_chunks)
            
            # 保存BM25索引，文件名用sha1_name
            sha1_name = report_data["metainfo"]["sha1"]
            output_file = output_dir / f"{sha1_name}.pkl"
            with open(output_file, 'wb') as f:
                pickle.dump(bm25_index, f)
                
        print(f"Processed {len(all_report_paths)} reports")

# VectorDBIngestor：向量库构建与保存工具
class VectorDBIngestor:
    def __init__(self, use_openai_compatible: bool = False):
        """
        初始化向量数据库构建器
        :param use_openai_compatible: 是否使用OpenAI兼容模式调用DashScope API
        """
        self.use_openai_compatible = use_openai_compatible
        if use_openai_compatible:
            # 使用OpenAI兼容模式
            self.client = OpenAI(
                api_key=os.getenv("DASHSCOPE_API_KEY"),
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            logger.info("Using OpenAI-compatible mode for DashScope API")
        else:
            # 使用DashScope原生API
            dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
            if not dashscope.api_key:
                raise ValueError("DASHSCOPE_API_KEY not found in environment variables")
            logger.info("Using native DashScope API")
            # 验证API密钥
            if len(dashscope.api_key) < 20:
                logger.warning("DashScope API key seems unusually short. Please verify it's correct.")

    @retry(wait=wait_fixed(20), stop=stop_after_attempt(3))
    def _get_embeddings(self, text: Union[str, List[str]], model: str = "text-embedding-v1") -> List[float]:
        # 获取文本或文本块的嵌入向量，支持重试
        if isinstance(text, str) and not text.strip():
            raise ValueError("Input text cannot be an empty string.")
        
        # 保证 input 为一维字符串列表或单个字符串
        if isinstance(text, list):
            text_chunks = text
        else:
            text_chunks = [text]

        # 类型检查，确保每一项都是字符串
        if not all(isinstance(x, str) for x in text_chunks):
            raise ValueError("所有待嵌入文本必须为字符串类型！实际类型: {}".format([type(x) for x in text_chunks]))

        # 过滤空字符串
        text_chunks = [x for x in text_chunks if x.strip()]
        if not text_chunks:
            raise ValueError("所有待嵌入文本均为空字符串！")
        
        logger.info(f"Generating embeddings for {len(text_chunks)} text chunks")
        
        if self.use_openai_compatible:
            return self._get_embeddings_openai_compatible(text_chunks)
        else:
            return self._get_embeddings_native(text_chunks)

    def _get_embeddings_openai_compatible(self, text_chunks: List[str]) -> List[float]:
        """使用OpenAI兼容模式获取嵌入向量"""
        embeddings = []
        MAX_BATCH_SIZE = 25
        for i in range(0, len(text_chunks), MAX_BATCH_SIZE):
            batch = text_chunks[i:i+MAX_BATCH_SIZE]
            try:
                resp = self.client.embeddings.create(
                    model="text-embedding-v4",
                    input=batch,
                    dimensions=1024,
                    encoding_format="float"
                )
                
                # 解析响应
                for item in resp.data:
                    embeddings.append(item.embedding)
                    
            except Exception as e:
                logger.error(f"Error generating embeddings with OpenAI-compatible API: {str(e)}")
                raise RuntimeError(f"Error generating embeddings: {str(e)}") from e
                
        logger.info(f"Successfully generated {len(embeddings)} embeddings using OpenAI-compatible API")
        return embeddings

    def _get_embeddings_native(self, text_chunks: List[str]) -> List[float]:
        """使用DashScope原生API获取嵌入向量"""
        embeddings = []
        MAX_BATCH_SIZE = 25
        for i in range(0, len(text_chunks), MAX_BATCH_SIZE):
            batch = text_chunks[i:i+MAX_BATCH_SIZE]
            try:
                resp = TextEmbedding.call(
                    model=TextEmbedding.Models.text_embedding_v1,
                    input=batch
                )
                
                # 检查API调用是否成功
                if resp.status_code != 200:
                    logger.error(f"DashScope API error: {resp}")
                    if resp.status_code == 401:
                        raise RuntimeError("DashScope API authentication failed. Please check your DASHSCOPE_API_KEY in the .env file.")
                    raise RuntimeError(f"DashScope API error: {resp}")
                
                # 正确处理响应格式
                if hasattr(resp, 'output') and isinstance(resp.output, dict):
                    if 'embeddings' in resp.output:
                        # 处理批量响应
                        for emb in resp.output['embeddings']:
                            if emb['embedding'] is None or len(emb['embedding']) == 0:
                                error_text = batch[emb['text_index']] if 'text_index' in emb else None
                                logger.error(f"DashScope returned empty embedding for text: {error_text}")
                                raise RuntimeError(f"DashScope returned empty embedding for text at index {emb.get('text_index', 'unknown')}")
                            embeddings.append(emb['embedding'])
                    elif 'embedding' in resp.output:
                        # 处理单个响应
                        if resp.output['embedding'] is None or len(resp.output['embedding']) == 0:
                            logger.error("DashScope returned empty embedding")
                            raise RuntimeError("DashScope returned empty embedding")
                        embeddings.append(resp.output['embedding'])
                    else:
                        logger.error(f"Unexpected DashScope API response format: {resp}")
                        raise RuntimeError(f"DashScope embedding API returned unexpected format: {resp}")
                else:
                    logger.error(f"Unexpected DashScope API response format: {resp}")
                    raise RuntimeError(f"DashScope embedding API returned unexpected format: {resp}")
                    
            except Exception as e:
                logger.error(f"Error generating embeddings for batch: {str(e)}")
                raise RuntimeError(f"Error generating embeddings: {str(e)}") from e
                
        logger.info(f"Successfully generated {len(embeddings)} embeddings using native API")
        return embeddings

    def _create_vector_db(self, embeddings: List[float]):
        # 用faiss构建向量库，采用内积（余弦距离）
        embeddings_array = np.array(embeddings, dtype=np.float32)
        dimension = len(embeddings[0])
        index = faiss.IndexFlatIP(dimension)  # Cosine distance
        index.add(embeddings_array)
        return index
    
    def _process_report(self, report: dict):
        # 针对单份报告，提取文本块并生成向量库
        # 修复：正确提取文本块中的文本内容
        if 'chunks' in report['content']:
            # 处理从Markdown文件分块的报告
            text_chunks = [chunk['text'] for chunk in report['content']['chunks'] if 'text' in chunk and chunk['text'].strip()]
        else:
            # 处理其他类型的报告
            text_chunks = [chunk['text'] for chunk in report['content']['chunks'] if 'text' in chunk and chunk['text'].strip()]
        
        # 过滤空内容，超长内容截断到 2048 字符
        max_len = 2048
        text_chunks = [t[:max_len] for t in text_chunks if len(t.strip()) > 0]
        
        if not text_chunks:
            logger.warning(f"报告 {report.get('metainfo', {}).get('file_name', 'unknown')} 没有有效的文本内容用于向量化")
            # 创建一个空的索引作为占位符
            dimension = 1024  # 假设嵌入维度为1024
            index = faiss.IndexFlatIP(dimension)
            return index
            
        embeddings = self._get_embeddings(text_chunks)
        index = self._create_vector_db(embeddings)
        return index

    def process_reports(self, all_reports_dir: Path, output_dir: Path):
        # 批量处理所有报告，生成并保存faiss向量库
        all_report_paths = list(all_reports_dir.glob("*.json"))
        output_dir.mkdir(parents=True, exist_ok=True)

        for idx, report_path in enumerate(tqdm(all_report_paths, desc="Processing reports for FAISS")):
            # 加载报告
            with open(report_path, 'r', encoding='utf-8') as f:
                report_data = json.load(f)
            index = self._process_report(report_data)
            # 使用报告中的sha1作为文件名，避免所有特殊字符问题
            sha1 = report_data["metainfo"]["sha1"]
            # 清理文件名中的特殊字符
            safe_sha1 = self._sanitize_filename(sha1)
            faiss_file_path = output_dir / f"{safe_sha1}.faiss"
            # 确保文件路径有效
            print(f"尝试保存FAISS索引到: {faiss_file_path}")
            faiss.write_index(index, str(faiss_file_path))

        print(f"Processed {len(all_report_paths)} reports")
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的特殊字符，使其在Windows系统中有效"""
        # 标准化Unicode字符
        filename = unicodedata.normalize('NFKC', filename)
        # 移除或替换所有非ASCII字符和特殊符号
        filename = re.sub(r'[^\w\-_.\u4e00-\u9fff]', '_', filename)
        # 限制文件名长度
        if len(filename) > 30:  # 进一步缩短文件名
            filename = filename[:30]
        # 移除开头和结尾的下划线
        filename = filename.strip('_')
        # 确保只包含ASCII字符用于文件名
        filename = re.sub(r'[^\x00-\x7F]', '_', filename)
        return filename or 'default_filename'
