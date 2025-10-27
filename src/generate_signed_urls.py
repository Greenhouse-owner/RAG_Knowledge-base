import oss2
from datetime import datetime, timedelta
import os

# 1. 替换成阿里云信息
access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
endpoint = "oss-cn-beijing.aliyuncs.com"   # 你的地域节点（之前确认过是北京）
bucket_name = "businessbucketchuan"           # 例如：businessbucketchuan

# OSS上的PDF文件列表
oss_files = [
    "pdf/【上海证券】中芯国际深度研究报告：晶圆制造龙头，领航国产芯片新征程.pdf",
    "pdf/【东方证券】产能利用率提升，持续推进工艺迭代和产品性能升级.pdf",
    "pdf/【中原证券】产能利用率显著提升，持续推进工艺迭代升级——中芯国际(688981)季报点评.pdf",
    "pdf/【光大证券】中芯国际2025年一季度业绩点评：1Q突发生产问题，2Q业绩有望筑底，自主可控趋势不改.pdf",
    "pdf/【兴证国际】季度盈利低于预期，看好国产芯片长期空间.pdf",
    "pdf/【华泰证券】中芯国际（688981）：上调港股目标价到63港币，看好DeepSeek推动代工需求强劲增长.pdf",
    "pdf/【国信证券】工业与汽车触底反弹，良率影响短期营收.pdf",
    "pdf/【财报】中芯国际：中芯国际2024年年度报告.pdf",
    "pdf/中芯国际机构调研纪要.pdf"
]

# 创建bucket对象
bucket = oss2.Bucket(oss2.Auth(access_key_id, access_key_secret), endpoint, bucket_name)

print("生成签名URL以访问私有OSS文件...\n")

# 为每个文件生成签名URL（有效期24小时）
signed_urls = []
for i, oss_file in enumerate(oss_files, 1):
    # 生成签名URL，有效期24小时
    url = bucket.sign_url('GET', oss_file, 60*60*24)  # 60*60*24 = 24小时
    signed_urls.append(url)
    print(f"[{i}] {oss_file}")
    print(f"    签名URL: {url}\n")

print(f"总共生成了 {len(signed_urls)} 个签名URL")
print("\n注意：这些URL有效期为24小时，过期后需要重新生成。")