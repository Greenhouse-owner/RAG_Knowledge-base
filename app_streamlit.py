import streamlit as st
from pathlib import Path
from src.pipeline import Pipeline, max_config
from src.questions_processing import QuestionsProcessor
import json
import os
import traceback

# 你可以让 root_path 固定，也可以让用户输入
root_path = Path("data/stock_data")
pipeline = Pipeline(root_path, run_config=max_config)

st.set_page_config(page_title="RAG Challenge 2", layout="wide")

# 页面标题
st.markdown("""
<div style='background: linear-gradient(90deg, #7b2ff2 0%, #f357a8 100%); padding: 20px 0; border-radius: 12px; text-align: center;'>
    <h2 style='color: white; margin: 0;'>🚀 RAG Challenge 2</h2>
    <div style='color: #fff; font-size: 16px;'>基于深度RAG系统，由RTX 5080 GPU加速 | 支持多公司年报问答 | 向量检索+LLM推理+GPT-4o</div>
</div>
""", unsafe_allow_html=True)

# 左侧输入区
with st.sidebar:
    st.header("查询设置")
    # 仅单问题输入
    user_question = st.text_area("输入问题", "请简要总结公司2022年主营业务的主要内容。", height=80)
    submit_btn = st.button("生成答案", use_container_width=True)
    
    # 添加环境检查
    st.subheader("环境检查")
    if os.getenv("DASHSCOPE_API_KEY"):
        st.success("✅ DashScope API密钥已配置")
    else:
        st.error("❌ 未找到DashScope API密钥，请检查.env文件")

# 右侧主内容区
st.markdown("<h3 style='margin-top: 24px;'>检索结果</h3>", unsafe_allow_html=True)

if submit_btn and user_question.strip():
    with st.spinner("正在生成答案，请稍候..."):
        try:
            # 检查必要文件是否存在
            required_paths = [
                root_path / "databases/vector_dbs",
                root_path / "databases/chunked_reports"
            ]
            
            missing_paths = [p for p in required_paths if not p.exists()]
            if missing_paths:
                st.error(f"缺少必要的数据文件，请先运行数据处理流程: {missing_paths}")
                st.info("请确保已运行以下命令生成必要数据：\n\n1. python src/pipeline.py\n\n2. 确保所有处理步骤完成")
            else:
                answer = pipeline.answer_single_question(user_question, kind="string")
                # 兼容 answer 可能为 str 或 dict
                if isinstance(answer, str):
                    try:
                        answer_dict = json.loads(answer)
                    except Exception:
                        st.error("返回内容无法解析为结构化答案：" + str(answer))
                        answer_dict = {}
                else:
                    answer_dict = answer
                    
                # 优先从 content 字段取各项内容
                content = answer_dict.get("content", answer_dict)
                
                # 如果 content 是字符串，尝试解析为 JSON 对象
                if isinstance(content, str):
                    # 首先尝试直接解析
                    try:
                        content = json.loads(content)
                    except json.JSONDecodeError:
                        # 如果失败，尝试移除可能的代码块标记后再解析
                        import re
                        # 移除开头和结尾的代码块标记
                        cleaned_content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
                        try:
                            content = json.loads(cleaned_content)
                        except json.JSONDecodeError:
                            # 如果仍然失败，保持原始内容
                            pass
                
                # 从 content 中提取各项内容
                if isinstance(content, dict):
                    step_by_step = content.get("step_by_step_analysis", "-")
                    reasoning_summary = content.get("reasoning_summary", "-")
                    relevant_pages = content.get("relevant_pages", [])
                    final_answer = content.get("final_answer", "-")
                else:
                    step_by_step = "-"
                    reasoning_summary = "-"
                    relevant_pages = []
                    final_answer = str(content)
                
                # 打印调试
                print("[DEBUG] step_by_step_analysis:", step_by_step)
                print("[DEBUG] reasoning_summary:", reasoning_summary)
                print("[DEBUG] relevant_pages:", relevant_pages)
                print("[DEBUG] final_answer:", final_answer)
                st.markdown("**分步推理：**")
                st.info(step_by_step)
                st.markdown("**推理摘要：**")
                st.success(reasoning_summary)
                st.markdown("**相关页面：** ")
                st.write(relevant_pages)
                st.markdown("**最终答案：**")
                st.markdown(f"<div style='background:#f6f8fa;padding:16px;border-radius:8px;font-size:18px;'>{final_answer}</div>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"生成答案时出错: {e}")
            st.text_area("详细错误信息:", traceback.format_exc(), height=200)
else:
    st.info("请在左侧输入问题并点击【生成答案】")
    
# 添加使用说明
with st.expander("使用说明"):
    st.markdown("""
    ### 如何使用本系统：
    
    1. **确保数据已准备**：
       - PDF年报已放入 `data/stock_data/pdf_reports` 目录
       - 运行 `python src/pipeline.py` 完成数据处理流程
    
    2. **输入问题**：
       - 在左侧输入框中输入问题
       - 问题中应包含公司名称（如"请简要总结**中芯国际**2022年主营业务的主要内容"）
    
    3. **生成答案**：
       - 点击"生成答案"按钮
       - 等待系统检索相关信息并生成答案
    
    ### 常见问题排查：
    
    - **无法生成答案**：
      - 检查.env文件中API密钥是否正确配置
      - 确认网络连接正常
      - 确认已完成数据处理流程
    """)