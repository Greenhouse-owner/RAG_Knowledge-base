import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def update_api_key_in_env():
    """帮助用户更新.env文件中的API Key"""
    env_file_path = '.env'
    
    # 读取当前的.env文件
    env_lines = []
    if os.path.exists(env_file_path):
        with open(env_file_path, 'r', encoding='utf-8') as f:
            env_lines = f.readlines()
    
    # 显示当前API Key（如果存在）
    current_key = os.getenv("DASHSCOPE_API_KEY", "")
    if current_key:
        print(f"当前配置的 DASHSCOPE_API_KEY: {current_key[:10]}{'*' * (len(current_key) - 10)}")
    else:
        print("未在环境变量中找到 DASHSCOPE_API_KEY")
    
    # 获取新的API Key
    new_key = input("请输入新的 DashScope API Key (直接回车跳过): ").strip()
    if not new_key:
        print("未输入新的 API Key，操作取消")
        return
    
    # 验证新API Key格式
    if not new_key.startswith("sk-"):
        print("警告: API Key 通常以 'sk-' 开头，请确认输入正确")
        confirm = input("是否继续使用此 API Key? (y/N): ").strip().lower()
        if confirm != 'y':
            print("操作取消")
            return
    
    # 更新.env文件
    dashscope_line_found = False
    for i, line in enumerate(env_lines):
        if line.startswith("DASHSCOPE_API_KEY="):
            env_lines[i] = f"DASHSCOPE_API_KEY={new_key}\n"
            dashscope_line_found = True
            break
    
    if not dashscope_line_found:
        env_lines.append(f"DASHSCOPE_API_KEY={new_key}\n")
    
    # 写入更新后的内容
    with open(env_file_path, 'w', encoding='utf-8') as f:
        f.writelines(env_lines)
    
    print("✅ .env 文件已更新")

if __name__ == "__main__":
    print("🔧 DashScope API Key 更新工具")
    update_api_key_in_env()