import os
from dotenv import load_dotenv
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

def check_and_fix_api_key():
    """检查并修复API密钥问题"""
    print("🔍 检查API密钥配置...")
    
    # 读取.env文件内容
    env_file_path = ".env"
    if not os.path.exists(env_file_path):
        logger.error(f"{env_file_path} 文件不存在")
        return False
    
    with open(env_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 查找DASHSCOPE_API_KEY行
    api_key_line_index = None
    api_key_value = None
    for i, line in enumerate(lines):
        if line.startswith("DASHSCOPE_API_KEY="):
            api_key_line_index = i
            api_key_value = line.strip().split("=", 1)[1]
            break
    
    if api_key_line_index is None:
        logger.error("未在.env文件中找到DASHSCOPE_API_KEY")
        return False
    
    print(f"当前API密钥: {api_key_value}")
    print(f"API密钥长度: {len(api_key_value)}")
    
    # 检查密钥是否看起来有效
    if len(api_key_value) < 20:
        print("❌ API密钥看起来太短，可能不完整")
        new_key = input("请输入正确的DASHSCOPE_API_KEY (留空跳过): ").strip()
        if new_key:
            # 替换API密钥
            lines[api_key_line_index] = f"DASHSCOPE_API_KEY={new_key}\n"
            with open(env_file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            print("✅ API密钥已更新")
            return True
        else:
            print("跳过API密钥更新")
            return False
    else:
        print("✅ API密钥看起来长度正常")
        return True

if __name__ == "__main__":
    success = check_and_fix_api_key()
    if success:
        print("\n✅ API密钥检查完成")
    else:
        print("\n❌ API密钥检查失败")