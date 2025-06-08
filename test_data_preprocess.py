import requests
import base64

if __name__ == '__main__':
    data_preprocess_url = 'http://localhost:8000/data_preprocess'
    src = 'resource/1.jpg'
    code = requests.post(data_preprocess_url)
    print(code.status_code)
    # with open(src, 'rb') as f:
        # files = {'file': (src, f, 'image/png')}  # 显式指定MIME类型
        
        
        # file_path = "F:\Code\InvoiceAgent\workdir\mp.png"
        # with open(file_path, "wb") as f2:
        #     f2.write(base64.b64decode(f))
        
    