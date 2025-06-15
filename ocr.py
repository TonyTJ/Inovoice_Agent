from flask import Flask, request, jsonify
from paddleocr import PaddleOCR
import os

app = Flask(__name__)

# PP-OCRv5_server 模型
ocr_model = PaddleOCR(
    device="gpu",
    det_db_unclip_ratio=2.0,
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

@app.route('/ocr', methods=['POST'])
def ocr():
    json_data = request.get_json()
    src_list = json_data['src_list']
    output_dir = os.path.dirname(src_list[0]).replace('src', 'ocr')
    ocr_list = []
    for src in src_list:
        # 大图如pdf推理太占显存，目前机器12GB显存只能推一张。实际能输入图像list
        result = ocr_model.predict(src)
        basename = os.path.splitext(os.path.basename(src))[0]
        # png结果用于调试，对结果无影响
        # result[0].save_to_img(os.path.join(output_dir, basename + '.png'))
        result[0].save_to_json(os.path.join(output_dir, basename + '.json'))
        ocr_list.append(os.path.join(output_dir, basename + '.json'))
    json_data['ocr_list'] = ocr_list
    return jsonify(json_data), 200
        
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)