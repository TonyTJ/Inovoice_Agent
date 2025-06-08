
from flask import Flask, request, make_response
import base64  # 新增Base64解码模块
import os

app = Flask(__name__)

def data_dump(uuid, mime_type, file_data, workdir='workdir'):
    file_ext = '.' + mime_type.split('/')[1]
    dst_path = os.path.join(workdir, uuid + file_ext)
    with open(dst_path, 'wb') as f:
        f.write(file_data)

@app.route('/data_preprocess', methods=['POST'])
def data_preprocess():
    json_data = request.get_json()
    mime_type = json_data['mime_type']
    uuid = json_data['uuid']
    file_data = base64.b64decode(json_data['data'])  # Base64解码
    
    data_dump(uuid, mime_type, file_data)
    return "Base64 file saved successfully", 200
    
    # return "Unsupported request format", 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)