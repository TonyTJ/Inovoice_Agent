import requests
import os
import uuid

if __name__ == '__main__':
    webhook_url = 'http://localhost:5678/webhook-test/c7645656-a150-424d-bacd-f52a9f4eae30'
    src = './resource/oracle_order_chinese_1.pdf'
    mime_type = 'application/pdf'
    # mime_type = 'image/jpg'
    
    file_ext = os.path.splitext(src)[1][1:]
    with open(src, 'rb') as f:
        files = {'file': (src, f, mime_type)}  # 显式指定MIME类型
        uuid_str = str(uuid.uuid4())
        headers = {
            'X-UUID': uuid_str,
        }
        status = requests.post(webhook_url, files=files, headers=headers)
        print(status.status_code)