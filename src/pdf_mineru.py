import requests
import time
import os
from pathlib import Path
import zipfile

class PDFMineru:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://mineru.net/api/v4/extract/task"
        
    def get_task_id(self, pdf_url: str) -> str:
        """获取PDF解析任务ID"""
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        
        data = {
            'url': pdf_url,
            'is_ocr': True,
            'enable_formula': False
        }
        
        response = requests.post(self.base_url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            task_id = result['data']['task_id']
            return task_id
        else:
            raise Exception(f"Failed to create task: {response.text}")
    
    def get_task_id_for_local_file(self, file_path: str) -> str:
        """为本地文件获取PDF解析任务ID"""
        # 注意：对于本地文件，我们需要先将其上传到可访问的位置
        # 或者使用Mineru支持的其他方式处理本地文件
        # 这里我们简化处理，假设有一个上传接口
        raise NotImplementedError("需要实现本地文件上传功能")
    
    def get_result(self, task_id: str) -> dict:
        """获取PDF解析结果"""
        url = f"{self.base_url}/{task_id}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        
        while True:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                state = result['data']['state']
                err_msg = result['data'].get('err_msg')
                
                # 如果有错误，输出错误信息
                if err_msg:
                    print(f"任务出错: {err_msg}")
                    return None
                
                # 如果任务完成，下载文件
                if state == 'done':
                    full_zip_url = result['data']['full_zip_url']
                    if full_zip_url:
                        local_filename = f"{task_id}.zip"
                        print(f"开始下载: {full_zip_url}")
                        
                        r = requests.get(full_zip_url, stream=True)
                        with open(local_filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        
                        print(f"下载完成，已保存到: {local_filename}")
                        
                        # 解压ZIP文件
                        extract_dir = local_filename.rsplit('.zip')[0]
                        try:
                            with zipfile.ZipFile(local_filename, 'r') as zip_ref:
                                zip_ref.extractall(extract_dir)
                            print(f"已解压到: {extract_dir}")
                        except Exception as e:
                            print(f"解压失败: {e}")
                            
                        return result
                
                # 如果任务还在进行中，等待后重试
                if state in ['pending', 'running']:
                    print("任务未完成，等待5秒后重试...")
                    time.sleep(5)
                    continue
            else:
                print(f"请求失败: {response.status_code}, {response.text}")
                time.sleep(5)
                continue

# 创建全局实例
mineru_api_key = os.getenv("MINERU_API_KEY")
if mineru_api_key:
    mineru_client = PDFMineru(mineru_api_key)
else:
    mineru_client = None
    print("警告: MINERU_API_KEY 未设置，PDF解析功能将不可用")

# 提供便捷的函数接口

def get_task_id(file_name: str) -> str:
    """获取PDF解析任务ID的便捷函数"""
    if mineru_client is None:
        raise RuntimeError("Mineru client not initialized. Please set MINERU_API_KEY in .env file.")
    return mineru_client.get_task_id(file_name)

def get_result(task_id: str) -> dict:
    """获取PDF解析结果的便捷函数"""
    if mineru_client is None:
        raise RuntimeError("Mineru client not initialized. Please set MINERU_API_KEY in .env file.")
    return mineru_client.get_result(task_id)

def unzip_file(zip_path: str, extract_to: str = None) -> str:
    """解压ZIP文件到指定目录"""
    if extract_to is None:
        extract_to = zip_path.rsplit('.zip')[0]
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"已解压 {zip_path} 到 {extract_to}")
        return extract_to
    except Exception as e:
        print(f"解压失败: {e}")
        return None