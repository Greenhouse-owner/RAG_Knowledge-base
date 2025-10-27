import oss2
import os

# 1. 替换成你的阿里云信息（必须改！）
access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
endpoint = "oss-cn-beijing.aliyuncs.com"   # 你的地域节点（之前确认过是北京）
bucket_name = "businessbucketchuan"           # 例如：businessbucketchuan

# 2. 替换成你的本地PDF文件目录路径（必须改！）
local_pdf_directory = "C:/Users/Administrator/Desktop/test.pdf"  # 包含PDF文件的目录路径

# 3. OSS上的存储目录（可以不改）
oss_folder = "pdf/"  # 会存在OSS的pdf文件夹里

# 以下是上传代码（不用改）
bucket = oss2.Bucket(oss2.Auth(access_key_id, access_key_secret), endpoint, bucket_name)

# 遍历目录中的所有PDF文件并上传
uploaded_files = []
for filename in os.listdir(local_pdf_directory):
    if filename.endswith(".pdf"):
        local_file_path = os.path.join(local_pdf_directory, filename)
        oss_file_name = oss_folder + filename
        
        print(f"正在上传 {filename}...")
        # 上传文件并设置为公共读权限
        bucket.put_object_from_file(oss_file_name, local_file_path, headers={'Content-Type': 'application/pdf', 'x-oss-object-acl': 'public-read'})
        uploaded_files.append(oss_file_name)
        print(f"{filename} 上传成功！")

print(f"\n总共上传了 {len(uploaded_files)} 个文件:")
for file in uploaded_files:
    print(f"- https://{bucket_name}.{endpoint}/{file}")