from PIL import Image
from fuzzy_match import FuzzyMatchHandwriting
from fuzzy_match import FuzzyMatchPrint
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route('/fuzzy_match_handwriting', methods=['POST'])
def fuzzy_match_handwriting():
    json_data = request.get_json()
    ocr_list = json_data['ocr_list']
    
    Matcher = FuzzyMatchHandwriting()
    ocr_path = ocr_list[0]
    Matcher.fuzzy_match(ocr_path)
    output_dir = os.path.dirname(ocr_path).replace('ocr', 'output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_path = os.path.join(output_dir, 'output.json')
    output = Matcher.format_output(output_path)
    
    src_list = json_data['src_list']
    src_path = src_list[0]
    Matcher.render_result(src_path)
    
    return jsonify(output), 200

@app.route('/fuzzy_match_print', methods=['POST'])
def fuzzy_match_print():
    json_data = request.get_json()
    ocr_list = json_data['ocr_list']
    
    Matcher = FuzzyMatchPrint()
    Matcher.fuzzy_match(ocr_list)
    output_dir = os.path.dirname(ocr_list[0]).replace('ocr', 'output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_path = os.path.join(output_dir, 'output.json')
    output = Matcher.format_output(output_path)
    
    src_list = json_data['src_list']
    Matcher.render_result(src_list)
    
    return jsonify(output), 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
    
