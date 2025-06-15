
from flask import Flask, request, jsonify
import base64
import os
import fitz
from PIL import Image
import numpy as np
import json

app = Flask(__name__)

def data_dump(uuid, mime_type, file_data, workdir='workdir'):
    file_ext = '.' + mime_type.split('/')[1]
    dst_path = os.path.join(workdir, uuid, 'src', uuid + file_ext)
    if not os.path.exists(os.path.dirname(dst_path)):
        os.makedirs(os.path.dirname(dst_path))
    with open(dst_path, 'wb') as f:
        f.write(file_data)
    if mime_type.split('/')[0] == 'image':
        json_config = {
            'task_type': 'handwritting',
            'src_list': [dst_path],
        }
        return json_config
    elif mime_type.split('/')[0] == 'application' and mime_type.split('/')[1] == 'pdf':
        images = pdf_to_images(dst_path)
        json_config = {
            'task_type': 'print',
            'src_list': [],
        }
        for i, data in enumerate(images):
            pil_image = Image.fromarray(data)
            image_dst_path = os.path.join(workdir, uuid, 'src', uuid + '_' + str(i) + '.png')
            pil_image.save(image_dst_path)
            json_config['src_list'].append(image_dst_path)
        return json_config
    else:
        return False
        
def pdf_to_images(pdf_path, dpi=300):
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)  # 设置分辨率
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(np.array(img))
    doc.close()
    return images

@app.route('/data_preprocess', methods=['POST'])
def data_preprocess():
    json_data = request.get_json()
    mime_type = json_data['mime_type']
    uuid = json_data['uuid']
    file_data = base64.b64decode(json_data['data'])  # Base64解码
    
    config = data_dump(uuid, mime_type, file_data)
    if config:
        return jsonify(config), 200
    else:
        return "Unsupported file format", 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)